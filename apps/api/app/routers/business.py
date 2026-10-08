import json
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session, selectinload

from ..core.errors import AppError, not_found
from ..database import get_db
from ..dependencies import BusinessContext, business_context
from ..domain import order_states as S
from ..domain import permissions as P
from ..domain.clock import as_utc, now_local, now_utc
from ..domain.periods import PeriodError, resolve
from ..domain.phone import normalize_tz_phone
from ..models import Business, BusinessCustomer, Customer, Order, OrderItem, Payment, Review, Service, User
from ..repositories.business import BusinessRepository, OrderFilters, customer_segment
from ..schemas.business import (
    BusinessOrderCreate,
    BusinessProfileUpdate,
    CollectRequest,
    CustomerCreate,
    CustomerNotes,
    HoursUpdate,
    MarketplaceApplication,
    MarketplaceDraft,
    OnboardingUpdate,
    OrderUpdate,
    PaymentRecord,
    ServiceCreate,
    StaffCreate,
)
from ..schemas.orders import StatusChange
from ..services.analytics import DUE_SOON_HOURS, LIVE, PRE_READY, BusinessAnalytics, avg_int
from ..services.audit import audit
from ..services.business import BusinessProfileService, BusinessRegistrationService
from ..services.entitlements import require_feature
from ..services.entitlements import resolve as resolve_plan
from ..services.marketplace import hours_out, service_out
from ..services.marketplace_program import MarketplaceProgram
from ..services.orders import OrderService, ensure_business_customer, order_detail
from ..services.payments import PaymentService, payment_out
from ..services.report_export import orders_csv
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
def profile(ctx: BusinessContext = Depends(business_context), db: Session = Depends(get_db)):
    """Includes the caller's role and capabilities so clients can shape navigation (the API still enforces them)."""
    effective = resolve_plan(db, ctx.business.id)
    return {**profile_out(ctx.business), "role": ctx.user.role, "capabilities": sorted(ctx.capabilities),
            "plan": {"name": effective.plan.name, "features": sorted(effective.features), "source": effective.source,
                     "access_until": effective.ends_at}}


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


# ---- customers ------------------------------------------------------------------------------------------------
def _customer_row(row) -> dict:
    customer, link, orders, spend, last_at, first_at, recent, outstanding = row
    orders, recent = orders or 0, recent or 0
    return {"id": customer.id, "name": customer.name, "phone": customer.phone, "email": customer.email,
            "has_app": customer.user_id is not None, "orders": orders, "spend": int(spend or 0),
            "average_order": avg_int(int(spend or 0), orders), "last_order_at": last_at, "first_order_at": first_at,
            "outstanding": int(outstanding or 0), "segment": customer_segment(orders, recent), "notes": link.notes,
            "added_at": link.created_at}


@router.get("/customers")
def customers(q: str | None = Query(None, max_length=80), segment: str | None = Query(None, max_length=20),
              sort: str = Query("recent", max_length=10), page: Page = Depends(page_params),
              ctx: BusinessContext = Depends(business_context), db: Session = Depends(get_db)):
    ctx.require("customers.view")
    if segment or sort not in ("recent", "name"):
        require_feature(db, ctx.business.id, "customer_crm")  # segments and spend ranking are CRM
    stmt = BusinessRepository(db).customers_stmt(ctx.business.id, q, segment, sort)
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    rows = db.execute(stmt.offset(page.offset).limit(page.page_size)).all()
    return {"items": [_customer_row(r) for r in rows], "total": total, "page": page.page, "page_size": page.page_size}


@router.post("/customers", status_code=201)
def add_customer(payload: CustomerCreate, ctx: BusinessContext = Depends(business_context), db: Session = Depends(get_db)):
    ctx.require("customers.view")
    try:
        phone = normalize_tz_phone(payload.phone)
    except ValueError as exc:
        raise AppError(422, "INVALID_PHONE", str(exc)) from exc
    customer = db.scalar(select(Customer).where(Customer.phone == phone))
    if not customer:
        # A phone number already known to Launder keeps its name; the laundry's own notes stay on its CRM link.
        customer = Customer(name=payload.name, phone=phone, email=payload.email or None)
        db.add(customer)
        db.flush()
    link = ensure_business_customer(db, ctx.business.id, customer.id)
    if payload.notes:
        link.notes = payload.notes
    audit(db, ctx.user.id, "CUSTOMER_ADDED", "customer", customer.id, business_id=ctx.business.id)
    db.commit()
    return _customer_detail(db, ctx, customer.id)


def _customer_detail(db: Session, ctx: BusinessContext, customer_id: str) -> dict:
    repo = BusinessRepository(db)
    row = db.execute(repo.customers_stmt(ctx.business.id).where(Customer.id == customer_id)).first()
    if not row:
        raise not_found("Customer")
    data = _customer_row(row)
    data["preferred_services"] = [
        {"name": name, "orders": n, "quantity": float(qty)} for name, n, qty in db.execute(
            select(OrderItem.name, func.count(distinct(OrderItem.order_id)), func.sum(OrderItem.quantity))
            .join(Order, Order.id == OrderItem.order_id)
            .where(Order.business_id == ctx.business.id, Order.customer_id == customer_id, LIVE)
            .group_by(OrderItem.name).order_by(func.count(distinct(OrderItem.order_id)).desc(), OrderItem.name).limit(3))]
    recent = db.scalars(repo.orders_stmt(ctx.business.id, OrderFilters(customer_id=customer_id), ctx.user.role)
                        .options(selectinload(Order.customer), selectinload(Order.items)).limit(10))
    now = now_utc()
    data["recent_orders"] = [_order_row(o, now) for o in recent]
    return data


@router.get("/customers/{customer_id}")
def customer_detail(customer_id: str, ctx: BusinessContext = Depends(business_context), db: Session = Depends(get_db)):
    ctx.require("customers.view")
    require_feature(db, ctx.business.id, "customer_crm")
    return _customer_detail(db, ctx, customer_id)


@router.put("/customers/{customer_id}/notes")
def customer_notes(customer_id: str, payload: CustomerNotes, ctx: BusinessContext = Depends(business_context),
                   db: Session = Depends(get_db)):
    ctx.require("customers.view")
    require_feature(db, ctx.business.id, "customer_crm")
    link = db.scalar(select(BusinessCustomer).where(BusinessCustomer.business_id == ctx.business.id,
                                                   BusinessCustomer.customer_id == customer_id))
    if not link:
        raise not_found("Customer")
    link.notes = payload.notes
    db.commit()
    return _customer_detail(db, ctx, customer_id)


# ---- orders ---------------------------------------------------------------------------------------------------
def _due_state(o: Order, now) -> str | None:
    if o.due_at is None or o.status not in PRE_READY:
        return None
    due = as_utc(o.due_at)
    if due < now:
        return "OVERDUE"
    if due < now + timedelta(hours=DUE_SOON_HOURS):
        return "DUE_SOON"
    return "DUE_TODAY" if due < resolve("today", now=now).end else None


def _order_row(o: Order, now) -> dict:
    return {"id": o.id, "order_number": o.order_number, "customer_id": o.customer_id,
            "customer_name": o.guest_name or o.customer.name, "is_guest": o.customer.is_guest,
            "phone": o.customer.phone, "source": o.source, "amount_paid": o.amount_paid, "status": o.status, "fulfillment": o.fulfillment,
            "payment_status": o.payment_status, "payment_method": o.payment_method, "total": o.total,
            "created_at": o.created_at, "pickup_window_start": o.pickup_window_start, "pickup_address": o.pickup_address,
            "due_at": o.due_at, "ready_at": o.ready_at, "due_state": _due_state(o, now),
            "items": [{"name": i.name, "quantity": float(i.quantity), "pricing_model": i.pricing_model} for i in o.items]}


def order_filters(view: str = Query("all", max_length=20), q: str | None = Query(None, max_length=80),
                  status: str | None = Query(None, max_length=200), source: str | None = Query(None, max_length=60),
                  due: str | None = Query(None, max_length=20), payment: str | None = Query(None, max_length=20),
                  date_from: date | None = None, date_to: date | None = None,
                  customer_id: str | None = Query(None, max_length=36)) -> OrderFilters:
    return OrderFilters(view, q, status, source, due, payment, date_from, date_to, customer_id)


@router.get("/orders")
def orders(f: OrderFilters = Depends(order_filters), page: int = Query(1, ge=1), page_size: int = Query(20, ge=5, le=100),
           ctx: BusinessContext = Depends(business_context), db: Session = Depends(get_db)):
    ctx.require("orders.view")
    stmt = BusinessRepository(db).orders_stmt(ctx.business.id, f, ctx.user.role).options(
        selectinload(Order.customer), selectinload(Order.items))
    now = now_utc()
    return paginate(db, stmt, Page(page, page_size), lambda o: _order_row(o, now))


@router.get("/orders/counts")
def order_counts(ctx: BusinessContext = Depends(business_context), db: Session = Depends(get_db)):
    ctx.require("orders.view")
    return BusinessRepository(db).view_counts(ctx.business.id, ctx.user.role)


EXPORT_LIMIT = 10_000


@router.get("/orders/export.csv")
def export_orders(f: OrderFilters = Depends(order_filters), ctx: BusinessContext = Depends(business_context),
                  db: Session = Depends(get_db)):
    """Every order matching the filters (up to 10,000), not just the page on screen."""
    ctx.require("reports.operational")
    require_feature(db, ctx.business.id, "data_export")
    stmt = BusinessRepository(db).orders_stmt(ctx.business.id, f, ctx.user.role).options(
        selectinload(Order.customer), selectinload(Order.items)).limit(EXPORT_LIMIT + 1)
    rows = list(db.scalars(stmt))
    if len(rows) > EXPORT_LIMIT:
        raise AppError(422, "EXPORT_TOO_LARGE", "Narrow the date range to export at most 10,000 orders")
    b = ctx.business
    body = orders_csv(rows, b.name, ", ".join(x for x in (b.address, b.area) if x), vars(f), now_utc())
    return Response("\ufeff" + body, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="orders-{now_local().date().isoformat()}.csv"'})


@router.post("/orders", status_code=201)
def create_order(payload: BusinessOrderCreate, ctx: BusinessContext = Depends(business_context), db: Session = Depends(get_db)):
    ctx.require("orders.create")
    require_feature(db, ctx.business.id, "walk_in_orders")
    order = OrderService(db).create_business_order(ctx.business, ctx.user, payload)
    return {"id": order.id, "order_number": order.order_number, "status": order.status, "total": order.total,
            "due_at": order.due_at}


def _owned_order(db: Session, ctx: BusinessContext, order_id: str) -> Order:
    ctx.require("orders.view")
    conds = [Order.id == order_id, Order.business_id == ctx.business.id]
    if ctx.can("orders.deliveries_only"):
        conds += [Order.fulfillment == "PICKUP", Order.status.in_(P.DRIVER_STATUSES)]
    order = db.scalar(select(Order).where(*conds))
    if not order:
        raise not_found("Order")
    return order


def _business_order(db: Session, ctx: BusinessContext, order: Order) -> dict:
    data = order_detail(db, order, "business")
    data["allowed_next"] = [s for s in data["allowed_next"] if P.may_move_to(ctx.user.role, s, order.status, order.fulfillment)]
    data["due_state"] = _due_state(order, now_utc())
    data["can_edit_due"] = ctx.can("orders.edit") and order.status not in S.TERMINAL
    data["can_record_payment"] = ctx.can("payments.record")
    data["can_collect"] = (order.fulfillment == "DROP_OFF" and order.status in (S.READY, S.DELIVERED)
                           and P.may_move_to(ctx.user.role, S.COMPLETED, S.DELIVERED, order.fulfillment))
    return data


@router.get("/orders/{order_id}")
def get_order(order_id: str, ctx: BusinessContext = Depends(business_context), db: Session = Depends(get_db)):
    return _business_order(db, ctx, _owned_order(db, ctx, order_id))


@router.patch("/orders/{order_id}")
def update_order(order_id: str, payload: OrderUpdate, ctx: BusinessContext = Depends(business_context),
                 db: Session = Depends(get_db)):
    ctx.require("orders.edit")
    order = OrderService(db).set_due(_owned_order(db, ctx, order_id), payload.due_at, ctx.user)
    return _business_order(db, ctx, order)


@router.post("/orders/{order_id}/status")
def change_status(order_id: str, payload: StatusChange, ctx: BusinessContext = Depends(business_context),
                  db: Session = Depends(get_db)):
    order = _owned_order(db, ctx, order_id)
    if not P.may_move_to(ctx.user.role, payload.status.upper(), order.status, order.fulfillment):
        raise AppError(403, "FORBIDDEN", "Your role cannot make this status change")
    order = OrderService(db).transition(order, payload.status, ctx.user, payload.note)
    return _business_order(db, ctx, order)


@router.post("/orders/{order_id}/payments")
def record_payment(order_id: str, payload: PaymentRecord, ctx: BusinessContext = Depends(business_context),
                   db: Session = Depends(get_db)):
    ctx.require("payments.record")
    order = _owned_order(db, ctx, order_id)
    return payment_out(PaymentService(db).record_manual(order, ctx.user.id, payload.method, payload.reference.strip(),
                                                        payload.amount))


@router.post("/orders/{order_id}/collect")
def collect(order_id: str, payload: CollectRequest, ctx: BusinessContext = Depends(business_context),
            db: Session = Depends(get_db)):
    """Counter hand-over in one step: take the balance (optional), then mark delivered and completed."""
    order = _owned_order(db, ctx, order_id)
    if not P.may_move_to(ctx.user.role, S.COMPLETED, S.DELIVERED, order.fulfillment):
        raise AppError(403, "FORBIDDEN", "Your role cannot hand over orders")
    if payload.payment:
        ctx.require("payments.record")
    return _business_order(db, ctx, OrderService(db).collect(order, ctx.user, payload.payment))


@router.post("/orders/{order_id}/payments/cash")
def record_cash(order_id: str, ctx: BusinessContext = Depends(business_context), db: Session = Depends(get_db)):
    ctx.require("payments.record")
    return payment_out(PaymentService(db).record_cash(_owned_order(db, ctx, order_id), ctx.user.id))


@router.get("/payments")
def payments(period: str = Query("today", max_length=20), start: date | None = None, end: date | None = None,
             page: Page = Depends(page_params), ctx: BusinessContext = Depends(business_context), db: Session = Depends(get_db)):
    """Payments received in a period (by the day the money came in), newest first."""
    ctx.require("money.view")
    try:
        p = resolve(period, start, end)
    except PeriodError as exc:
        raise AppError(422, "INVALID_PERIOD", str(exc)) from exc
    where = [Order.business_id == ctx.business.id, Payment.paid_at >= p.start, Payment.paid_at < p.until]
    total = db.scalar(select(func.count()).select_from(Payment).join(Order, Order.id == Payment.order_id).where(*where)) or 0
    rows = db.execute(select(Payment, Order.order_number, func.coalesce(Order.guest_name, Customer.name))
                      .join(Order, Order.id == Payment.order_id).join(Customer, Customer.id == Order.customer_id)
                      .where(*where).order_by(Payment.paid_at.desc()).offset(page.offset).limit(page.page_size)).all()
    result = {"items": [{**payment_out(pay), "paid_at": pay.paid_at, "refunded_at": pay.refunded_at, "order_id": pay.order_id,
                         "order_number": number, "customer_name": name} for pay, number, name in rows],
              "total": total, "page": page.page, "page_size": page.page_size}
    summary = BusinessAnalytics(db, ctx.business)
    result["summary"] = {**summary.collections(p.start, p.until), "sales": summary.order_totals(p.start, p.until)["sales"],
                         "outstanding_now": summary.outstanding(), "period": p.out()}
    return result


# ---- marketplace ------------------------------------------------------------------------------------------------
@router.get("/marketplace")
def marketplace(ctx: BusinessContext = Depends(business_context), db: Session = Depends(get_db)):
    ctx.require("marketplace.view")
    return MarketplaceProgram(db).provider_view(ctx.business)


@router.put("/marketplace/application")
def save_application(payload: MarketplaceDraft, ctx: BusinessContext = Depends(business_context), db: Session = Depends(get_db)):
    """Save an unfinished application; nothing is submitted."""
    ctx.require_owner()
    program = MarketplaceProgram(db, ctx.user)
    program.save_draft(ctx.business, payload.model_dump(exclude_unset=True))
    return program.provider_view(ctx.business)


@router.post("/marketplace/application")
def apply(payload: MarketplaceApplication, ctx: BusinessContext = Depends(business_context), db: Session = Depends(get_db)):
    """Submit (or confirm an invitation). The owner accepts the Marketplace terms shown on the page."""
    ctx.require_owner()
    program = MarketplaceProgram(db, ctx.user)
    program.submit(ctx.business, payload.model_dump())
    return program.provider_view(ctx.business)


@router.post("/marketplace/accept-terms")
def accept_terms(ctx: BusinessContext = Depends(business_context), db: Session = Depends(get_db)):
    """Accept the standard Marketplace terms: after an expired trial (reactivates new orders) or in advance."""
    ctx.require_owner()
    program = MarketplaceProgram(db, ctx.user)
    program.accept_standard_terms(ctx.business)
    return program.provider_view(ctx.business)


@router.get("/reviews")
def reviews(page: Page = Depends(page_params), ctx: BusinessContext = Depends(business_context), db: Session = Depends(get_db)):
    ctx.require("marketplace.view")
    stmt = select(Review).where(Review.business_id == ctx.business.id).order_by(Review.created_at.desc())
    return paginate(db, stmt, page, lambda r: {"id": r.id, "rating": r.rating, "comment": r.comment, "author": r.author_name,
                                                 "status": r.status, "created_at": r.created_at})


# ---- staff ------------------------------------------------------------------------------------------------------
def _staff_out(u: User) -> dict:
    return {"id": u.id, "name": u.full_name, "email": u.email, "role": u.role, "active": u.active}


@router.get("/staff")
def staff(ctx: BusinessContext = Depends(business_context), db: Session = Depends(get_db)):
    ctx.require("staff.view")
    owner = db.get(User, ctx.business.owner_id)
    members = db.scalars(select(User).where(User.business_id == ctx.business.id).order_by(User.full_name))
    return {"items": [_staff_out(owner)] + [_staff_out(u) for u in members]}


@router.post("/staff", status_code=201)
def add_staff(payload: StaffCreate, ctx: BusinessContext = Depends(business_context), db: Session = Depends(get_db)):
    ctx.require_owner()
    effective = resolve_plan(db, ctx.business.id)
    if payload.role != "STAFF" and "team_roles" not in effective.features:
        require_feature(db, ctx.business.id, "team_roles")
    team = db.scalar(select(func.count()).select_from(User).where(User.business_id == ctx.business.id,
                                                                    User.active.is_(True))) or 0
    if effective.plan.max_staff is not None and team >= effective.plan.max_staff:
        raise AppError(402, "PLAN_LIMIT_REACHED", f"Your plan includes up to {effective.plan.max_staff} team members",
                       {"limit": effective.plan.max_staff, "current_plan": effective.plan.name})
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
