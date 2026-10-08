"""Admin → Marketplace: rollout, enrolment, review, trials and activation.

Any admin may review applications, invite, activate, suspend and reactivate (operations). Anything that changes
money — Marketplace settings, individual trial terms, granting, extending or ending trials — needs SUPER_ADMIN or
FINANCE_ADMIN.
"""
import json
from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session, aliased, selectinload

from ..core.errors import AppError
from ..database import get_db
from ..dependencies import require_admin, require_pricing_admin, require_pricing_role
from ..domain import order_states as S
from ..domain.clock import now_utc
from ..domain.periods import local_midnight
from ..models import (
    Business,
    Commission,
    CommissionRule,
    MarketplaceAccount,
    MarketplaceAgreement,
    Order,
    PlatformSetting,
    Service,
    User,
)
from ..schemas.admin import CohortSet, MarketplaceDecision, MarketplaceInvite, MarketplaceSettingsUpdate, TrialExtend, TrialGrant
from ..schemas.billing import ReasonOnly
from ..services.billing import business_or_404
from ..services.commission import CommissionService, commission_terms
from ..services.marketplace import hours_out
from ..services.marketplace_program import MARKETPLACE_SETTINGS, MarketplaceProgram, account_or_404
from ..services.pricing import PricingAdmin
from .common import Page, page_params, paginate

router = APIRouter(prefix="/admin/marketplace", tags=["Admin marketplace"], dependencies=[Depends(require_admin)])


# ---- settings --------------------------------------------------------------------------------------------------------
@router.get("/settings")
def settings_list(db: Session = Depends(get_db)):
    rows = {r.key: r for r in db.scalars(select(PlatformSetting).where(PlatformSetting.key.in_(MARKETPLACE_SETTINGS)))}
    out = []
    for key, (_, label, default) in MARKETPLACE_SETTINGS.items():
        row = rows.get(key)
        out.append({"key": key, "label": label, "value": json.loads(row.value_json) if row else default,
                    "updated_at": row.updated_at if row else None})
    # The standard rate for a laundry without its own terms (a promotion for all, else the default rule).
    standard = CommissionService(db).rule_for("", include_trials=False)
    return {"settings": out, "standard_commission": {"rule_id": standard.id, **commission_terms(standard)}}


@router.put("/settings")
def settings_update(payload: MarketplaceSettingsUpdate, db: Session = Depends(get_db),
                    actor: User = Depends(require_pricing_admin)):
    """Several settings in one transaction with one reason. New values apply to new grants and decisions only;
    agreements already made keep their terms. Opening the Marketplace starts waiting trials straight away."""
    admin = PricingAdmin(db, actor)
    for key, value in payload.values.items():
        if key not in MARKETPLACE_SETTINGS:
            raise AppError(404, "NOT_FOUND", f"Unknown setting {key}")
        admin.set_setting(key, value, payload.reason, commit=False)
    db.commit()
    MarketplaceProgram(db).run()
    return settings_list(db)


@router.post("/lifecycle/run")
def run_lifecycle(db: Session = Depends(get_db), _: User = Depends(require_pricing_admin)):
    """Start waiting trials, send reminders and end trials now (it also runs on the billing timer)."""
    return MarketplaceProgram(db).run()


# ---- overview --------------------------------------------------------------------------------------------------------
@router.get("/overview")
def overview(start: date | None = None, end: date | None = None, db: Session = Depends(get_db)):
    today = now_utc().date()
    start, end = start or today.replace(day=1), end or today
    if end < start or (end - start).days > 366:
        raise AppError(422, "INVALID_PERIOD", "Choose a range of at most a year")
    lo, hi = local_midnight(start), local_midnight(end + timedelta(days=1))
    now = now_utc()
    by_status = dict(db.execute(select(MarketplaceAccount.status, func.count()).group_by(MarketplaceAccount.status)).all())

    trial = MarketplaceAgreement
    ended = list(db.scalars(select(trial).where(trial.kind == "TRIAL", trial.status == "ENDED")))
    converted = sum(1 for t in ended if _converted(db, t))
    expiring = list(db.execute(select(trial, Business.name).join(Business, Business.id == trial.business_id).where(
        trial.kind == "TRIAL", trial.status == "ACTIVE", trial.ends_at <= now + timedelta(days=30)).order_by(trial.ends_at)))
    program = MarketplaceProgram(db)

    live = Order.status.notin_([S.CANCELLED, S.REJECTED])
    gmv, mp_orders = db.execute(select(func.coalesce(func.sum(Order.total), 0), func.count(Order.id)).where(
        Order.source == "MARKETPLACE", live, Order.created_at >= lo, Order.created_at < hi)).one()
    is_trial = CommissionRule.agreement_id.is_not(None)
    ledger = db.execute(select(
        func.coalesce(func.sum(case((Commission.entry_type == "EARNED", Commission.amount), else_=0)), 0),
        func.coalesce(func.sum(case((Commission.entry_type == "REVERSED", Commission.amount), else_=0)), 0),
        func.coalesce(func.sum(Commission.amount), 0),
        func.coalesce(func.sum(case((is_trial, Commission.amount), else_=0)), 0),
        func.coalesce(func.sum(case((is_trial, 0), else_=Commission.amount)), 0),
        func.coalesce(func.sum(Commission.waived_amount), 0),
    ).outerjoin(CommissionRule, CommissionRule.id == Commission.rule_id).where(
        Commission.created_at >= lo, Commission.created_at < hi)).one()
    return {
        "start": start.isoformat(), "end": end.isoformat(), "mode": program.policy["mode"],
        "by_status": by_status,
        "applications_pending": by_status.get("PENDING_REVIEW", 0),
        "invited": by_status.get("INVITED", 0),
        "approved": sum(by_status.get(s, 0) for s in ("APPROVED", "TRIAL_ACTIVE", "ACTIVE", "TRIAL_EXPIRED", "SUSPENDED")),
        "waiting_to_start": db.scalar(select(func.count(trial.id)).where(trial.kind == "TRIAL", trial.status == "PENDING_START")),
        "active_trials": by_status.get("TRIAL_ACTIVE", 0),
        "active_providers": by_status.get("ACTIVE", 0) + by_status.get("TRIAL_ACTIVE", 0),
        "trial_expired": by_status.get("TRIAL_EXPIRED", 0),
        "suspended": by_status.get("SUSPENDED", 0),
        "trials_ended": len(ended), "trials_converted": converted,
        "conversion_rate": round(converted / len(ended), 4) if ended else None,
        "expiring": [{"business_id": t.business_id, "business_name": name, "ends_at": t.ends_at,
                      "days_left": program.agreement_out(t, now)["days_left"],
                      "accepted": bool(_account(db, t.business_id).post_trial_accepted_at)} for t, name in expiring],
        "marketplace_orders": mp_orders, "gmv": int(gmv),
        "commission": {"earned": int(ledger[0]), "reversed": int(ledger[1]), "net": int(ledger[2]),
                       "trial": int(ledger[3]), "standard": int(ledger[4]), "waived": int(ledger[5])},
    }


def _account(db: Session, business_id: str) -> MarketplaceAccount:
    return db.scalar(select(MarketplaceAccount).where(MarketplaceAccount.business_id == business_id))


def _converted(db: Session, t: MarketplaceAgreement) -> bool:
    return bool(db.scalar(select(MarketplaceAgreement.id).where(
        MarketplaceAgreement.business_id == t.business_id, MarketplaceAgreement.kind == "STANDARD",
        MarketplaceAgreement.version > t.version)))


# ---- providers -------------------------------------------------------------------------------------------------------
def _row(db: Session, program: MarketplaceProgram, account: MarketplaceAccount) -> dict:
    b = account.business
    agreement = program.open_agreement(b.id)
    checklist = program.readiness(b, account)
    return {"business_id": b.id, "business_name": b.name, "slug": b.slug, "area": b.area, "status": account.status,
            "review_status": account.review_status, "commercial_status": account.commercial_status,
            "listing_status": account.listing_status, "launch_cohort": account.launch_cohort,
            "ready": sum(1 for c in checklist if c["done"]), "checks": len(checklist),
            "accepting_orders": program.accepting_orders(account, b),
            "agreement": program.agreement_out(agreement), "submitted_at": account.submitted_at,
            "invited_at": account.invited_at, "approved_at": account.approved_at,
            "post_trial_accepted": account.post_trial_accepted_at is not None, "status_reason": account.status_reason,
            "rejection_reason": account.rejection_reason}


@router.get("/providers")
def providers(status: str | None = Query(None, max_length=20), q: str | None = Query(None, max_length=80),
              include_not_enrolled: bool = False, page: Page = Depends(page_params), db: Session = Depends(get_db)):
    stmt = (select(MarketplaceAccount).join(Business, Business.id == MarketplaceAccount.business_id)
            .options(selectinload(MarketplaceAccount.business))
            .order_by(case((MarketplaceAccount.status == "PENDING_REVIEW", 0), else_=1),
                      MarketplaceAccount.submitted_at.desc().nulls_last(), Business.name))
    if status:
        stmt = stmt.where(MarketplaceAccount.status == status)
    elif not include_not_enrolled:
        stmt = stmt.where(MarketplaceAccount.status != "NOT_ENROLLED")
    if q:
        stmt = stmt.where(or_(Business.name.ilike(f"%{q}%"), Business.area.ilike(f"%{q}%")))
    program = MarketplaceProgram(db)
    return paginate(db, stmt, page, lambda a: _row(db, program, a))


@router.get("/providers/{business_id}")
def provider(business_id: str, db: Session = Depends(get_db)):
    business = business_or_404(db, business_id)
    program = MarketplaceProgram(db)
    account = program.account(business.id)
    services = db.scalars(select(Service).where(Service.business_id == business.id, Service.active.is_(True))
                          .order_by(Service.sort_order, Service.name))
    agreements = program.agreements(business.id)
    last_trial = next((a for a in agreements if a.kind == "TRIAL" and a.starts_at), None)
    return {**_row(db, program, account),
            "business": {"description": business.description, "phone": business.phone, "address": business.address,
                         "latitude": business.latitude, "longitude": business.longitude, "status": business.status,
                         "pickup_enabled": business.pickup_enabled, "pickup_fee": business.pickup_fee,
                         "hours": hours_out(business.hours)},
            "application": {"contact_name": account.contact_name, "registration_number": account.registration_number,
                            "tin": account.tin, "pickup_radius_km": float(account.pickup_radius_km or 0),
                            "terms_accepted_at": account.terms_accepted_at, "invitation_note": account.invitation_note},
            "services": [{"name": s.name, "price": s.price, "pricing_model": s.pricing_model} for s in services],
            "checklist": program.readiness(business, account),
            "commission": commission_terms(CommissionService(db).rule_for(business.id)),
            "standard_terms": program.standard_terms(business.id), "trial_offer": program.trial_offer(business.id),
            "agreements": [program.agreement_out(a) for a in agreements],
            "trial_stats": program.trial_stats(business.id, last_trial),
            "history": program.history(business.id)}


ACTIONS = Literal["approve", "reject", "request-changes", "activate", "suspend", "reactivate"]


def apply_decision(db: Session, actor: User, account: MarketplaceAccount, action: str, payload: MarketplaceDecision):
    if payload.commission_rate is not None or payload.trial_days is not None or payload.trial_rate is not None \
            or payload.skip_trial:
        require_pricing_role(actor)
    program = MarketplaceProgram(db, actor)
    reason = (payload.reason or "").strip()
    if action == "approve":
        if payload.commission_rate is not None:
            from decimal import Decimal

            PricingAdmin(db, actor).create_rule("BUSINESS", account.business_id, Decimal(str(payload.commission_rate)), 0,
                                                False, True, None, None, "Set on approval", commit=False)
        return program.approve(account, reason, payload.trial_days, payload.trial_rate, payload.skip_trial)
    if action == "reject":
        return program.reject(account, reason)
    if action == "request-changes":
        return program.request_changes(account, reason)
    if action == "activate":
        return program.activate(account, reason)
    if action == "suspend":
        return program.suspend(account, reason)
    return program.reactivate(account, reason)


@router.post("/providers/{business_id}/invite")
def invite(business_id: str, payload: MarketplaceInvite, db: Session = Depends(get_db), actor: User = Depends(require_admin)):
    if payload.trial_days is not None or payload.trial_rate is not None:
        require_pricing_role(actor)
    business = business_or_404(db, business_id)
    MarketplaceProgram(db, actor).invite(business, payload.note, payload.trial_days, payload.trial_rate, payload.launch_cohort)
    return provider(business_id, db)


@router.post("/providers/{business_id}/cohort")
def cohort(business_id: str, payload: CohortSet, db: Session = Depends(get_db), actor: User = Depends(require_admin)):
    MarketplaceProgram(db, actor).set_launch_cohort(account_or_404(db, business_id), payload.included, payload.reason)
    return provider(business_id, db)


@router.post("/providers/{business_id}/trial/grant")
def grant_trial(business_id: str, payload: TrialGrant, db: Session = Depends(get_db),
                actor: User = Depends(require_pricing_admin)):
    MarketplaceProgram(db, actor).grant_trial(account_or_404(db, business_id), payload.reason, payload.days, payload.rate)
    return provider(business_id, db)


@router.post("/providers/{business_id}/trial/extend")
def extend_trial(business_id: str, payload: TrialExtend, db: Session = Depends(get_db),
                 actor: User = Depends(require_pricing_admin)):
    MarketplaceProgram(db, actor).extend_trial(account_or_404(db, business_id), payload.days, payload.reason)
    return provider(business_id, db)


@router.post("/providers/{business_id}/trial/end")
def end_trial(business_id: str, payload: ReasonOnly, db: Session = Depends(get_db),
              actor: User = Depends(require_pricing_admin)):
    MarketplaceProgram(db, actor).end_trial(account_or_404(db, business_id), payload.reason)
    return provider(business_id, db)


# Declared after the specific routes above so /invite, /cohort and /trial/* are matched first.
@router.post("/providers/{business_id}/{action}")
def decide(business_id: str, action: ACTIONS, payload: MarketplaceDecision, db: Session = Depends(get_db),
           actor: User = Depends(require_admin)):
    account = apply_decision(db, actor, account_or_404(db, business_id), action, payload)
    return provider(account.business_id, db)


# ---- trials ----------------------------------------------------------------------------------------------------------
@router.get("/trials")
def trials(bucket: Literal["active", "waiting", "expiring", "converted", "expired"] = "active",
           within_days: int = Query(14, ge=1, le=365), db: Session = Depends(get_db)):
    t = MarketplaceAgreement
    now = now_utc()
    stmt = select(t, Business.name).join(Business, Business.id == t.business_id).where(t.kind == "TRIAL")
    if bucket == "active":
        stmt = stmt.where(t.status == "ACTIVE").order_by(t.ends_at)
    elif bucket == "waiting":
        stmt = stmt.where(t.status == "PENDING_START").order_by(t.created_at)
    elif bucket == "expiring":
        stmt = stmt.where(t.status == "ACTIVE", t.ends_at <= now + timedelta(days=within_days)).order_by(t.ends_at)
    else:
        later = aliased(MarketplaceAgreement)
        has_standard = select(later.id).where(later.business_id == t.business_id, later.kind == "STANDARD",
                                              later.version > t.version).exists()
        stmt = stmt.where(t.status == "ENDED", has_standard if bucket == "converted" else ~has_standard) \
            .order_by(t.ends_at.desc())
    program = MarketplaceProgram(db)
    rows = list(db.execute(stmt.limit(200)))
    return [{"business_id": a.business_id, "business_name": name, "status": _account(db, a.business_id).status,
             "post_trial_accepted": _account(db, a.business_id).post_trial_accepted_at is not None,
             "agreement": program.agreement_out(a, now), "stats": program.trial_stats(a.business_id, a)}
            for a, name in rows]

