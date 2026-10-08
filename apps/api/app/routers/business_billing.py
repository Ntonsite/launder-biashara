from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.errors import AppError, not_found
from ..database import get_db
from ..dependencies import BusinessContext, business_context
from ..domain.clock import now_utc
from ..models import BusinessSubscription, SubscriptionInvoice, SubscriptionPlan
from ..schemas.billing import PlanChange
from ..services.billing import BillingService
from ..services.billing_views import subscription_view
from ..services.entitlements import current_subscription

router = APIRouter(prefix="/business", tags=["Business billing"])


def _plan(db: Session, plan_id: str) -> SubscriptionPlan:
    plan = db.get(SubscriptionPlan, plan_id)
    if not plan or plan.status != "ACTIVE":
        raise AppError(404, "NOT_FOUND", "Plan not found")
    return plan


@router.get("/subscription")
def subscription(ctx: BusinessContext = Depends(business_context), db: Session = Depends(get_db)):
    ctx.require("billing.manage")
    return subscription_view(db, ctx.business)


@router.get("/subscription/preview")
def preview(plan_id: str = Query(max_length=36), interval: str = Query("MONTHLY", pattern="^(MONTHLY|ANNUAL)$"),
            ctx: BusinessContext = Depends(business_context), db: Session = Depends(get_db)):
    """What changing plan would cost now, so the owner confirms with real numbers."""
    ctx.require("billing.manage")
    plan = _plan(db, plan_id)
    billing = BillingService(db)
    quote = billing.quote(ctx.business.id, plan, interval)
    current = current_subscription(db, ctx.business.id)
    credit = billing.unused_credit(current, now_utc()) if current else 0
    current_rank = db.get(SubscriptionPlan, current.plan_id).sort_order if current else 0
    scheduled = bool(current and plan.sort_order < current_rank and current.price_amount > 0)
    # Same rule as BillingService._start: a paid plan's trial is offered once per laundry and plan.
    trialled = db.scalar(select(BusinessSubscription.id).where(BusinessSubscription.business_id == ctx.business.id,
                                                              BusinessSubscription.plan_id == plan.id))
    paying = bool(current and current.status in ("ACTIVE", "PAST_DUE") and current.price_amount > 0)
    trial = plan.trial_days if quote["list_price"] and plan.trial_days and not trialled and not paying else 0
    due_now = 0 if scheduled or trial else max(quote["price"] - credit, 0)
    return {**quote, "credit": min(credit, quote["price"]), "due_now": due_now, "takes_effect": "PERIOD_END" if scheduled else "NOW",
            "effective_at": current.current_period_end if scheduled else now_utc(), "trial_days": trial}


@router.post("/subscription")
def change(payload: PlanChange, ctx: BusinessContext = Depends(business_context), db: Session = Depends(get_db)):
    ctx.require("billing.manage")
    BillingService(db).change_plan(ctx.business, _plan(db, payload.plan_id), payload.interval, ctx.user, "SELF")
    return subscription_view(db, ctx.business)


@router.post("/subscription/cancel")
def cancel(ctx: BusinessContext = Depends(business_context), db: Session = Depends(get_db)):
    ctx.require("billing.manage")
    BillingService(db).cancel(ctx.business, ctx.user)
    return subscription_view(db, ctx.business)


@router.get("/invoices/{invoice_id}")
def invoice(invoice_id: str, ctx: BusinessContext = Depends(business_context), db: Session = Depends(get_db)):
    ctx.require("billing.manage")
    inv = db.scalar(select(SubscriptionInvoice).where(SubscriptionInvoice.id == invoice_id,
                                                      SubscriptionInvoice.business_id == ctx.business.id))
    if not inv:
        raise not_found("Invoice")
    b = ctx.business
    return {**BillingService(db).invoice_out(inv), "business": {"name": b.name, "address": b.address, "area": b.area,
                                                                "phone": b.phone}}
