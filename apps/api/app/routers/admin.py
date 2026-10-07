import json
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from ..core.errors import not_found
from ..database import get_db
from ..dependencies import require_admin
from ..domain import order_states as S
from ..models import AuditLog, Business, Commission, Customer, MarketplaceAccount, Order, Payment, Review, Service, User
from ..schemas.admin import MarketplaceDecision
from ..services.admin import MarketplaceAdminService
from ..services.business import BusinessProfileService
from ..services.marketplace import hours_out
from ..services.payments import PaymentService, payment_out
from ..services.reviews import ReviewService
from .common import Page, page_params, paginate

router = APIRouter(prefix="/admin", tags=["Administration"], dependencies=[Depends(require_admin)])


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db)):
    live = Order.status.notin_([S.CANCELLED, S.REJECTED])
    marketplace_gmv = db.scalar(select(func.coalesce(func.sum(Order.total), 0)).where(Order.source == "MARKETPLACE", live)) or 0
    return {
        "businesses": db.scalar(select(func.count(Business.id))),
        "marketplace_active": db.scalar(select(func.count(MarketplaceAccount.id)).where(MarketplaceAccount.status == "ACTIVE")),
        "pending_applications": db.scalar(select(func.count(MarketplaceAccount.id)).where(MarketplaceAccount.status == "PENDING_REVIEW")),
        "customers": db.scalar(select(func.count(Customer.id))),
        "orders": db.scalar(select(func.count(Order.id)).where(live)),
        "marketplace_orders": db.scalar(select(func.count(Order.id)).where(Order.source == "MARKETPLACE", live)),
        "gmv": marketplace_gmv,
        # Real accrued commission on completed marketplace orders, not an estimate.
        "platform_revenue": db.scalar(select(func.coalesce(func.sum(Commission.amount), 0))) or 0,
    }


@router.get("/businesses")
def businesses(q: str | None = Query(None, max_length=80), page: Page = Depends(page_params), db: Session = Depends(get_db)):
    stmt = select(Business).options(selectinload(Business.marketplace)).order_by(Business.created_at.desc())
    if q:
        stmt = stmt.where(or_(Business.name.ilike(f"%{q}%"), Business.area.ilike(f"%{q}%")))
    return paginate(db, stmt, page, lambda x: {
        "id": x.id, "name": x.name, "slug": x.slug, "area": x.area, "status": x.status,
        "verification_status": x.verification_status, "rating": float(x.rating), "review_count": x.review_count,
        "marketplace_status": x.marketplace.status if x.marketplace else "NOT_ENROLLED"})


def _application_out(m: MarketplaceAccount) -> dict:
    b = m.business
    return {"id": m.id, "business_id": b.id, "business_name": b.name, "slug": b.slug, "area": b.area, "status": m.status,
            "commission_rate": float(m.commission_rate), "pickup_radius_km": float(m.pickup_radius_km),
            "contact_name": m.contact_name, "registration_number": m.registration_number, "tin": m.tin,
            "submitted_at": m.submitted_at, "reviewed_at": m.reviewed_at, "rejection_reason": m.rejection_reason}


@router.get("/marketplace-applications")
def applications(status: str | None = Query(None, max_length=20), page: Page = Depends(page_params), db: Session = Depends(get_db)):
    stmt = (select(MarketplaceAccount).options(selectinload(MarketplaceAccount.business))
            .where(MarketplaceAccount.status != "NOT_ENROLLED").order_by(MarketplaceAccount.submitted_at.desc()))
    if status:
        stmt = stmt.where(MarketplaceAccount.status == status)
    return paginate(db, stmt, page, _application_out)


@router.get("/marketplace-applications/{application_id}")
def application_detail(application_id: str, db: Session = Depends(get_db)):
    account = db.get(MarketplaceAccount, application_id)
    if not account:
        raise not_found("Application")
    b = account.business
    services = db.scalars(select(Service).where(Service.business_id == b.id, Service.active.is_(True)).order_by(Service.name))
    return {**_application_out(account), "business": {"description": b.description, "phone": b.phone, "address": b.address,
            "latitude": b.latitude, "longitude": b.longitude, "pickup_enabled": b.pickup_enabled, "pickup_fee": b.pickup_fee,
            "hours": hours_out(b.hours)},
            "services": [{"name": s.name, "price": s.price, "pricing_model": s.pricing_model} for s in services],
            "checklist": BusinessProfileService(db).readiness(b)}


@router.post("/marketplace-applications/{application_id}/{decision}")
def decide(application_id: str, decision: Literal["approve", "reject", "suspend", "reinstate"], payload: MarketplaceDecision,
           db: Session = Depends(get_db), actor: User = Depends(require_admin)):
    account = db.get(MarketplaceAccount, application_id)
    if not account:
        raise not_found("Application")
    account = MarketplaceAdminService(db).decide(account, decision, actor, payload.reason, payload.commission_rate)
    return {"id": account.id, "status": account.status}


@router.get("/orders")
def orders(status: str | None = Query(None, max_length=20), source: str | None = Query(None, max_length=20),
           page: Page = Depends(page_params), db: Session = Depends(get_db)):
    stmt = select(Order).options(selectinload(Order.business), selectinload(Order.customer)).order_by(Order.created_at.desc())
    if status:
        stmt = stmt.where(Order.status == status)
    if source:
        stmt = stmt.where(Order.source == source)
    return paginate(db, stmt, page, lambda x: {
        "id": x.id, "order_number": x.order_number, "status": x.status, "payment_status": x.payment_status, "total": x.total,
        "source": x.source, "business_name": x.business.name, "customer_name": x.customer.name, "created_at": x.created_at})


@router.get("/customers")
def customers(q: str | None = Query(None, max_length=80), page: Page = Depends(page_params), db: Session = Depends(get_db)):
    stmt = select(Customer).order_by(Customer.name)
    if q:
        stmt = stmt.where(or_(Customer.name.ilike(f"%{q}%"), Customer.phone.ilike(f"%{q}%")))
    return paginate(db, stmt, page, lambda x: {"id": x.id, "name": x.name, "phone": x.phone, "email": x.email,
                                                 "has_app": x.user_id is not None})


@router.get("/payments")
def payments(status: str | None = Query(None, max_length=20), page: Page = Depends(page_params), db: Session = Depends(get_db)):
    stmt = select(Payment).order_by(Payment.created_at.desc())
    if status:
        stmt = stmt.where(Payment.status == status)
    return paginate(db, stmt, page, lambda p: {**payment_out(p), "order_id": p.order_id, "created_at": p.created_at})


@router.post("/payments/{payment_id}/refund")
def refund(payment_id: str, payload: MarketplaceDecision, db: Session = Depends(get_db), actor: User = Depends(require_admin)):
    payment = db.get(Payment, payment_id)
    if not payment:
        raise not_found("Payment")
    return payment_out(PaymentService(db).refund(payment, actor.id, payload.reason))


@router.get("/reviews")
def reviews(page: Page = Depends(page_params), db: Session = Depends(get_db)):
    stmt = select(Review, Business.name).join(Business, Business.id == Review.business_id).order_by(Review.created_at.desc())
    total = db.scalar(select(func.count(Review.id))) or 0
    rows = db.execute(stmt.offset(page.offset).limit(page.page_size)).all()
    return {"items": [{"id": r.id, "rating": r.rating, "comment": r.comment, "status": r.status, "author": r.author_name,
                       "business_name": name, "created_at": r.created_at} for r, name in rows],
            "total": total, "page": page.page, "page_size": page.page_size}


@router.post("/reviews/{review_id}/{action}")
def moderate(review_id: str, action: Literal["hide", "publish"], db: Session = Depends(get_db), actor: User = Depends(require_admin)):
    review = db.get(Review, review_id)
    if not review:
        raise not_found("Review")
    review = ReviewService(db).moderate(review, "HIDDEN" if action == "hide" else "PUBLISHED", actor)
    return {"id": review.id, "status": review.status}


@router.get("/audit-logs")
def logs(page: Page = Depends(page_params), db: Session = Depends(get_db)):
    stmt = select(AuditLog, User.email, User.phone).outerjoin(User, User.id == AuditLog.actor_id).order_by(AuditLog.created_at.desc())
    total = db.scalar(select(func.count(AuditLog.id))) or 0
    rows = db.execute(stmt.offset(page.offset).limit(page.page_size)).all()
    return {"items": [{"action": x.action, "entity": x.entity, "entity_id": x.entity_id, "actor": email or phone,
                       "metadata": json.loads(x.metadata_json or "{}"), "created_at": x.created_at} for x, email, phone in rows],
            "total": total, "page": page.page, "page_size": page.page_size}
