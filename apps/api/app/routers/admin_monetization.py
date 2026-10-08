"""Admin → Monetization. Reading needs any admin role; changing anything needs SUPER_ADMIN or FINANCE_ADMIN."""
import json
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..core.errors import AppError, not_found
from ..database import get_db
from ..dependencies import require_admin, require_pricing_admin
from ..domain.clock import as_utc, now_utc
from ..domain.features import FEATURES
from ..domain.periods import local_midnight
from ..models import (
    Business,
    BusinessSubscription,
    CommercialOverride,
    CommissionRule,
    PilotEnrollment,
    PilotProgram,
    PlanPrice,
    PlatformSetting,
    PricingAuditLog,
    SubscriptionInvoice,
    SubscriptionPlan,
    User,
)
from ..schemas.billing import (
    AdminSubscriptionAssign,
    FeaturesSet,
    OverrideCreate,
    PilotCreate,
    PilotEnroll,
    PlanCreate,
    PlanUpdate,
    PriceSet,
    ReasonOnly,
    RuleCreate,
    RuleEnd,
    SettingSet,
    SubscriptionPaymentCreate,
)
from ..services.billing import BillingService, business_or_404
from ..services.billing_views import plan_card
from ..services.commission import CommissionService
from ..services.entitlements import resolve
from ..services.pricing import SETTINGS, PricingAdmin, price_in_force
from .common import Page, page_params, paginate

router = APIRouter(prefix="/admin/monetization", tags=["Admin monetization"], dependencies=[Depends(require_admin)])


def _get(db: Session, model, id_: str, label: str):
    row = db.get(model, id_)
    if not row:
        raise not_found(label)
    return row


def _business_names(db: Session, ids) -> dict[str, str]:
    ids = {i for i in ids if i}
    return dict(db.execute(select(Business.id, Business.name).where(Business.id.in_(ids))).all()) if ids else {}


# ---- overview --------------------------------------------------------------------------------------------------------
@router.get("/revenue")
def revenue(start: date | None = None, end: date | None = None, db: Session = Depends(get_db)):
    """Revenue for a date range (local dates, inclusive). Defaults to this month so far."""
    today = now_utc().date()
    start = start or today.replace(day=1)
    end = end or today
    if end < start or (end - start).days > 366:
        raise AppError(422, "INVALID_PERIOD", "Choose a range of at most a year")
    return {"start": start.isoformat(), "end": end.isoformat(),
            **BillingService(db).revenue(local_midnight(start), local_midnight(end + timedelta(days=1)))}


@router.get("/features")
def features():
    return [{"key": k, "label": v} for k, v in FEATURES.items()]


# ---- plans ------------------------------------------------------------------------------------------------------------
def _plan_out(db: Session, plan: SubscriptionPlan) -> dict:
    history = [{"id": p.id, "interval": p.interval, "amount": p.amount, "effective_from": p.effective_from,
                "effective_to": p.effective_to} for p in db.scalars(
        select(PlanPrice).where(PlanPrice.plan_id == plan.id).order_by(PlanPrice.interval, PlanPrice.effective_from))]
    current_prices = {i: (price_in_force(db, plan.id, i).amount if price_in_force(db, plan.id, i) else None)
                      for i in ("MONTHLY", "ANNUAL")}
    subscribers = db.scalar(select(func.count()).where(BusinessSubscription.plan_id == plan.id,
                                                       BusinessSubscription.ended_at.is_(None))) or 0
    return {**plan_card(db, plan), "code": plan.code, "status": plan.status, "is_default": plan.is_default,
            "grace_days": plan.grace_days, "sort_order": plan.sort_order, "current_prices": current_prices,
            "price_history": history, "subscribers": subscribers}


@router.get("/plans")
def plans(db: Session = Depends(get_db)):
    return [_plan_out(db, p) for p in db.scalars(select(SubscriptionPlan).order_by(SubscriptionPlan.sort_order))]


@router.post("/plans", status_code=201)
def create_plan(payload: PlanCreate, db: Session = Depends(get_db), actor: User = Depends(require_pricing_admin)):
    data = payload.model_dump(exclude={"monthly_price", "annual_price", "features", "reason"})
    plan = PricingAdmin(db, actor).create_plan(data, {"MONTHLY": payload.monthly_price, "ANNUAL": payload.annual_price},
                                               payload.features, payload.reason)
    return _plan_out(db, plan)


@router.patch("/plans/{plan_id}")
def update_plan(plan_id: str, payload: PlanUpdate, db: Session = Depends(get_db), actor: User = Depends(require_pricing_admin)):
    plan = _get(db, SubscriptionPlan, plan_id, "Plan")
    changes = payload.model_dump(exclude_unset=True, exclude={"reason"})
    return _plan_out(db, PricingAdmin(db, actor).update_plan(plan, changes, payload.reason))


@router.post("/plans/{plan_id}/prices", status_code=201)
def set_price(plan_id: str, payload: PriceSet, db: Session = Depends(get_db), actor: User = Depends(require_pricing_admin)):
    plan = _get(db, SubscriptionPlan, plan_id, "Plan")
    PricingAdmin(db, actor).set_price(plan, payload.interval, payload.amount, payload.effective_from, payload.reason)
    return _plan_out(db, plan)


@router.put("/plans/{plan_id}/features")
def set_features(plan_id: str, payload: FeaturesSet, db: Session = Depends(get_db), actor: User = Depends(require_pricing_admin)):
    plan = _get(db, SubscriptionPlan, plan_id, "Plan")
    PricingAdmin(db, actor).set_features(plan, payload.features, payload.reason)
    return _plan_out(db, plan)


# ---- marketplace commission ------------------------------------------------------------------------------------------
def _rule_out(r: CommissionRule, names: dict[str, str]) -> dict:
    now = now_utc()
    state = "SCHEDULED" if as_utc(r.effective_from) > now else (
        "ENDED" if r.effective_to and as_utc(r.effective_to) <= now else "IN_FORCE")
    return {"id": r.id, "scope": r.scope, "business_id": r.business_id, "business_name": names.get(r.business_id),
            "rate": float(r.rate), "min_commission": r.min_commission, "include_pickup_fee": r.include_pickup_fee,
            "discounts_reduce_basis": r.discounts_reduce_basis, "effective_from": r.effective_from,
            "effective_to": r.effective_to, "reason": r.reason, "state": state, "created_at": r.created_at}


@router.get("/commission/rules")
def rules(scope: str | None = Query(None, max_length=10), business_id: str | None = Query(None, max_length=36),
          db: Session = Depends(get_db)):
    stmt = select(CommissionRule).order_by(CommissionRule.scope, CommissionRule.effective_from.desc())
    if scope:
        stmt = stmt.where(CommissionRule.scope == scope)
    if business_id:
        stmt = stmt.where(CommissionRule.business_id == business_id)
    rows = list(db.scalars(stmt))
    names = _business_names(db, (r.business_id for r in rows))
    return [_rule_out(r, names) for r in rows]


@router.post("/commission/rules", status_code=201)
def create_rule(payload: RuleCreate, db: Session = Depends(get_db), actor: User = Depends(require_pricing_admin)):
    rule = PricingAdmin(db, actor).create_rule(payload.scope, payload.business_id, payload.rate, payload.min_commission,
                                               payload.include_pickup_fee, payload.discounts_reduce_basis,
                                               payload.effective_from, payload.effective_to, payload.reason)
    return _rule_out(rule, _business_names(db, [rule.business_id]))


@router.post("/commission/rules/{rule_id}/end")
def end_rule(rule_id: str, payload: RuleEnd, db: Session = Depends(get_db), actor: User = Depends(require_pricing_admin)):
    rule = PricingAdmin(db, actor).end_rule(_get(db, CommissionRule, rule_id, "Rule"), payload.at, payload.reason)
    return _rule_out(rule, _business_names(db, [rule.business_id]))


@router.get("/commission/preview")
def commission_preview(business_id: str = Query(max_length=36), services: int = Query(30000, ge=0, le=100_000_000),
                       discount: int = Query(0, ge=0), pickup_fee: int = Query(0, ge=0), db: Session = Depends(get_db)):
    """What a Marketplace order placed now would be charged — the calculation admins and providers can check."""
    business_or_404(db, business_id)
    rule = CommissionService(db).rule_for(business_id)
    calc = CommissionService.calculate(rule, services, discount, pickup_fee)
    return {"rule": _rule_out(rule, _business_names(db, [rule.business_id])), "basis": calc.basis, "commission": calc.amount,
            "laundry_amount": calc.laundry_amount, "detail": calc.detail}


# ---- settings --------------------------------------------------------------------------------------------------------
@router.get("/settings")
def settings_list(db: Session = Depends(get_db)):
    rows = {r.key: r for r in db.scalars(select(PlatformSetting))}
    return [{"key": k, "label": label, "value": json.loads(rows[k].value_json) if k in rows else None,
             "updated_at": rows[k].updated_at if k in rows else None} for k, (_, label) in SETTINGS.items()]


@router.put("/settings/{key}")
def settings_set(key: str, payload: SettingSet, db: Session = Depends(get_db), actor: User = Depends(require_pricing_admin)):
    PricingAdmin(db, actor).set_setting(key, payload.value, payload.reason)
    return settings_list(db)


# ---- business terms --------------------------------------------------------------------------------------------------
def _override_out(o: CommercialOverride, names: dict[str, str], plans: dict[str, str]) -> dict:
    now = now_utc()
    state = "REVOKED" if o.revoked_at else "SCHEDULED" if as_utc(o.effective_from) > now else (
        "EXPIRED" if o.expires_at and as_utc(o.expires_at) <= now else "IN_FORCE")
    return {"id": o.id, "business_id": o.business_id, "business_name": names.get(o.business_id), "type": o.type,
            "plan_id": o.plan_id, "plan_name": plans.get(o.plan_id), "value": float(o.value),
            "effective_from": o.effective_from, "expires_at": o.expires_at, "reason": o.reason, "state": state,
            "pilot": o.pilot_enrollment_id is not None, "created_at": o.created_at, "revoked_at": o.revoked_at}


@router.get("/overrides")
def overrides(business_id: str | None = Query(None, max_length=36), include_ended: bool = False, db: Session = Depends(get_db)):
    stmt = select(CommercialOverride).order_by(CommercialOverride.created_at.desc())
    if business_id:
        stmt = stmt.where(CommercialOverride.business_id == business_id)
    if not include_ended:
        stmt = stmt.where(CommercialOverride.revoked_at.is_(None),
                          or_(CommercialOverride.expires_at.is_(None), CommercialOverride.expires_at > now_utc()))
    rows = list(db.scalars(stmt))
    plans = dict(db.execute(select(SubscriptionPlan.id, SubscriptionPlan.name)).all())
    return [_override_out(o, _business_names(db, (x.business_id for x in rows)), plans) for o in rows]


@router.post("/overrides", status_code=201)
def create_override(payload: OverrideCreate, db: Session = Depends(get_db), actor: User = Depends(require_pricing_admin)):
    start = as_utc(payload.effective_from) if payload.effective_from else now_utc()
    expires = payload.expires_at or (start + timedelta(days=payload.days) if payload.days else None)
    o = PricingAdmin(db, actor).create_override(payload.business_id, payload.type, payload.plan_id, payload.value, start,
                                                expires, payload.reason)
    return _override_out(o, _business_names(db, [o.business_id]), {o.plan_id: db.get(SubscriptionPlan, o.plan_id).name})


@router.post("/overrides/{override_id}/revoke")
def revoke_override(override_id: str, payload: ReasonOnly, db: Session = Depends(get_db),
                    actor: User = Depends(require_pricing_admin)):
    o = PricingAdmin(db, actor).revoke_override(_get(db, CommercialOverride, override_id, "Override"), payload.reason)
    return _override_out(o, _business_names(db, [o.business_id]), {o.plan_id: db.get(SubscriptionPlan, o.plan_id).name})


# ---- pilots ----------------------------------------------------------------------------------------------------------
def _pilot_out(db: Session, p: PilotProgram) -> dict:
    enrollments = list(db.scalars(select(PilotEnrollment).where(PilotEnrollment.program_id == p.id)
                                  .order_by(PilotEnrollment.ends_at)))
    names = _business_names(db, (e.business_id for e in enrollments))
    return {"id": p.id, "name": p.name, "plan_id": p.plan_id, "plan_name": db.get(SubscriptionPlan, p.plan_id).name,
            "duration_days": p.duration_days, "transition_policy": p.transition_policy, "status": p.status, "notes": p.notes,
            "enrollments": [{"id": e.id, "business_id": e.business_id, "business_name": names.get(e.business_id),
                             "starts_at": e.starts_at, "ends_at": e.ends_at, "status": e.status} for e in enrollments]}


@router.get("/pilots")
def pilots(db: Session = Depends(get_db)):
    return [_pilot_out(db, p) for p in db.scalars(select(PilotProgram).order_by(PilotProgram.created_at.desc()))]


@router.post("/pilots", status_code=201)
def create_pilot(payload: PilotCreate, db: Session = Depends(get_db), actor: User = Depends(require_pricing_admin)):
    p = PricingAdmin(db, actor).create_pilot(payload.name, payload.plan_id, payload.duration_days, payload.transition_policy,
                                             payload.notes)
    return _pilot_out(db, p)


@router.post("/pilots/{pilot_id}/enrollments")
def enroll(pilot_id: str, payload: PilotEnroll, db: Session = Depends(get_db), actor: User = Depends(require_pricing_admin)):
    program = _get(db, PilotProgram, pilot_id, "Pilot")
    admin = PricingAdmin(db, actor)
    for business_id in payload.business_ids:
        business_or_404(db, business_id)
        admin.enroll(program, business_id, payload.starts_at)
    return _pilot_out(db, program)


@router.post("/pilots/{pilot_id}/enrollments/{enrollment_id}/remove")
def remove_enrollment(pilot_id: str, enrollment_id: str, payload: ReasonOnly, db: Session = Depends(get_db),
                      actor: User = Depends(require_pricing_admin)):
    enrollment = _get(db, PilotEnrollment, enrollment_id, "Enrollment")
    if enrollment.program_id != pilot_id or enrollment.status != "ACTIVE":
        raise AppError(409, "NOT_ACTIVE", "This enrollment is not active")
    PricingAdmin(db, actor).remove_enrollment(enrollment, payload.reason)
    return _pilot_out(db, _get(db, PilotProgram, pilot_id, "Pilot"))


@router.post("/pilots/{pilot_id}/close")
def close_pilot(pilot_id: str, payload: ReasonOnly, db: Session = Depends(get_db), actor: User = Depends(require_pricing_admin)):
    program = _get(db, PilotProgram, pilot_id, "Pilot")
    program.status = "CLOSED"  # existing enrollments run to their end date; no new ones
    from ..services.pricing import pricing_audit

    pricing_audit(db, actor, "PILOT_CLOSED", "pilot", program.id, {"status": "ACTIVE"}, {"status": "CLOSED"}, payload.reason)
    db.commit()
    return _pilot_out(db, program)


# ---- subscriptions, invoices, payments -------------------------------------------------------------------------------
@router.get("/businesses")
def businesses_commercial(q: str | None = Query(None, max_length=80), page: Page = Depends(page_params),
                          db: Session = Depends(get_db)):
    stmt = select(Business).order_by(Business.name)
    if q:
        stmt = stmt.where(Business.name.ilike(f"%{q}%"))

    def row(b: Business) -> dict:
        eff = resolve(db, b.id)
        sub = eff.subscription
        rule = CommissionService(db).rule_for(b.id)
        return {"id": b.id, "name": b.name, "area": b.area, "plan": eff.plan.name, "source": eff.source,
                "access_until": eff.ends_at, "subscription_status": sub.status if sub else None,
                "price": sub.price_amount if sub else 0, "interval": sub.interval if sub else None,
                "commission_rate": float(rule.rate), "commission_scope": rule.scope,
                "marketplace_status": b.marketplace.status if b.marketplace else "NOT_ENROLLED"}
    return paginate(db, stmt, page, row)


@router.post("/businesses/{business_id}/subscription")
def assign_plan(business_id: str, payload: AdminSubscriptionAssign, db: Session = Depends(get_db),
                actor: User = Depends(require_pricing_admin)):
    business = business_or_404(db, business_id)
    plan = _get(db, SubscriptionPlan, payload.plan_id, "Plan")
    sub = BillingService(db).change_plan(business, plan, payload.interval, actor, "ADMIN", payload.reason)
    return {"subscription_id": sub.id, "status": sub.status, "plan": plan.name, "price": sub.price_amount}


@router.get("/invoices")
def invoices(status: str | None = Query(None, max_length=8), business_id: str | None = Query(None, max_length=36),
             page: Page = Depends(page_params), db: Session = Depends(get_db)):
    stmt = select(SubscriptionInvoice).order_by(SubscriptionInvoice.issued_at.desc())
    if status:
        stmt = stmt.where(SubscriptionInvoice.status == status)
    if business_id:
        stmt = stmt.where(SubscriptionInvoice.business_id == business_id)
    billing = BillingService(db)
    result = paginate(db, stmt, page, lambda i: billing.invoice_out(i, with_lines=False))
    names = _business_names(db, (i["business_id"] for i in result["items"]))
    for item in result["items"]:
        item["business_name"] = names.get(item["business_id"])
    return result


@router.get("/invoices/{invoice_id}")
def invoice(invoice_id: str, db: Session = Depends(get_db)):
    inv = _get(db, SubscriptionInvoice, invoice_id, "Invoice")
    return {**BillingService(db).invoice_out(inv), "business_name": db.get(Business, inv.business_id).name}


@router.post("/invoices/{invoice_id}/payments", status_code=201)
def record_payment(invoice_id: str, payload: SubscriptionPaymentCreate, db: Session = Depends(get_db),
                   actor: User = Depends(require_pricing_admin),
                   idempotency_key: str | None = Header(None, alias="Idempotency-Key", max_length=64)):
    inv = _get(db, SubscriptionInvoice, invoice_id, "Invoice")
    BillingService(db).record_payment(inv, payload.amount, payload.method, payload.reference.strip() or None,
                                      payload.received_at, actor, idempotency_key, payload.note)
    db.refresh(inv)
    return BillingService(db).invoice_out(inv)


@router.post("/invoices/{invoice_id}/void")
def void_invoice(invoice_id: str, payload: ReasonOnly, db: Session = Depends(get_db), actor: User = Depends(require_pricing_admin)):
    inv = BillingService(db).void_invoice(_get(db, SubscriptionInvoice, invoice_id, "Invoice"), actor, payload.reason)
    return BillingService(db).invoice_out(inv)


@router.post("/billing/run")
def run_billing(db: Session = Depends(get_db), actor: User = Depends(require_pricing_admin)):
    """Process renewals, trial and pilot ends and overdue invoices now (it also runs on a timer)."""
    return BillingService(db).run()


# ---- audit -----------------------------------------------------------------------------------------------------------
@router.get("/audit")
def audit_history(business_id: str | None = Query(None, max_length=36), entity: str | None = Query(None, max_length=40),
                  page: Page = Depends(page_params), db: Session = Depends(get_db)):
    stmt = select(PricingAuditLog).order_by(PricingAuditLog.created_at.desc())
    if business_id:
        stmt = stmt.where(PricingAuditLog.business_id == business_id)
    if entity:
        stmt = stmt.where(PricingAuditLog.entity == entity)
    result = paginate(db, stmt, page, lambda a: {
        "id": a.id, "action": a.action, "entity": a.entity, "entity_id": a.entity_id, "business_id": a.business_id,
        "before": json.loads(a.before_json) if a.before_json else None, "after": json.loads(a.after_json) if a.after_json else None,
        "reason": a.reason, "actor_id": a.actor_id, "created_at": a.created_at})
    names = _business_names(db, (i["business_id"] for i in result["items"]))
    actor_ids = {i["actor_id"] for i in result["items"] if i["actor_id"]}
    actors = dict(db.execute(select(User.id, User.email).where(User.id.in_(actor_ids))).all()) if actor_ids else {}
    for item in result["items"]:
        item["business_name"] = names.get(item["business_id"])
        item["actor"] = actors.get(item.pop("actor_id"), "system")
    return result

