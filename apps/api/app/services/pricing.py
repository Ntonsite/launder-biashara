"""Administration of the commercial model. Every change is validated, versioned where money depends on it, and
written to the pricing audit log with the previous and new values and a reason."""
import json
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..core.errors import AppError, not_found
from ..domain.clock import as_utc, now_utc
from ..domain.features import FEATURES
from ..models import (
    Business,
    BusinessSubscription,
    CommercialOverride,
    CommissionRule,
    PilotEnrollment,
    PilotProgram,
    PlanFeature,
    PlanPrice,
    PlatformSetting,
    PricingAuditLog,
    SubscriptionPlan,
    User,
)

INTERVALS = ("MONTHLY", "ANNUAL")
SETTINGS = {
    # key: (validator, description)
    "marketplace_listing_fee": (lambda v: isinstance(v, int) and 0 <= v <= 10_000_000, "Monthly Marketplace listing fee (TZS)"),
    "subscription_payment_instructions": (lambda v: isinstance(v, str) and 10 <= len(v) <= 1000, "How providers pay invoices"),
    "trial_reminder_days": (lambda v: isinstance(v, int) and 0 <= v <= 60, "Days before a trial or pilot ends to remind"),
    "invoice_payment_terms_days": (lambda v: isinstance(v, int) and 0 <= v <= 60, "Days to pay an invoice"),
}


def jsonable(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def snapshot(row, fields: tuple[str, ...]) -> dict:
    return {f: jsonable(getattr(row, f)) for f in fields}


def pricing_audit(db: Session, actor: User | None, action: str, entity: str, entity_id: str, before: dict | None,
                  after: dict | None, reason: str = "", business_id: str | None = None) -> None:
    db.add(PricingAuditLog(actor_id=actor.id if actor else None, action=action, entity=entity, entity_id=entity_id,
                           business_id=business_id, before_json=json.dumps(before) if before is not None else None,
                           after_json=json.dumps(after) if after is not None else None, reason=reason or ""))


def get_setting(db: Session, key: str):
    row = db.get(PlatformSetting, key)
    return json.loads(row.value_json) if row else None


def price_in_force(db: Session, plan_id: str, interval: str, at: datetime | None = None) -> PlanPrice | None:
    at = at or now_utc()
    return db.scalar(select(PlanPrice).where(PlanPrice.plan_id == plan_id, PlanPrice.interval == interval,
                                             PlanPrice.effective_from <= at,
                                             or_(PlanPrice.effective_to.is_(None), PlanPrice.effective_to > at))
                     .order_by(PlanPrice.effective_from.desc()))


PLAN_FIELDS = ("code", "name", "description", "benefits_json", "status", "is_default", "trial_days", "grace_days", "max_staff",
               "max_branches", "sort_order")
RULE_FIELDS = ("scope", "business_id", "rate", "min_commission", "include_pickup_fee", "discounts_reduce_basis",
               "effective_from", "effective_to", "reason")
OVERRIDE_FIELDS = ("business_id", "type", "plan_id", "value", "effective_from", "expires_at", "reason", "revoked_at")


class PricingAdmin:
    def __init__(self, db: Session, actor: User):
        self.db, self.actor = db, actor

    # ---- settings -------------------------------------------------------------------------------------------------
    def set_setting(self, key: str, value, reason: str, commit: bool = True) -> None:
        from .marketplace_program import MARKETPLACE_SETTINGS, normalize_setting

        registry = {**SETTINGS, **{k: v[:2] for k, v in MARKETPLACE_SETTINGS.items()}}
        if key not in registry:
            raise AppError(404, "NOT_FOUND", "Unknown setting")
        if not registry[key][0](value):
            raise AppError(422, "INVALID_VALUE", f"Invalid value for {registry[key][1]}")
        value = normalize_setting(key, value)
        row = self.db.get(PlatformSetting, key)
        before = json.loads(row.value_json) if row else None
        if row is None:
            row = PlatformSetting(key=key, value_json="null")
            self.db.add(row)
        row.value_json, row.updated_by = json.dumps(value), self.actor.id
        pricing_audit(self.db, self.actor, "SETTING_CHANGED", "setting", key, {"value": before}, {"value": value}, reason)
        if commit:
            self.db.commit()

    # ---- plans ----------------------------------------------------------------------------------------------------
    def create_plan(self, data: dict, prices: dict[str, int], features: dict[str, bool], reason: str) -> SubscriptionPlan:
        if self.db.scalar(select(SubscriptionPlan.id).where(SubscriptionPlan.code == data["code"])):
            raise AppError(409, "PLAN_CODE_TAKEN", "A plan with this code already exists")
        values = {k: v for k, v in data.items() if k != "benefits"}
        plan = SubscriptionPlan(**values, benefits_json=json.dumps(data.get("benefits", [])), is_default=False)
        self.db.add(plan)
        self.db.flush()
        for interval, amount in prices.items():
            self.db.add(PlanPrice(plan_id=plan.id, interval=interval, amount=amount, effective_from=now_utc(),
                                  created_by=self.actor.id))
        self._write_features(plan, features)
        pricing_audit(self.db, self.actor, "PLAN_CREATED", "plan", plan.id, None,
                      {**snapshot(plan, PLAN_FIELDS), "prices": prices, "features": features}, reason)
        self.db.commit()
        return plan

    def update_plan(self, plan: SubscriptionPlan, changes: dict, reason: str) -> SubscriptionPlan:
        before = snapshot(plan, PLAN_FIELDS)
        if "benefits" in changes:
            changes["benefits_json"] = json.dumps(changes.pop("benefits"))
        if changes.get("status") in ("RETIRED", "HIDDEN") and (plan.is_default or changes.get("is_default")):
            raise AppError(409, "DEFAULT_PLAN_REQUIRED", "Choose another default plan before retiring or hiding this one")
        if changes.get("is_default") is False and plan.is_default:
            raise AppError(409, "DEFAULT_PLAN_REQUIRED", "Make another plan the default instead")
        if changes.get("is_default") and not plan.is_default:
            if price_in_force(self.db, plan.id, "MONTHLY") and price_in_force(self.db, plan.id, "MONTHLY").amount > 0:
                raise AppError(409, "DEFAULT_PLAN_MUST_BE_FREE", "The default plan must be free")
            current = self.db.scalar(select(SubscriptionPlan).where(SubscriptionPlan.is_default.is_(True)))
            if current:
                current.is_default = False
                self.db.flush()
        for key, value in changes.items():
            setattr(plan, key, value)
        pricing_audit(self.db, self.actor, "PLAN_UPDATED", "plan", plan.id, before, snapshot(plan, PLAN_FIELDS), reason)
        self.db.commit()
        return plan

    def set_price(self, plan: SubscriptionPlan, interval: str, amount: int, effective_from: datetime | None,
                  reason: str) -> PlanPrice:
        """New price from a date. The price in force until then is closed at that date; history is untouched."""
        if interval not in INTERVALS:
            raise AppError(422, "INVALID_INTERVAL", "Interval must be MONTHLY or ANNUAL")
        if plan.is_default and amount > 0:
            raise AppError(409, "DEFAULT_PLAN_MUST_BE_FREE", "The default plan must be free")
        start = as_utc(effective_from) if effective_from else now_utc()
        if start < now_utc() - timedelta(minutes=5):
            raise AppError(422, "BACKDATED_PRICE", "Prices cannot start in the past")
        later = self.db.scalar(select(PlanPrice.id).where(PlanPrice.plan_id == plan.id, PlanPrice.interval == interval,
                                                         PlanPrice.effective_from >= start))
        if later:
            raise AppError(409, "OVERLAPPING_PRICE", "A price already starts on or after that date")
        current = price_in_force(self.db, plan.id, interval, start)
        before = {"amount": current.amount, "effective_from": current.effective_from.isoformat()} if current else None
        if current:
            current.effective_to = start
        price = PlanPrice(plan_id=plan.id, interval=interval, amount=amount, effective_from=start, created_by=self.actor.id)
        self.db.add(price)
        self.db.flush()
        pricing_audit(self.db, self.actor, "PLAN_PRICE_SET", "plan_price", price.id, before,
                      {"plan": plan.code, "interval": interval, "amount": amount, "effective_from": start.isoformat()}, reason)
        self.db.commit()
        return price

    def _write_features(self, plan: SubscriptionPlan, features: dict[str, bool]) -> None:
        unknown = set(features) - set(FEATURES)
        if unknown:
            raise AppError(422, "UNKNOWN_FEATURE", f"Unknown features: {', '.join(sorted(unknown))}")
        existing = {f.feature_key: f for f in self.db.scalars(select(PlanFeature).where(PlanFeature.plan_id == plan.id))}
        for key, enabled in features.items():
            row = existing.get(key) or PlanFeature(plan_id=plan.id, feature_key=key)
            row.enabled = bool(enabled)
            self.db.add(row)

    def set_features(self, plan: SubscriptionPlan, features: dict[str, bool], reason: str) -> None:
        before = {f.feature_key: f.enabled for f in self.db.scalars(select(PlanFeature).where(PlanFeature.plan_id == plan.id))}
        self._write_features(plan, features)
        pricing_audit(self.db, self.actor, "PLAN_FEATURES_SET", "plan", plan.id, before, {**before, **features}, reason)
        self.db.commit()

    # ---- commission rules -----------------------------------------------------------------------------------------
    def create_rule(self, scope: str, business_id: str | None, rate: Decimal, min_commission: int, include_pickup_fee: bool,
                    discounts_reduce_basis: bool, effective_from: datetime | None, effective_to: datetime | None,
                    reason: str, commit: bool = True, agreement_id: str | None = None,
                    allow_past: bool = False) -> CommissionRule:
        """`allow_past` is only for the lifecycle job starting a trial at the moment it became due."""
        start = as_utc(effective_from) if effective_from else now_utc()
        end = as_utc(effective_to) if effective_to else None
        if not allow_past and start < now_utc() - timedelta(minutes=5):
            raise AppError(422, "BACKDATED_RULE", "Commission rules cannot start in the past; historical orders keep their terms")
        if end and end <= start:
            raise AppError(422, "INVALID_WINDOW", "The end date must be after the start date")
        rate = Decimal(rate).quantize(Decimal("0.01"))
        if not (Decimal("0") <= rate <= Decimal("50")):
            raise AppError(422, "INVALID_RATE", "Commission must be between 0 % and 50 %")
        if scope == "DEFAULT" and business_id:
            raise AppError(422, "INVALID_SCOPE", "The default rule applies to every laundry")
        if scope == "BUSINESS" and not business_id:
            raise AppError(422, "INVALID_SCOPE", "Choose the laundry")
        if scope == "PROMOTION" and not end:
            raise AppError(422, "PROMOTION_NEEDS_END", "A promotion needs an end date")
        if business_id and not self.db.get(Business, business_id):
            raise not_found("Business")
        same = [CommissionRule.scope == scope,
                CommissionRule.business_id == business_id if business_id else CommissionRule.business_id.is_(None)]
        if scope == "PROMOTION":
            clash = self.db.scalar(select(CommissionRule.id).where(*same, CommissionRule.effective_from < end,
                                   or_(CommissionRule.effective_to.is_(None), CommissionRule.effective_to > start)))
            if clash:
                raise AppError(409, "OVERLAPPING_RULE", "Another promotion overlaps these dates")
            previous = None
        else:
            if self.db.scalar(select(CommissionRule.id).where(*same, CommissionRule.effective_from >= start)):
                raise AppError(409, "OVERLAPPING_RULE", "A rule already starts on or after that date")
            previous = self.db.scalar(select(CommissionRule).where(*same, CommissionRule.effective_from < start,
                                      or_(CommissionRule.effective_to.is_(None), CommissionRule.effective_to > start)))
            if previous:
                previous.effective_to = start  # the old terms stop exactly when the new ones start
        rule = CommissionRule(scope=scope, business_id=business_id, rate=rate, min_commission=min_commission,
                              include_pickup_fee=include_pickup_fee, discounts_reduce_basis=discounts_reduce_basis,
                              effective_from=start, effective_to=end, reason=reason, agreement_id=agreement_id,
                              created_by=self.actor.id if self.actor else None)
        self.db.add(rule)
        self.db.flush()
        pricing_audit(self.db, self.actor, "COMMISSION_RULE_CREATED", "commission_rule", rule.id,
                      snapshot(previous, RULE_FIELDS) if previous else None, snapshot(rule, RULE_FIELDS), reason, business_id)
        if commit:
            self.db.commit()
        return rule

    def end_rule(self, rule: CommissionRule, at: datetime | None, reason: str) -> CommissionRule:
        if rule.agreement_id:
            raise AppError(409, "TRIAL_RULE", "This rate belongs to a Marketplace trial; end or extend the trial instead")
        if rule.scope == "DEFAULT":
            raise AppError(409, "DEFAULT_RULE_REQUIRED", "Replace the default rate with a new one instead of ending it")
        end = max(as_utc(at) if at else now_utc(), now_utc())
        if rule.effective_to and as_utc(rule.effective_to) <= end:
            raise AppError(409, "ALREADY_ENDED", "This rule has already ended")
        before = snapshot(rule, RULE_FIELDS)
        if as_utc(rule.effective_from) >= end:
            rule.effective_to = as_utc(rule.effective_from) + timedelta(seconds=1)  # never started: close immediately
        else:
            rule.effective_to = end
        pricing_audit(self.db, self.actor, "COMMISSION_RULE_ENDED", "commission_rule", rule.id, before,
                      snapshot(rule, RULE_FIELDS), reason, rule.business_id)
        self.db.commit()
        return rule

    # ---- business terms -------------------------------------------------------------------------------------------
    def create_override(self, business_id: str, type_: str, plan_id: str, value: Decimal, effective_from: datetime | None,
                        expires_at: datetime | None, reason: str, pilot_enrollment_id: str | None = None,
                        commit: bool = True) -> CommercialOverride:
        if type_ not in ("COMPLIMENTARY_PLAN", "PLAN_PRICE", "PLAN_DISCOUNT"):
            raise AppError(422, "INVALID_OVERRIDE", "Unknown override type")
        if not self.db.get(Business, business_id):
            raise not_found("Business")
        plan = self.db.get(SubscriptionPlan, plan_id)
        if not plan or plan.status == "RETIRED":
            raise AppError(422, "INVALID_PLAN", "Choose an available plan")
        if type_ == "PLAN_PRICE" and not (Decimal("0") <= value <= Decimal("100000000") and value == value.to_integral_value()):
            raise AppError(422, "INVALID_VALUE", "Price must be whole shillings")
        if type_ == "PLAN_DISCOUNT" and not (Decimal("0") < value <= Decimal("100")):
            raise AppError(422, "INVALID_VALUE", "Discount must be between 0 % and 100 %")
        start = as_utc(effective_from) if effective_from else now_utc()
        end = as_utc(expires_at) if expires_at else None
        if end and end <= start:
            raise AppError(422, "INVALID_WINDOW", "The expiry must be after the start")
        clash = self.db.scalar(select(CommercialOverride.id).where(
            CommercialOverride.business_id == business_id, CommercialOverride.plan_id == plan_id,
            CommercialOverride.revoked_at.is_(None),
            CommercialOverride.type.in_(("COMPLIMENTARY_PLAN",) if type_ == "COMPLIMENTARY_PLAN" else ("PLAN_PRICE", "PLAN_DISCOUNT")),
            or_(CommercialOverride.expires_at.is_(None), CommercialOverride.expires_at > start),
            *([CommercialOverride.effective_from < end] if end else [])))
        if clash:
            raise AppError(409, "OVERLAPPING_OVERRIDE", "This laundry already has terms for this plan in that period")
        override = CommercialOverride(business_id=business_id, type=type_, plan_id=plan_id, value=value, effective_from=start,
                                      expires_at=end, reason=reason, pilot_enrollment_id=pilot_enrollment_id,
                                      created_by=self.actor.id)
        self.db.add(override)
        self.db.flush()
        pricing_audit(self.db, self.actor, "OVERRIDE_CREATED", "override", override.id, None,
                      snapshot(override, OVERRIDE_FIELDS), reason, business_id)
        if commit:
            self.db.commit()
        return override

    def revoke_override(self, override: CommercialOverride, reason: str) -> CommercialOverride:
        if override.revoked_at:
            raise AppError(409, "ALREADY_REVOKED", "Already revoked")
        before = snapshot(override, OVERRIDE_FIELDS)
        override.revoked_at, override.revoked_by = now_utc(), self.actor.id
        pricing_audit(self.db, self.actor, "OVERRIDE_REVOKED", "override", override.id, before,
                      snapshot(override, OVERRIDE_FIELDS), reason, override.business_id)
        self.db.commit()
        return override

    # ---- pilots ---------------------------------------------------------------------------------------------------
    def create_pilot(self, name: str, plan_id: str, duration_days: int, transition_policy: str, notes: str) -> PilotProgram:
        if not self.db.get(SubscriptionPlan, plan_id):
            raise not_found("Plan")
        if transition_policy not in ("DOWNGRADE", "INVOICE"):
            raise AppError(422, "INVALID_POLICY", "Choose DOWNGRADE or INVOICE")
        program = PilotProgram(name=name, plan_id=plan_id, duration_days=duration_days, transition_policy=transition_policy,
                               notes=notes, created_by=self.actor.id)
        self.db.add(program)
        self.db.flush()
        pricing_audit(self.db, self.actor, "PILOT_CREATED", "pilot", program.id, None,
                      {"name": name, "plan_id": plan_id, "duration_days": duration_days, "policy": transition_policy}, notes)
        self.db.commit()
        return program

    def enroll(self, program: PilotProgram, business_id: str, starts_at: datetime | None) -> PilotEnrollment:
        if program.status != "ACTIVE":
            raise AppError(409, "PILOT_CLOSED", "This pilot is closed")
        if self.db.scalar(select(PilotEnrollment.id).where(PilotEnrollment.program_id == program.id,
                                                          PilotEnrollment.business_id == business_id)):
            raise AppError(409, "ALREADY_ENROLLED", "This laundry is already in the pilot")
        start = as_utc(starts_at) if starts_at else now_utc()
        enrollment = PilotEnrollment(program_id=program.id, business_id=business_id, starts_at=start,
                                     ends_at=start + timedelta(days=program.duration_days), enrolled_by=self.actor.id)
        self.db.add(enrollment)
        self.db.flush()
        # Pilot access is a complimentary plan for the pilot's dates. Marketplace listing is NOT touched.
        self.create_override(business_id, "COMPLIMENTARY_PLAN", program.plan_id, Decimal("0"), start, enrollment.ends_at,
                             f"Pilot: {program.name}", pilot_enrollment_id=enrollment.id, commit=False)
        self.db.commit()
        return enrollment

    def remove_enrollment(self, enrollment: PilotEnrollment, reason: str) -> None:
        override = self.db.scalar(select(CommercialOverride).where(CommercialOverride.pilot_enrollment_id == enrollment.id,
                                                                  CommercialOverride.revoked_at.is_(None)))
        enrollment.status = "REMOVED"
        if override:
            self.revoke_override(override, reason)
        else:
            self.db.commit()

    def current_subscriptions_for_plan(self, plan_id: str) -> int:
        return len(list(self.db.scalars(select(BusinessSubscription.id).where(BusinessSubscription.plan_id == plan_id,
                                                                              BusinessSubscription.ended_at.is_(None)))))
