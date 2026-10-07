import json
from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, selectinload

from ..core.errors import not_found
from ..database import get_db
from ..dependencies import BusinessContext, business_context
from ..domain import order_states as S
from ..domain.clock import now_local, now_utc
from ..models import Business, Commission, Order, Review, Service, User
from ..repositories.business import BusinessRepository
from ..schemas.business import (
    BusinessOrderCreate,
    BusinessProfileUpdate,
    HoursUpdate,
    MarketplaceApplication,
    OnboardingUpdate,
    ServiceCreate,
    StaffCreate,
)
from ..schemas.orders import StatusChange
from ..services.audit import audit
from ..services.business import BusinessProfileService, BusinessRegistrationService, marketplace_status_out
from ..services.marketplace import hours_out, service_out
from ..services.orders import OrderService, order_detail
from ..services.payments import PaymentService, payment_out
from .common import Page, page_params, paginate

router = APIRouter(prefix="/business", tags=["Business"])


def profile_out(b: Business) -> dict:
    return {"id": b.id, "name": b.name, "slug": b.slug, "description": b.description, "phone": b.phone, "address": b.address,
            "area": b.area, "city": b.city, "status": b.status, "verification_status": b.verification_status,
            "latitude": b.latitude, "longitude": b.longitude, "pickup_enabled": b.pickup_enabled, "pickup_fee": b.pickup_fee,
            "rating": float(b.rating), "review_count": b.review_count, "cover_image_url": b.cover_image_url,
            "hours": hours_out(b.hours)}


# ---- profile, hours, onboarding ---------------------------------------------------------------------------------
@router.get("/profile")
def profile(ctx: BusinessContext = Depends(business_context)):
    return profile_out(ctx.business)


@router.put("/profile")
def update_profile(payload: BusinessProfileUpdate, ctx: BusinessContext = Depends(business_context), db: Session = Depends(get_db)):
    ctx.require_manager()
    return profile_out(BusinessProfileService(db).update_profile(ctx.business, payload, ctx.user))


@router.put("/hours")
def update_hours(payload: HoursUpdate, ctx: BusinessContext = Depends(business_context), db: Session = Depends(get_db)):
    ctx.require_manager()
    return {"hours": hours_out(BusinessProfileService(db).set_hours(ctx.business, payload, ctx.user))}


@router.get("/onboarding")
def get_onboarding(ctx: BusinessContext = Depends(business_context), db: Session = Depends(get_db)):
    record = BusinessRepository(db).onboarding(ctx.business.id)
    db.commit()
    return {"current_step": record.current_step, "data": json.loads(record.data_json), "completed": record.completed}


@router.put("/onboarding")
def save_onboarding(payload: OnboardingUpdate, ctx: BusinessContext = Depends(business_context), db: Session = Depends(get_db)):
    ctx.require_owner()
    record = BusinessRepository(db).onboarding(ctx.business.id)
    record = BusinessRegistrationService(db).save_onboarding(ctx.business, record, payload.step, payload.data, payload.completed)
    return {"current_step": record.current_step, "completed": record.completed}


# ---- services ---------------------------------------------------------------------------------------------------
@router.get("/services")
def services(ctx: BusinessContext = Depends(business_context), db: Session = Depends(get_db)):
    return [service_out(x) for x in BusinessRepository(db).services(ctx.business.id)]


@router.post("/services", status_code=201)
def create_service(payload: ServiceCreate, ctx: BusinessContext = Depends(business_context), db: Session = Depends(get_db)):
    ctx.require_manager()
    service = Service(business_id=ctx.business.id, **payload.model_dump())
    db.add(service)
    db.flush()
    audit(db, ctx.user.id, "SERVICE_CREATED", "service", service.id, price=service.price)
    db.commit()
    return service_out(service)


def _owned_service(db: Session, ctx: BusinessContext, service_id: str) -> Service:
    service = db.scalar(select(Service).where(Service.id == service_id, Service.business_id == ctx.business.id))
    if not service:
        raise not_found("Service")
    return service


@router.put("/services/{service_id}")
def update_service(service_id: str, payload: ServiceCreate, ctx: BusinessContext = Depends(business_context),
                   db: Session = Depends(get_db)):
    ctx.require_manager()
    service = _owned_service(db, ctx, service_id)
    old_price = service.price
    for key, value in payload.model_dump().items():
        setattr(service, key, value)
    audit(db, ctx.user.id, "SERVICE_UPDATED", "service", service.id, old_price=old_price, new_price=service.price)
    db.commit()
    return service_out(service)


@router.delete("/services/{service_id}", status_code=204)
def delete_service(service_id: str, ctx: BusinessContext = Depends(business_context), db: Session = Depends(get_db)):
    """Soft delete: order history keeps pointing at the service, and it disappears from the storefront."""
    ctx.require_manager()
    service = _owned_service(db, ctx, service_id)
    service.active = False
    audit(db, ctx.user.id, "SERVICE_ARCHIVED", "service", service.id)
    db.commit()


# ---- customers & orders -----------------------------------------------------------------------------------------
@router.get("/customers")
def customers(q: str | None = Query(None, max_length=80), page: Page = Depends(page_params),
              ctx: BusinessContext = Depends(business_context), db: Session = Depends(get_db)):
    stmt = BusinessRepository(db).customers_stmt(ctx.business.id, q)
    return paginate(db, stmt, page, lambda x: {"id": x.id, "name": x.name, "phone": x.phone, "email": x.email,
                                                 "has_app": x.user_id is not None})


def _order_row(o: Order) -> dict:
    return {"id": o.id, "order_number": o.order_number, "customer_name": o.customer.name, "phone": o.customer.phone,
            "source": o.source, "status": o.status, "fulfillment": o.fulfillment, "payment_status": o.payment_status,
            "payment_method": o.payment_method, "total": o.total, "created_at": o.created_at,
            "pickup_window_start": o.pickup_window_start}


@router.get("/orders")
def orders(q: str | None = Query(None, max_length=80), status: str | None = Query(None, max_length=200),
           source: str | None = Query(None, max_length=20), page: int = Query(1, ge=1),
           page_size: int = Query(10, ge=5, le=100), ctx: BusinessContext = Depends(business_context),
           db: Session = Depends(get_db)):
    stmt = BusinessRepository(db).orders_stmt(ctx.business.id, q, status, source).options(selectinload(Order.customer))
    return paginate(db, stmt, Page(page, page_size), _order_row)


@router.post("/orders", status_code=201)
def create_order(payload: BusinessOrderCreate, ctx: BusinessContext = Depends(business_context), db: Session = Depends(get_db)):
    order = OrderService(db).create_business_order(ctx.business, ctx.user, payload)
    return {"id": order.id, "order_number": order.order_number, "status": order.status, "total": order.total}


def _owned_order(db: Session, ctx: BusinessContext, order_id: str) -> Order:
    order = db.scalar(select(Order).where(Order.id == order_id, Order.business_id == ctx.business.id))
    if not order:
        raise not_found("Order")
    return order


@router.get("/orders/{order_id}")
def get_order(order_id: str, ctx: BusinessContext = Depends(business_context), db: Session = Depends(get_db)):
    return order_detail(db, _owned_order(db, ctx, order_id), "business")


@router.post("/orders/{order_id}/status")
def change_status(order_id: str, payload: StatusChange, ctx: BusinessContext = Depends(business_context),
                  db: Session = Depends(get_db)):
    order = OrderService(db).transition(_owned_order(db, ctx, order_id), payload.status, ctx.user, payload.note)
    return order_detail(db, order, "business")


@router.post("/orders/{order_id}/payments/cash")
def record_cash(order_id: str, ctx: BusinessContext = Depends(business_context), db: Session = Depends(get_db)):
    return payment_out(PaymentService(db).record_cash(_owned_order(db, ctx, order_id), ctx.user.id))


# ---- marketplace ------------------------------------------------------------------------------------------------
@router.get("/marketplace")
def marketplace(ctx: BusinessContext = Depends(business_context), db: Session = Depends(get_db)):
    return marketplace_status_out(db, ctx.business)


@router.post("/marketplace/application")
def apply(payload: MarketplaceApplication, ctx: BusinessContext = Depends(business_context), db: Session = Depends(get_db)):
    ctx.require_owner()
    BusinessProfileService(db).apply_to_marketplace(ctx.business, payload, ctx.user)
    return marketplace_status_out(db, ctx.business)


@router.get("/reviews")
def reviews(page: Page = Depends(page_params), ctx: BusinessContext = Depends(business_context), db: Session = Depends(get_db)):
    stmt = select(Review).where(Review.business_id == ctx.business.id).order_by(Review.created_at.desc())
    return paginate(db, stmt, page, lambda r: {"id": r.id, "rating": r.rating, "comment": r.comment, "author": r.author_name,
                                                 "status": r.status, "created_at": r.created_at})


# ---- staff ------------------------------------------------------------------------------------------------------
def _staff_out(u: User) -> dict:
    return {"id": u.id, "name": u.full_name, "email": u.email, "role": u.role, "active": u.active}


@router.get("/staff")
def staff(ctx: BusinessContext = Depends(business_context), db: Session = Depends(get_db)):
    ctx.require_manager()
    owner = db.get(User, ctx.business.owner_id)
    members = db.scalars(select(User).where(User.business_id == ctx.business.id).order_by(User.full_name))
    return {"items": [_staff_out(owner)] + [_staff_out(u) for u in members]}


@router.post("/staff", status_code=201)
def add_staff(payload: StaffCreate, ctx: BusinessContext = Depends(business_context), db: Session = Depends(get_db)):
    ctx.require_owner()
    return _staff_out(BusinessProfileService(db).add_staff(ctx.business, payload, ctx.user))


@router.delete("/staff/{user_id}", status_code=204)
def deactivate_staff(user_id: str, ctx: BusinessContext = Depends(business_context), db: Session = Depends(get_db)):
    ctx.require_owner()
    member = db.scalar(select(User).where(User.id == user_id, User.business_id == ctx.business.id))
    if not member:
        raise not_found("Staff member")
    member.active = False
    audit(db, ctx.user.id, "STAFF_DEACTIVATED", "user", member.id)
    db.commit()


# ---- analytics --------------------------------------------------------------------------------------------------
@router.get("/analytics")
def analytics(ctx: BusinessContext = Depends(business_context), db: Session = Depends(get_db)):
    """Revenue counts only PAID orders; cancelled and rejected orders are excluded from every figure."""
    bid = ctx.business.id
    live = Order.status.notin_([S.CANCELLED, S.REJECTED])
    start_of_day = now_local().replace(hour=0, minute=0, second=0, microsecond=0)
    week_ago = now_utc() - timedelta(days=7)
    count, revenue, outstanding = db.execute(select(
        func.count(Order.id),
        func.coalesce(func.sum(case((Order.payment_status == "PAID", Order.total), else_=0)), 0),
        func.coalesce(func.sum(case((Order.payment_status != "PAID", Order.total), else_=0)), 0),
    ).where(Order.business_id == bid, live)).one()
    today_orders, today_revenue = db.execute(select(
        func.count(Order.id), func.coalesce(func.sum(case((Order.payment_status == "PAID", Order.total), else_=0)), 0),
    ).where(Order.business_id == bid, live, Order.created_at >= start_of_day)).one()
    ready = db.scalar(select(func.count(Order.id)).where(Order.business_id == bid, Order.status == S.READY)) or 0
    new = db.scalar(select(func.count(Order.id)).where(Order.business_id == bid, Order.status == S.NEW)) or 0
    sources = dict(db.execute(select(Order.source, func.count(Order.id)).where(Order.business_id == bid, live)
                              .group_by(Order.source)).all())
    week = db.scalar(select(func.count(Order.id)).where(Order.business_id == bid, live, Order.created_at >= week_ago)) or 0
    commission = db.scalar(select(func.coalesce(func.sum(Commission.amount), 0)).where(Commission.business_id == bid)) or 0
    return {"orders": count, "revenue": revenue, "outstanding": outstanding, "average_order": revenue // count if count else 0,
            "today_orders": today_orders, "today_revenue": today_revenue, "ready_for_collection": ready, "new_orders": new,
            "orders_last_7_days": week, "sources": sources, "marketplace_commission": commission,
            "rating": float(ctx.business.rating), "review_count": ctx.business.review_count}
