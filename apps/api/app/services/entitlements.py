"""Which plan a business effectively has right now, and therefore which features and limits apply.

Resolution is time-based, so expiries take effect on the second they happen even if the billing job has not run yet:
  1. an active complimentary override (admin grant or pilot) for a plan;
  2. the current subscription, while it is trialling, paid up, or inside its grace period;
  3. otherwise the default plan.
If both 1 and 2 apply, the higher plan wins.
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..core.errors import AppError
from ..domain.clock import as_utc, now_utc
from ..domain.features import FEATURES
from ..models import (
    BusinessSubscription,
    CommercialOverride,
    PlanFeature,
    SubscriptionInvoice,
    SubscriptionPlan,
)


@dataclass
class EffectivePlan:
    plan: SubscriptionPlan
    features: set[str]
    source: str  # COMPLIMENTARY | PILOT | TRIAL | SUBSCRIPTION | DEFAULT
    ends_at: datetime | None = None
    subscription: BusinessSubscription | None = None
    override: CommercialOverride | None = None
    notices: list[dict] = field(default_factory=list)


def default_plan(db: Session) -> SubscriptionPlan:
    plan = db.scalar(select(SubscriptionPlan).where(SubscriptionPlan.is_default.is_(True)))
    if not plan:
        raise AppError(500, "NO_DEFAULT_PLAN", "No default plan is configured")
    return plan


def plan_features(db: Session, plan_id: str) -> set[str]:
    return set(db.scalars(select(PlanFeature.feature_key).where(PlanFeature.plan_id == plan_id, PlanFeature.enabled.is_(True))))


def active_overrides(db: Session, business_id: str, at: datetime, types: tuple[str, ...]) -> list[CommercialOverride]:
    return list(db.scalars(select(CommercialOverride).where(
        CommercialOverride.business_id == business_id, CommercialOverride.type.in_(types),
        CommercialOverride.revoked_at.is_(None), CommercialOverride.effective_from <= at,
        or_(CommercialOverride.expires_at.is_(None), CommercialOverride.expires_at > at))
        .order_by(CommercialOverride.created_at.desc())))


def current_subscription(db: Session, business_id: str) -> BusinessSubscription | None:
    return db.scalar(select(BusinessSubscription).where(BusinessSubscription.business_id == business_id,
                                                        BusinessSubscription.ended_at.is_(None)))


def subscription_access_until(db: Session, sub: BusinessSubscription) -> datetime | None:
    """The moment this subscription stops giving access (None = no access at all)."""
    plan = db.get(SubscriptionPlan, sub.plan_id)
    grace = timedelta(days=plan.grace_days)
    if sub.status == "TRIALING":
        return as_utc(sub.trial_ends_at) if sub.trial_ends_at else None
    if sub.status not in ("ACTIVE", "PAST_DUE"):
        return None
    oldest_unpaid = db.scalar(select(SubscriptionInvoice).where(
        SubscriptionInvoice.subscription_id == sub.id, SubscriptionInvoice.status == "OPEN",
        SubscriptionInvoice.amount_due > SubscriptionInvoice.amount_paid).order_by(SubscriptionInvoice.due_at))
    until = as_utc(sub.current_period_end) + grace
    if oldest_unpaid:
        until = min(until, as_utc(oldest_unpaid.due_at) + grace)
    return until


def resolve(db: Session, business_id: str, at: datetime | None = None) -> EffectivePlan:
    at = at or now_utc()
    options: list[EffectivePlan] = []
    for o in active_overrides(db, business_id, at, ("COMPLIMENTARY_PLAN",)):
        plan = db.get(SubscriptionPlan, o.plan_id)
        options.append(EffectivePlan(plan, set(), "PILOT" if o.pilot_enrollment_id else "COMPLIMENTARY",
                                     as_utc(o.expires_at) if o.expires_at else None, override=o))
    sub = current_subscription(db, business_id)
    if sub:
        until = subscription_access_until(db, sub)
        if until and until > at:
            source = "TRIAL" if sub.status == "TRIALING" else "SUBSCRIPTION"
            options.append(EffectivePlan(db.get(SubscriptionPlan, sub.plan_id), set(), source, until, subscription=sub))
    best = max(options, key=lambda e: e.plan.sort_order, default=None) or EffectivePlan(default_plan(db), set(), "DEFAULT")
    best.subscription = best.subscription or sub
    best.features = plan_features(db, best.plan.id)
    return best


def plans_with(db: Session, feature: str) -> list[str]:
    return list(db.scalars(select(SubscriptionPlan.name).join(PlanFeature, PlanFeature.plan_id == SubscriptionPlan.id)
                           .where(PlanFeature.feature_key == feature, PlanFeature.enabled.is_(True),
                                  SubscriptionPlan.status == "ACTIVE").order_by(SubscriptionPlan.sort_order)))


def require_feature(db: Session, business_id: str, feature: str) -> EffectivePlan:
    """Backend enforcement of plan features. Raises 402 with the plans that would unlock it."""
    if feature not in FEATURES:
        raise ValueError(f"Unknown feature {feature}")
    effective = resolve(db, business_id)
    if feature not in effective.features:
        raise AppError(402, "PLAN_UPGRADE_REQUIRED", "Your plan does not include this. Upgrade to use it.",
                       {"feature": feature, "current_plan": effective.plan.name, "available_on": plans_with(db, feature)})
    return effective
