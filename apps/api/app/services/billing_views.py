"""What a laundry owner sees about their plan, bills and Marketplace terms. Plain language; no internal codes."""
import json
import math
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..domain.clock import as_utc, now_utc
from ..domain.features import FEATURES
from ..models import (
    Business,
    MarketplaceAccount,
    PilotEnrollment,
    PilotProgram,
    SubscriptionInvoice,
    SubscriptionPayment,
    SubscriptionPlan,
)
from .billing import BillingService
from .commission import CommissionService, commission_terms
from .entitlements import plan_features, resolve
from .pricing import get_setting, price_in_force


def _days_left(until: datetime | None, now: datetime) -> int | None:
    """Whole days left, counted the way people do: a 14-day trial started now has 14 days left."""
    return None if until is None else max(0, math.ceil((as_utc(until) - now).total_seconds() / 86400))


def plan_card(db: Session, plan: SubscriptionPlan, business_id: str | None = None) -> dict:
    billing = BillingService(db)
    prices = {}
    for interval in ("MONTHLY", "ANNUAL"):
        price = price_in_force(db, plan.id, interval)
        if price is None:
            continue
        prices[interval] = billing.quote(business_id, plan, interval) if business_id else \
            {"list_price": price.amount, "discount": 0, "price": price.amount, "terms": []}
    return {"id": plan.id, "name": plan.name, "description": plan.description, "benefits": json.loads(plan.benefits_json),
            "features": sorted(plan_features(db, plan.id)), "trial_days": plan.trial_days, "max_staff": plan.max_staff,
            "max_branches": plan.max_branches, "prices": prices, "rank": plan.sort_order}


def notices(db: Session, business: Business, effective, now: datetime) -> list[dict]:
    out = []
    sub = effective.subscription
    if effective.source in ("COMPLIMENTARY", "PILOT") and effective.ends_at:
        days = _days_left(effective.ends_at, now)
        policy = None
        if effective.source == "PILOT" and effective.override and effective.override.pilot_enrollment_id:
            enrollment = db.get(PilotEnrollment, effective.override.pilot_enrollment_id)
            policy = db.get(PilotProgram, enrollment.program_id).transition_policy if enrollment else None
        out.append({"kind": "pilot_ending" if effective.source == "PILOT" else "complimentary_ending", "days": days,
                    "ends_at": effective.ends_at, "plan": effective.plan.name, "policy": policy,
                    "level": "warning" if days is not None and days <= 14 else "info"})
    if sub and sub.status == "TRIALING" and sub.trial_ends_at:
        out.append({"kind": "trial_ending", "days": _days_left(sub.trial_ends_at, now), "ends_at": sub.trial_ends_at,
                    "plan": effective.plan.name, "level": "info"})
    if sub:
        for inv in db.scalars(select(SubscriptionInvoice).where(SubscriptionInvoice.subscription_id == sub.id,
                                                               SubscriptionInvoice.status == "OPEN")):
            overdue = as_utc(inv.due_at) < now
            out.append({"kind": "invoice_overdue" if overdue else "invoice_open", "invoice_id": inv.id,
                        "number": inv.number, "amount": inv.amount_due - inv.amount_paid, "due_at": inv.due_at,
                        "level": "danger" if overdue else "info"})
        if sub.next_plan_id:
            out.append({"kind": "downgrade_scheduled", "plan": db.get(SubscriptionPlan, sub.next_plan_id).name,
                        "at": sub.current_period_end, "level": "info"})
        if sub.cancel_at_period_end:
            out.append({"kind": "cancel_scheduled", "at": sub.current_period_end, "level": "info"})
    return out


def subscription_view(db: Session, business: Business) -> dict:
    now = now_utc()
    effective = resolve(db, business.id, now)
    sub = effective.subscription
    billing = BillingService(db)
    plans = [plan_card(db, p, business.id) for p in db.scalars(
        select(SubscriptionPlan).where(SubscriptionPlan.status == "ACTIVE").order_by(SubscriptionPlan.sort_order))]
    invoices = [billing.invoice_out(i, with_lines=False) for i in db.scalars(
        select(SubscriptionInvoice).where(SubscriptionInvoice.business_id == business.id)
        .order_by(SubscriptionInvoice.issued_at.desc()).limit(24))]
    payments = [{"amount": p.amount, "method": p.method, "reference": p.reference, "received_at": p.received_at,
                 "invoice_id": p.invoice_id} for p in db.scalars(
        select(SubscriptionPayment).where(SubscriptionPayment.business_id == business.id)
        .order_by(SubscriptionPayment.received_at.desc()).limit(24))]
    account = db.scalar(select(MarketplaceAccount).where(MarketplaceAccount.business_id == business.id))
    rule = CommissionService(db).rule_for(business.id, now)
    on_subscription = sub is not None and sub.plan_id == effective.plan.id
    return {
        "current": {
            "plan": plan_card(db, effective.plan, business.id),
            "source": effective.source,  # DEFAULT | TRIAL | SUBSCRIPTION | COMPLIMENTARY | PILOT
            "status": sub.status if on_subscription else ("ACTIVE" if effective.source != "DEFAULT" else "FREE"),
            "interval": sub.interval if on_subscription else None,
            "price": sub.price_amount if on_subscription else 0,
            "period_start": sub.current_period_start if on_subscription else None,
            "renews_at": sub.current_period_end if on_subscription and not sub.cancel_at_period_end else None,
            "access_until": effective.ends_at,
            "terms": [o.reason for o in [effective.override] if o],
            "feature_names": [FEATURES[f] for f in sorted(effective.features) if f in FEATURES],
        },
        "subscription": None if not sub else {
            "plan": db.get(SubscriptionPlan, sub.plan_id).name, "status": sub.status, "interval": sub.interval,
            "price": sub.price_amount, "period_end": sub.current_period_end, "trial_ends_at": sub.trial_ends_at,
            "cancel_at_period_end": sub.cancel_at_period_end},
        "plans": plans,
        "invoices": invoices,
        "payments": payments,
        "notices": notices(db, business, effective, now),
        "payment_instructions": get_setting(db, "subscription_payment_instructions"),
        "marketplace": {"status": account.status if account else "NOT_ENROLLED", "commission": commission_terms(rule),
                        "listing_fee": get_setting(db, "marketplace_listing_fee") or 0,
                        "eligible": "marketplace_eligible" in effective.features},
    }
