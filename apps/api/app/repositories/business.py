from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from ..core.errors import AppError
from ..domain import order_states as S
from ..domain import permissions as P
from ..domain.clock import now_utc
from ..domain.periods import local_midnight, resolve
from ..models import BusinessCustomer, BusinessOnboarding, Customer, Order, Service
from ..services.analytics import DUE_SOON_HOURS, LIVE, OUTSTANDING, PRE_READY, UNCOLLECTED_HOURS, UNPAID

# Order list views, as staff think about the work.
VIEWS = {
    "all": None,
    "new": Order.status == S.NEW,
    "in_progress": Order.status.in_([S.ACCEPTED, S.AWAITING_PICKUP, S.RECEIVED, S.WASHING, S.DRYING, S.IRONING,
                                     S.QUALITY_CHECK]),
    "ready": Order.status == S.READY,
    "delivery": or_(and_(Order.fulfillment == "PICKUP", Order.status.in_([S.ACCEPTED, S.AWAITING_PICKUP, S.READY])),
                    Order.status == S.OUT_FOR_DELIVERY),
    "completed": Order.status.in_([S.DELIVERED, S.COMPLETED]),
    "cancelled": Order.status.in_([S.CANCELLED, S.REJECTED]),
}
DUE = ("overdue", "today", "soon", "uncollected")
PAYMENT = ("unpaid", "paid", "processing", "outstanding")

# Segments are descriptive, not judgements: nobody is labelled "churned".
INACTIVE_DAYS = 45
FREQUENT_WINDOW_DAYS = 60
FREQUENT_MIN_ORDERS = 3


@dataclass
class OrderFilters:
    view: str = "all"
    q: str | None = None
    status: str | None = None
    source: str | None = None
    due: str | None = None
    payment: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    customer_id: str | None = None


def due_clause(due: str, now: datetime):
    pre_ready = Order.status.in_(PRE_READY)
    if due == "overdue":
        return and_(pre_ready, Order.due_at < now)
    if due == "soon":
        return and_(pre_ready, Order.due_at >= now, Order.due_at < now + timedelta(hours=DUE_SOON_HOURS))
    if due == "today":
        return and_(pre_ready, Order.due_at >= now, Order.due_at < resolve("today", now=now).end)
    return and_(Order.status == S.READY, Order.fulfillment == "DROP_OFF",
                Order.ready_at < now - timedelta(hours=UNCOLLECTED_HOURS))


class BusinessRepository:
    def __init__(self, db: Session):
        self.db = db

    def onboarding(self, business_id: str) -> BusinessOnboarding:
        record = self.db.scalar(select(BusinessOnboarding).where(BusinessOnboarding.business_id == business_id))
        if record is None:
            record = BusinessOnboarding(business_id=business_id)
            self.db.add(record)
            self.db.flush()
        return record

    def services(self, business_id: str):
        return list(self.db.scalars(select(Service).where(Service.business_id == business_id)
                                    .order_by(Service.category, Service.sort_order, Service.name)))

    # ---- orders --------------------------------------------------------------------------------------------------
    def order_conditions(self, business_id: str, f: OrderFilters, role: str, now: datetime | None = None) -> list:
        now = now or now_utc()
        conds = [Order.business_id == business_id]
        if P.can(role, "orders.deliveries_only"):
            conds += [Order.fulfillment == "PICKUP", Order.status.in_(P.DRIVER_STATUSES)]
        if f.view not in VIEWS:
            raise AppError(422, "INVALID_FILTER", f"Unknown view {f.view}")
        if VIEWS[f.view] is not None:
            conds.append(VIEWS[f.view])
        if f.status:
            conds.append(Order.status.in_(f.status.split(",")))
        if f.source:
            conds.append(Order.source.in_(f.source.split(",")))
        if f.due:
            if f.due not in DUE:
                raise AppError(422, "INVALID_FILTER", f"Unknown due filter {f.due}")
            conds.append(due_clause(f.due, now))
        if f.payment:
            if f.payment not in PAYMENT:
                raise AppError(422, "INVALID_FILTER", f"Unknown payment filter {f.payment}")
            conds.append({"unpaid": and_(LIVE, Order.payment_status.in_(UNPAID)), "outstanding": OUTSTANDING,
                          "paid": Order.payment_status.in_(["PAID", "REFUNDED"]),
                          "processing": Order.payment_status == "PROCESSING"}[f.payment])
        if f.date_from:
            conds.append(Order.created_at >= local_midnight(f.date_from))
        if f.date_to:
            conds.append(Order.created_at < local_midnight(f.date_to + timedelta(days=1)))
        if f.customer_id:
            conds.append(Order.customer_id == f.customer_id)
        if f.q:
            like = f"%{f.q.strip()}%"
            matching = select(Customer.id).where(or_(Customer.name.ilike(like), Customer.phone.ilike(like)))
            conds.append(or_(Order.order_number.ilike(like), Order.customer_id.in_(matching)))
        return conds

    def orders_stmt(self, business_id: str, f: OrderFilters, role: str):
        stmt = select(Order).where(*self.order_conditions(business_id, f, role))
        # Urgent work first wherever urgency is the point of the view.
        if f.due in ("overdue", "today", "soon") or f.view in ("new", "in_progress"):
            return stmt.order_by(Order.due_at.asc().nulls_last(), Order.created_at)
        if f.view == "ready" or f.due == "uncollected":
            return stmt.order_by(Order.ready_at.asc().nulls_last())
        if f.view == "delivery":
            return stmt.order_by(Order.pickup_window_start.asc().nulls_last(), Order.due_at.asc().nulls_last())
        return stmt.order_by(Order.created_at.desc())

    def view_counts(self, business_id: str, role: str) -> dict:
        now = now_utc()
        base = self.order_conditions(business_id, OrderFilters(), role, now)
        columns = [func.count().filter(clause).label(name) for name, clause in VIEWS.items() if clause is not None]
        columns += [func.count().filter(due_clause(d, now)).label(f"due_{d}") for d in DUE]
        row = self.db.execute(select(func.count().label("all"), *columns).where(*base)).one()
        return dict(row._mapping)

    # ---- customers -----------------------------------------------------------------------------------------------
    def customer_stats(self, business_id: str):
        now = now_utc()
        return (select(
            Order.customer_id.label("cid"),
            func.count().filter(LIVE).label("orders"),
            func.coalesce(func.sum(Order.total).filter(LIVE), 0).label("spend"),
            func.max(Order.created_at).filter(LIVE).label("last_order_at"),
            func.min(Order.created_at).filter(LIVE).label("first_order_at"),
            func.count().filter(and_(LIVE, Order.created_at >= now - timedelta(days=FREQUENT_WINDOW_DAYS))).label("recent"),
            func.coalesce(func.sum(Order.total).filter(OUTSTANDING), 0).label("outstanding"),
        ).where(Order.business_id == business_id).group_by(Order.customer_id).subquery())

    def customers_stmt(self, business_id: str, q: str | None = None, segment: str | None = None, sort: str = "recent"):
        stats = self.customer_stats(business_id)
        orders = func.coalesce(stats.c.orders, 0)
        stmt = (select(Customer, BusinessCustomer, stats.c.orders, stats.c.spend, stats.c.last_order_at,
                       stats.c.first_order_at, stats.c.recent, stats.c.outstanding)
                .join(BusinessCustomer, BusinessCustomer.customer_id == Customer.id)
                .outerjoin(stats, stats.c.cid == Customer.id)
                .where(BusinessCustomer.business_id == business_id))
        if q:
            like = f"%{q.strip()}%"
            stmt = stmt.where(or_(Customer.name.ilike(like), Customer.phone.ilike(like)))
        inactive_before = now_utc() - timedelta(days=INACTIVE_DAYS)
        segments = {
            "new": orders <= 1,
            "returning": and_(orders >= 2, func.coalesce(stats.c.recent, 0) < FREQUENT_MIN_ORDERS),
            "frequent": func.coalesce(stats.c.recent, 0) >= FREQUENT_MIN_ORDERS,
            "inactive": and_(orders >= 1, stats.c.last_order_at < inactive_before),
            "outstanding": func.coalesce(stats.c.outstanding, 0) > 0,
        }
        if segment:
            if segment not in segments:
                raise AppError(422, "INVALID_FILTER", f"Unknown segment {segment}")
            stmt = stmt.where(segments[segment])
        order = {"recent": [stats.c.last_order_at.desc().nulls_last()], "spend": [func.coalesce(stats.c.spend, 0).desc()],
                 "orders": [orders.desc()], "name": [Customer.name]}.get(sort)
        if order is None:
            raise AppError(422, "INVALID_FILTER", f"Unknown sort {sort}")
        return stmt.order_by(*order, Customer.name, Customer.id)


def customer_segment(orders: int, recent: int) -> str:
    if recent >= FREQUENT_MIN_ORDERS:
        return "FREQUENT"
    return "RETURNING" if orders >= 2 else "NEW"
