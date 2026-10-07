"""Business analytics: every figure is aggregated in PostgreSQL, scoped to one business, in local time.

Definitions (see docs/ANALYTICS.md):
* Sales        value of orders taken in the period (created in it), excluding cancelled/declined. After discounts.
* Collected    money received in the period (payments by paid_at), whatever day the order was taken.
* Refunded     payments refunded in the period (by refunded_at).
* Outstanding  unpaid value of live orders the laundry has accepted (status beyond NEW, not cancelled/declined).
* Overdue      orders not yet READY whose promised time (due_at) has passed.
* Delayed      orders due in the period that became ready after their promised time, or are still not ready.
* New customer a customer whose first (non-cancelled) order with this laundry falls in the period.
"""
from datetime import date, datetime, timedelta

from sqlalchemy import Date, and_, case, cast, distinct, exists, func, or_, select
from sqlalchemy.orm import Session

from ..core.config import settings
from ..domain import order_states as S
from ..domain import permissions as P
from ..domain.clock import LOCAL_TZ, now_utc
from ..domain.money import percentage_of
from ..domain.periods import Period, local_midnight, resolve
from ..models import (
    Business,
    BusinessHours,
    Commission,
    Customer,
    DayClose,
    MarketplaceAccount,
    Order,
    OrderItem,
    OrderStatusEvent,
    Payment,
    Service,
    User,
)

MIN_COMPARE_ORDERS = 5  # below this many orders in the comparison period, a % change is noise and is not shown
MIN_INSIGHT_ORDERS = 10
DUE_SOON_HOURS = 4
UNCOLLECTED_HOURS = 48
STUCK_PAYMENT_MINUTES = 30
CLOSED = (S.CANCELLED, S.REJECTED)
LIVE = Order.status.notin_(CLOSED)
PRE_READY = (S.NEW, S.ACCEPTED, S.AWAITING_PICKUP, S.RECEIVED, S.WASHING, S.DRYING, S.IRONING, S.QUALITY_CHECK)
PROCESSING = (S.RECEIVED, S.WASHING, S.DRYING, S.IRONING, S.QUALITY_CHECK)
PIPELINE = (S.NEW, S.ACCEPTED, S.AWAITING_PICKUP, S.RECEIVED, S.WASHING, S.DRYING, S.IRONING, S.QUALITY_CHECK, S.READY,
            S.OUT_FOR_DELIVERY, S.DELIVERED)
UNPAID = ("PENDING", "PROCESSING", "FAILED")
SOURCES = ("WALK_IN", "MARKETPLACE", "PHONE", "WHATSAPP")
METHODS = ("CASH", "MOBILE_MONEY")
OUTSTANDING = and_(LIVE, Order.status != S.NEW, Order.payment_status.in_(UNPAID))


def local_day(column):
    return cast(func.timezone(settings.timezone, column), Date)


def pct(part: float, whole: float) -> float | None:
    return round(part * 100 / whole, 1) if whole else None


def avg_int(total: int, count: int) -> int:
    return (total + count // 2) // count if count else 0


def metric(current: float, previous: float | None, comparable: bool) -> dict:
    """A figure with its comparison. change_pct is None when the comparison would mislead."""
    if not comparable or previous is None:
        return {"value": current, "previous": None, "change_pct": None}
    return {"value": current, "previous": previous,
            "change_pct": round((current - previous) * 100 / previous, 1) if previous else None}


class BusinessAnalytics:
    def __init__(self, db: Session, business: Business, now: datetime | None = None):
        self.db, self.business, self.bid = db, business, business.id
        self.now = now or now_utc()

    def _scalar(self, stmt) -> int:
        return int(self.db.scalar(stmt) or 0)

    # ---- building blocks --------------------------------------------------------------------------------------
    def order_totals(self, start: datetime, end: datetime) -> dict:
        orders, sales, discounts, cancelled, customers = self.db.execute(select(
            func.count().filter(LIVE), func.coalesce(func.sum(Order.total).filter(LIVE), 0),
            func.coalesce(func.sum(Order.discount).filter(LIVE), 0), func.count().filter(Order.status.in_(CLOSED)),
            func.count(distinct(Order.customer_id)).filter(LIVE),
        ).where(Order.business_id == self.bid, Order.created_at >= start, Order.created_at < end)).one()
        return {"orders": orders, "sales": int(sales), "discounts": int(discounts), "cancelled": cancelled,
                "created": orders + cancelled, "customers": customers, "average_order": avg_int(int(sales), orders)}

    def collections(self, start: datetime, end: datetime) -> dict:
        rows = self.db.execute(
            select(Payment.method, func.count(), func.coalesce(func.sum(Payment.amount), 0))
            .join(Order, Order.id == Payment.order_id)
            .where(Order.business_id == self.bid, Payment.paid_at >= start, Payment.paid_at < end)
            .group_by(Payment.method)).all()
        by_method = {m: {"count": 0, "amount": 0} for m in METHODS}
        for method, count, amount in rows:
            by_method[method] = {"count": count, "amount": int(amount)}
        refunded = self._scalar(select(func.sum(Payment.amount)).join(Order, Order.id == Payment.order_id)
                                .where(Order.business_id == self.bid, Payment.refunded_at >= start, Payment.refunded_at < end))
        collected = sum(x["amount"] for x in by_method.values())
        return {"collected": collected, "refunded": refunded, "net_collected": collected - refunded, "by_method": by_method}

    def outstanding(self, start: datetime | None = None, end: datetime | None = None) -> dict:
        conds = [Order.business_id == self.bid, OUTSTANDING]
        if start is not None:
            conds += [Order.created_at >= start, Order.created_at < end]
        count, amount = self.db.execute(select(func.count(), func.coalesce(func.sum(Order.total), 0)).where(*conds)).one()
        return {"count": count, "amount": int(amount)}

    def sources(self, start: datetime, end: datetime) -> list[dict]:
        rows = {src: (n, int(v)) for src, n, v in self.db.execute(
            select(Order.source, func.count(), func.coalesce(func.sum(Order.total), 0))
            .where(Order.business_id == self.bid, LIVE, Order.created_at >= start, Order.created_at < end)
            .group_by(Order.source)).all()}
        total_orders = sum(n for n, _ in rows.values())
        total_sales = sum(v for _, v in rows.values())
        return [{"source": s, "orders": rows.get(s, (0, 0))[0], "sales": rows.get(s, (0, 0))[1],
                 "share_orders": pct(rows.get(s, (0, 0))[0], total_orders), "share_sales": pct(rows.get(s, (0, 0))[1], total_sales)}
                for s in SOURCES]

    def customers(self, start: datetime, end: datetime) -> dict:
        first = (select(Order.customer_id.label("cid"), func.min(Order.created_at).label("first_at"))
                 .where(Order.business_id == self.bid, LIVE).group_by(Order.customer_id).subquery())
        first_source = (select(Order.customer_id.label("cid"), Order.source.label("source"))
                        .distinct(Order.customer_id).where(Order.business_id == self.bid, LIVE)
                        .order_by(Order.customer_id, Order.created_at).subquery())
        per = (select(Order.customer_id.label("cid"), func.count().label("n"))
               .where(Order.business_id == self.bid, LIVE, Order.created_at >= start, Order.created_at < end)
               .group_by(Order.customer_id).subquery())
        unique, new, multi, new_mp = self.db.execute(
            select(func.count(), func.count().filter(first.c.first_at >= start), func.count().filter(per.c.n >= 2),
                   func.count().filter(and_(first.c.first_at >= start, first_source.c.source == "MARKETPLACE")))
            .select_from(per.join(first, first.c.cid == per.c.cid).join(first_source, first_source.c.cid == per.c.cid))).one()
        returning = unique - new
        return {"unique": unique, "new": new, "returning": returning, "repeat_rate": pct(returning, unique),
                "multi_order": multi, "new_from_marketplace": new_mp}

    def services(self, start: datetime, end: datetime, limit: int = 8) -> dict:
        rows = self.db.execute(
            select(OrderItem.name, func.max(OrderItem.pricing_model), func.count(distinct(OrderItem.order_id)),
                   func.sum(OrderItem.quantity), func.sum(OrderItem.line_total))
            .join(Order, Order.id == OrderItem.order_id)
            .where(Order.business_id == self.bid, LIVE, Order.created_at >= start, Order.created_at < end)
            .group_by(OrderItem.name)).all()
        total = sum(int(r[4] or 0) for r in rows)
        items = [{"name": name, "pricing_model": model, "orders": orders, "quantity": float(qty or 0),
                  "revenue": int(revenue or 0), "share_revenue": pct(int(revenue or 0), total)}
                 for name, model, orders, qty, revenue in rows]
        return {"total_revenue": total,
                "by_revenue": sorted(items, key=lambda x: (-x["revenue"], x["name"]))[:limit],
                "by_orders": sorted(items, key=lambda x: (-x["orders"], -x["revenue"], x["name"]))[:limit]}

    def marketplace(self, start: datetime, end: datetime, all_orders: int, all_sales: int) -> dict:
        mp = and_(Order.business_id == self.bid, Order.source == "MARKETPLACE", LIVE, Order.created_at >= start,
                  Order.created_at < end)
        orders, gmv, customers = self.db.execute(select(
            func.count(), func.coalesce(func.sum(Order.total), 0), func.count(distinct(Order.customer_id))).where(mp)).one()
        accrued = self._scalar(select(func.sum(Commission.amount)).join(Order, Order.id == Commission.order_id).where(mp))
        open_base = self._scalar(select(func.sum(Order.subtotal)).where(mp, Order.status != S.COMPLETED))
        account = self.db.scalar(select(MarketplaceAccount).where(MarketplaceAccount.business_id == self.bid))
        rate = account.commission_rate if account else 0
        pending = percentage_of(open_base, rate) if open_base else 0
        return {"status": account.status if account else "NOT_ENROLLED", "commission_rate": float(rate),
                "orders": orders, "sales": int(gmv), "customers": customers, "average_order": avg_int(int(gmv), orders),
                "commission_accrued": accrued, "commission_pending": pending, "net": int(gmv) - accrued - pending,
                "share_orders": pct(orders, all_orders), "share_sales": pct(int(gmv), all_sales),
                "rating": float(self.business.rating), "review_count": self.business.review_count}

    def operations(self, start: datetime, until: datetime) -> dict:
        stages = dict(self.db.execute(
            select(OrderStatusEvent.to_status, func.count(distinct(OrderStatusEvent.order_id)))
            .join(Order, Order.id == OrderStatusEvent.order_id)
            .where(Order.business_id == self.bid, OrderStatusEvent.created_at >= start, OrderStatusEvent.created_at < until,
                   OrderStatusEvent.to_status.in_([S.RECEIVED, S.WASHING, S.IRONING, S.READY, S.DELIVERED, S.COMPLETED,
                                                   S.CANCELLED, S.REJECTED]))
            .group_by(OrderStatusEvent.to_status)).all())
        ready, on_time, late, avg_seconds = self.db.execute(select(
            func.count(), func.count().filter(Order.ready_at <= Order.due_at), func.count().filter(Order.ready_at > Order.due_at),
            func.avg(func.extract("epoch", Order.ready_at - Order.created_at)),
        ).where(Order.business_id == self.bid, Order.ready_at >= start, Order.ready_at < until)).one()
        delayed = self._scalar(select(func.count()).where(
            Order.business_id == self.bid, LIVE, Order.due_at >= start, Order.due_at < until,
            or_(Order.ready_at.is_(None), Order.ready_at > Order.due_at)))
        overdue_now = self._scalar(select(func.count()).where(Order.business_id == self.bid, Order.status.in_(PRE_READY),
                                                               Order.due_at < self.now))
        with_due = on_time + late
        return {"received": stages.get(S.RECEIVED, 0), "washing": stages.get(S.WASHING, 0), "ironing": stages.get(S.IRONING, 0),
                "ready": stages.get(S.READY, 0), "delivered": stages.get(S.DELIVERED, 0), "completed": stages.get(S.COMPLETED, 0),
                "cancelled": stages.get(S.CANCELLED, 0) + stages.get(S.REJECTED, 0),
                "ready_on_time": on_time, "ready_late": late, "on_time_rate": pct(on_time, with_due), "delayed": delayed,
                "overdue_now": overdue_now,
                "average_turnaround_hours": round(float(avg_seconds) / 3600, 1) if ready and avg_seconds is not None else None}

    def _closed_at(self):
        return func.coalesce(Order.completed_at, select(func.min(OrderStatusEvent.created_at)).where(
            OrderStatusEvent.order_id == Order.id, OrderStatusEvent.to_status.in_(CLOSED)).scalar_subquery())

    def open_at(self, moment: datetime) -> int:
        """Orders taken before `moment` and not yet completed, cancelled or declined at that moment."""
        closed = self._closed_at()
        return self._scalar(select(func.count()).where(Order.business_id == self.bid, Order.created_at < moment,
                                                       or_(closed.is_(None), closed >= moment)))

    def daily(self, period: Period) -> list[dict]:
        day = local_day(Order.created_at).label("d")
        orders = {d: (n, int(v)) for d, n, v in self.db.execute(
            select(day, func.count(), func.coalesce(func.sum(Order.total), 0))
            .where(Order.business_id == self.bid, LIVE, Order.created_at >= period.start, Order.created_at < period.until)
            .group_by(day)).all()}
        paid_day = local_day(Payment.paid_at).label("d")
        collected = {d: int(v) for d, v in self.db.execute(
            select(paid_day, func.sum(Payment.amount)).join(Order, Order.id == Payment.order_id)
            .where(Order.business_id == self.bid, Payment.paid_at >= period.start, Payment.paid_at < period.until)
            .group_by(paid_day)).all()}
        last = period.until.astimezone(LOCAL_TZ).date() if period.in_progress else period.end_date
        return [{"date": d.isoformat(), "weekday": d.weekday(), "orders": orders.get(d, (0, 0))[0],
                 "sales": orders.get(d, (0, 0))[1], "collected": collected.get(d, 0)}
                for d in period.local_dates() if d <= last]

    def weekdays(self, weeks: int = 8) -> dict:
        """Orders per weekday over the last full `weeks` weeks (today excluded)."""
        today = self.now.astimezone(LOCAL_TZ).date()
        start, end = local_midnight(today - timedelta(days=7 * weeks)), local_midnight(today)
        day = local_day(Order.created_at).label("d")
        rows = self.db.execute(select(day, func.count()).where(Order.business_id == self.bid, LIVE, Order.created_at >= start,
                                                               Order.created_at < end).group_by(day)).all()
        totals = [0] * 7
        for d, n in rows:
            totals[d.weekday()] += n
        active_weeks = len({d.isocalendar()[:2] for d, _ in rows})
        return {"weeks": weeks, "active_weeks": active_weeks, "orders": totals,
                "average": [round(t / weeks, 1) for t in totals]}

    def pipeline(self, deliveries_only: bool = False) -> dict:
        conds = [Order.business_id == self.bid, Order.status.in_(PIPELINE)]
        if deliveries_only:
            conds += [Order.fulfillment == "PICKUP", Order.status.in_(P.DRIVER_STATUSES)]
        counts = dict(self.db.execute(select(Order.status, func.count()).where(*conds).group_by(Order.status)).all())
        return {s: counts.get(s, 0) for s in PIPELINE}

    def top_customers(self, start: datetime, end: datetime, limit: int = 10) -> list[dict]:
        rows = self.db.execute(
            select(Customer.id, Customer.name, Customer.phone, func.count(), func.sum(Order.total))
            .join(Order, Order.customer_id == Customer.id)
            .where(Order.business_id == self.bid, LIVE, Order.created_at >= start, Order.created_at < end)
            .group_by(Customer.id, Customer.name, Customer.phone)
            .order_by(func.sum(Order.total).desc(), Customer.name).limit(limit)).all()
        return [{"id": i, "name": n, "phone": p, "orders": c, "spend": int(v)} for i, n, p, c, v in rows]

    # ---- dashboard ----------------------------------------------------------------------------------------------
    def dashboard(self, role: str) -> dict:
        caps = P.capabilities(role)
        now = self.now
        today = resolve("today", now=now)
        tomorrow = today.end
        biz = Order.business_id == self.bid
        driver = "orders.deliveries_only" in caps

        counts = self.db.execute(select(
            func.count().filter(and_(Order.status.in_(PRE_READY), Order.due_at < now)),
            func.count().filter(and_(Order.status == S.NEW, Order.source == "MARKETPLACE")),
            func.count().filter(and_(Order.status.in_(PRE_READY), Order.due_at >= now, Order.due_at < tomorrow)),
            func.count().filter(and_(Order.status.in_(PRE_READY), Order.due_at >= now,
                                     Order.due_at < now + timedelta(hours=DUE_SOON_HOURS))),
            func.count().filter(Order.status.in_(PROCESSING)),
            func.count().filter(Order.status == S.READY),
            func.count().filter(and_(Order.status == S.READY, Order.payment_status.in_(UNPAID))),
            func.count().filter(and_(Order.fulfillment == "PICKUP", Order.status.in_([S.ACCEPTED, S.AWAITING_PICKUP]),
                                     Order.pickup_window_start < tomorrow)),
            func.count().filter(and_(Order.fulfillment == "PICKUP", Order.status.in_([S.READY, S.OUT_FOR_DELIVERY]))),
            func.count().filter(and_(Order.status == S.READY, Order.fulfillment == "DROP_OFF",
                                     Order.ready_at < now - timedelta(hours=UNCOLLECTED_HOURS))),
        ).where(biz)).one()
        (overdue, mp_new, due_today, due_soon, processing, ready, ready_unpaid, pickups, deliveries, uncollected) = counts
        stuck = self._scalar(select(func.count()).select_from(Payment).join(Order, Order.id == Payment.order_id).where(
            biz, Payment.status == "PROCESSING", Payment.updated_at < now - timedelta(minutes=STUCK_PAYMENT_MINUTES)))

        has_orders = bool(self.db.scalar(select(exists().where(biz))))
        out: dict = {"business": {"name": self.business.name, "area": self.business.area},
                     "local_date": today.start_date.isoformat(), "role": role, "capabilities": sorted(caps),
                     "has_orders": has_orders, "first_run": None if has_orders else self.first_run()}

        money = "money.view" in caps
        attention = []

        def add(key, count, severity, path, query=None, **extra):
            if count:
                attention.append({"key": key, "count": count, "severity": severity, "path": path, "query": query or {},
                                  **extra})

        if not driver:
            add("overdue", overdue, "critical", "/app/orders", {"due": "overdue"})
            add("marketplace_new", mp_new, "warning", "/app/orders", {"view": "new", "source": "MARKETPLACE"})
        if money:
            add("payments_stuck", stuck, "warning", "/app/orders", {"payment": "processing"}, minutes=STUCK_PAYMENT_MINUTES)
        if not driver:
            add("due_today", due_today, "info", "/app/orders", {"due": "today"}, soon=due_soon, hours=DUE_SOON_HOURS)
        add("pickups_today", pickups, "info", "/app/orders", {"view": "delivery"})
        add("deliveries", deliveries, "info", "/app/orders", {"view": "delivery"})
        outstanding_now = self.outstanding() if money else None
        if money:
            add("outstanding", outstanding_now["count"], "info", "/app/payments", {}, amount=outstanding_now["amount"])
        if "customers.view" in caps:
            add("uncollected", uncollected, "info", "/app/orders", {"view": "ready", "due": "uncollected"},
                hours=UNCOLLECTED_HOURS)
        out["attention"] = attention
        out["pipeline"] = self.pipeline(deliveries_only=driver)
        out["today"] = {"processing": processing, "ready": ready, "due_today": due_today, "overdue": overdue,
                        "pickups": pickups, "deliveries": deliveries}

        if money:
            cur = self.order_totals(today.start, today.until)
            prev = self.order_totals(today.prev_start, today.prev_until)
            comparable = prev["orders"] >= MIN_COMPARE_ORDERS
            out["today"] |= {"orders": metric(cur["orders"], prev["orders"], comparable),
                             "sales": metric(cur["sales"], prev["sales"], comparable),
                             "collected": self.collections(today.start, today.until)["collected"],
                             "ready_unpaid": ready_unpaid, "outstanding": outstanding_now,
                             "compare_to": today.compare_to}
        else:
            out["today"]["orders"] = {"value": self._scalar(select(func.count()).where(
                biz, LIVE, Order.created_at >= today.start, Order.created_at < today.until)), "previous": None, "change_pct": None}

        if "performance.view" in caps and has_orders:
            out |= self.performance()
        return out

    def performance(self) -> dict:
        month = resolve("this_month", now=self.now)
        cur, prev = self.order_totals(month.start, month.until), self.order_totals(month.prev_start, month.prev_until)
        comparable = prev["orders"] >= MIN_COMPARE_ORDERS
        coll, prev_coll = self.collections(month.start, month.until), self.collections(month.prev_start, month.prev_until)
        cust, prev_cust = self.customers(month.start, month.until), self.customers(month.prev_start, month.prev_until)
        mp = self.marketplace(month.start, month.until, cur["orders"], cur["sales"])
        prev_mp = self.marketplace(month.prev_start, month.prev_until, prev["orders"], prev["sales"])
        today = self.now.astimezone(LOCAL_TZ).date()
        trend = self.daily(resolve("custom", today - timedelta(days=29), today, now=self.now))
        services = self.services(month.start, month.until, limit=5)
        ops = self.operations(month.start, month.until)
        return {
            "performance": {
                "period": month.out(),
                "sales": metric(cur["sales"], prev["sales"], comparable),
                "orders": metric(cur["orders"], prev["orders"], comparable),
                "average_order": metric(cur["average_order"], prev["average_order"], comparable),
                "collected": metric(coll["collected"], prev_coll["collected"], comparable),
                "trend": trend,
            },
            "marketplace": None if mp["status"] == "NOT_ENROLLED" and not mp["orders"] else {
                **mp, "sales_metric": metric(mp["sales"], prev_mp["sales"], prev_mp["orders"] >= MIN_COMPARE_ORDERS),
                "orders_metric": metric(mp["orders"], prev_mp["orders"], prev_mp["orders"] >= MIN_COMPARE_ORDERS)},
            "customers": {**cust, "new_metric": metric(cust["new"], prev_cust["new"], comparable),
                          "repeat_rate_metric": metric(cust["repeat_rate"] or 0, prev_cust["repeat_rate"], comparable)},
            "insights": self.insights(cur, prev, cust, services, mp, ops),
        }

    def insights(self, cur: dict, prev: dict, cust: dict, services: dict, mp: dict, ops: dict) -> list[dict]:
        """Plain, checkable statements from this laundry's own numbers. Each has a minimum-data rule."""
        out = []
        week = self.weekdays()
        total = sum(week["orders"])
        if total >= 30 and week["active_weeks"] >= 4:
            busiest = max(range(7), key=lambda d: week["orders"][d])
            if week["orders"][busiest] > 1.15 * total / 7:
                out.append({"key": "busiest_day", "weekday": busiest, "average": week["average"][busiest]})
        if cur["orders"] >= MIN_INSIGHT_ORDERS and services["by_revenue"]:
            top = services["by_revenue"][0]
            out.append({"key": "top_service", "name": top["name"], "share": top["share_revenue"]})
        if cur["orders"] >= MIN_INSIGHT_ORDERS and mp["orders"]:
            out.append({"key": "marketplace_share", "share": mp["share_orders"]})
        if cur["orders"] >= MIN_INSIGHT_ORDERS and prev["orders"] >= MIN_INSIGHT_ORDERS and prev["average_order"]:
            change = round((cur["average_order"] - prev["average_order"]) * 100 / prev["average_order"], 1)
            if abs(change) >= 3:
                out.append({"key": "aov_up" if change > 0 else "aov_down", "change": abs(change),
                            "value": cur["average_order"], "previous": prev["average_order"]})
        if cust["multi_order"] >= 3:
            out.append({"key": "repeat_customers", "count": cust["multi_order"]})
        if ops["ready_late"] >= 1:
            out.append({"key": "late_orders", "count": ops["ready_late"]})
        return out

    def first_run(self) -> list[dict]:
        b = self.business
        services = self._scalar(select(func.count()).where(Service.business_id == b.id, Service.active.is_(True)))
        hours = bool(self.db.scalar(select(exists().where(BusinessHours.business_id == b.id, BusinessHours.closed.is_(False)))))
        staff = bool(self.db.scalar(select(exists().where(User.business_id == b.id))))
        account = self.db.scalar(select(MarketplaceAccount.status).where(MarketplaceAccount.business_id == b.id))
        return [
            {"key": "business", "done": True, "path": "/app/settings"},
            {"key": "location", "done": bool(b.address and b.latitude is not None), "path": "/app/settings"},
            {"key": "services", "done": services > 0, "path": "/app/services"},
            {"key": "hours", "done": hours, "path": "/app/settings"},
            {"key": "first_order", "done": False, "path": "/app/orders/new"},
            {"key": "staff", "done": staff, "path": "/app/settings"},
            {"key": "marketplace", "done": account not in (None, "NOT_ENROLLED", "REJECTED"), "path": "/app/marketplace"},
        ]

    # ---- reports ------------------------------------------------------------------------------------------------
    SECTIONS = {
        "daily": ["summary", "day_book", "money", "payments", "sources", "operations", "customers", "marketplace", "day_close"],
        "weekly": ["summary", "money", "operations", "customers", "marketplace", "daily", "services"],
        "monthly": ["summary", "money", "payments", "marketplace", "services", "customers", "top_customers", "operations",
                    "daily", "weekdays", "insights"],
        "sales": ["summary", "money", "daily", "services", "sources"],
        "orders": ["summary", "day_book", "sources", "operations", "daily"],
        "customers": ["summary", "customers", "top_customers"],
        "marketplace": ["summary", "marketplace", "daily"],
        "payments": ["summary", "money", "payments", "daily"],
    }
    DEFAULT_PERIOD = {"daily": "today", "weekly": "this_week", "monthly": "this_month", "sales": "this_month",
                      "orders": "this_month", "customers": "this_month", "marketplace": "this_month", "payments": "this_month"}

    def report(self, kind: str, period: Period) -> dict:
        start, until = period.start, period.until
        cur, prev = self.order_totals(start, until), self.order_totals(period.prev_start, period.prev_until)
        comparable = prev["orders"] >= MIN_COMPARE_ORDERS
        coll, prev_coll = self.collections(start, until), self.collections(period.prev_start, period.prev_until)
        cust, prev_cust = self.customers(start, until), self.customers(period.prev_start, period.prev_until)
        mp = self.marketplace(start, until, cur["orders"], cur["sales"])
        prev_mp = self.marketplace(period.prev_start, period.prev_until, prev["orders"], prev["sales"])
        ops = self.operations(start, until)
        services = self.services(start, until)
        outstanding_period = self.outstanding(start, until)
        sections = self.SECTIONS[kind]
        data: dict = {
            "kind": kind, "sections": sections, "period": period.out(), "generated_at": self.now.isoformat(),
            "business": {"name": self.business.name, "branch": ", ".join(x for x in (self.business.address, self.business.area) if x)},
            "summary": {
                "sales": metric(cur["sales"], prev["sales"], comparable),
                "orders": metric(cur["orders"], prev["orders"], comparable),
                "average_order": metric(cur["average_order"], prev["average_order"], comparable),
                "collected": metric(coll["collected"], prev_coll["collected"], comparable),
                "customers": metric(cur["customers"], prev["customers"], comparable),
                "new_customers": metric(cust["new"], prev_cust["new"], comparable),
                "returning_customers": metric(cust["returning"], prev_cust["returning"], comparable),
                "repeat_rate": metric(cust["repeat_rate"] or 0, prev_cust["repeat_rate"], comparable),
                "marketplace_sales": metric(mp["sales"], prev_mp["sales"], prev_mp["orders"] >= MIN_COMPARE_ORDERS),
                "marketplace_orders": metric(mp["orders"], prev_mp["orders"], prev_mp["orders"] >= MIN_COMPARE_ORDERS),
                "on_time_rate": ops["on_time_rate"],
                "outstanding_now": self.outstanding(),
                "comparable": comparable,
            },
            "money": {"sales": cur["sales"], "discounts": cur["discounts"], "collected": coll["collected"],
                      "refunded": coll["refunded"], "net_collected": coll["net_collected"],
                      "unpaid_from_period": outstanding_period, "outstanding_now": self.outstanding()},
            "payments": coll["by_method"],
            "sources": self.sources(start, until),
            "operations": {**ops, "cancellation_rate": pct(cur["cancelled"], cur["created"])},
            "customers": cust,
            "marketplace": mp,
            "services": services,
        }
        if "day_book" in sections:
            completed = self._scalar(select(func.count()).where(Order.business_id == self.bid, Order.completed_at >= start,
                                                                Order.completed_at < until))
            data["day_book"] = {"opening": self.open_at(start), "new": cur["created"], "completed": completed,
                                "cancelled": cur["cancelled"], "carried_forward": self.open_at(until)}
        if "daily" in sections:
            data["daily"] = self.daily(period)
        if "weekdays" in sections:
            data["weekdays"] = self.weekdays()
        if "top_customers" in sections:
            data["top_customers"] = self.top_customers(start, until)
        if "insights" in sections:
            data["insights"] = self.insights(cur, prev, cust, self.services(start, until, limit=5), mp, ops)
        if "day_close" in sections:
            data["day_close"] = self.day_close_view(period, coll) if period.days == 1 else None
        return data

    # ---- end of day -----------------------------------------------------------------------------------------------
    def day_close_view(self, period: Period, coll: dict | None = None) -> dict:
        coll = coll or self.collections(period.start, period.until)
        record = self.db.scalar(select(DayClose).where(DayClose.business_id == self.bid,
                                                       DayClose.business_date == period.start_date))
        closer = self.db.get(User, record.closed_by) if record else None
        return {"date": period.start_date.isoformat(), "expected_cash": coll["by_method"]["CASH"]["amount"],
                "expected_mobile_money": coll["by_method"]["MOBILE_MONEY"]["amount"], "expected_total": coll["collected"],
                "outstanding_now": self.outstanding(), "carried_forward": self.open_at(period.until),
                "can_close": period.end <= self.now or period.kind == "today",
                "closed": None if not record else {
                    "closed_at": record.closed_at, "closed_by": closer.full_name if closer else None,
                    "expected_cash": record.expected_cash, "counted_cash": record.counted_cash,
                    "variance": None if record.counted_cash is None else record.counted_cash - record.expected_cash,
                    "note": record.note}}


def business_date_period(day: date, now: datetime | None = None) -> Period:
    return resolve("custom", day, day, now=now)


def case_due_state(now: datetime):
    """SQL expression labelling an order's urgency: OVERDUE, DUE_SOON, DUE_TODAY or NULL."""
    tomorrow = resolve("today", now=now).end
    pre_ready = Order.status.in_(PRE_READY)
    return case(
        (and_(pre_ready, Order.due_at < now), "OVERDUE"),
        (and_(pre_ready, Order.due_at < now + timedelta(hours=DUE_SOON_HOURS)), "DUE_SOON"),
        (and_(pre_ready, Order.due_at < tomorrow), "DUE_TODAY"),
        else_=None)
