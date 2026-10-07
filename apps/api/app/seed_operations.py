"""Ten weeks of believable FreshWash trading, so the business dashboard and reports have something real to show.

Pattern: Saturdays busiest, Sundays quiet, slow growth over the period, ~30 % marketplace orders, a core of
returning customers, cash and mobile money, the odd discount, a few late orders, a refund. Today's work is
spread across every stage, with some orders overdue, some due today, marketplace orders waiting for acceptance
and ready orders not yet collected. Development data only; idempotent (keyed on a marker customer).
"""
import random
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import select

from .domain import order_states as S
from .domain.clock import LOCAL_TZ, now_utc
from .domain.money import line_total, percentage_of
from .models import (
    Business,
    BusinessCustomer,
    Commission,
    Customer,
    Order,
    OrderItem,
    OrderStatusEvent,
    Payment,
    Service,
    User,
)
from .services.orders import new_order_number

MARKER_PHONE = "+255690000001"
FIRST = ["Amina", "Baraka", "Rehema", "Juma", "Neema", "Hassan", "Upendo", "Daudi", "Mwanaidi", "Omari", "Faraja", "Saida",
         "Elia", "Zuhura", "Khamis", "Imani", "Petro", "Asha", "Yusuf", "Halima", "Godfrey", "Mariam", "Selemani", "Furaha"]
LAST = ["Mushi", "Mwakalinga", "Kombo", "Massawe", "Ngowi", "Shirima", "Mrisho", "Lyimo", "Mbwana", "Kitwana", "Swai",
        "Mapunda", "Ndege", "Temba", "Chande", "Msuya"]
WEEKDAY_ORDERS = [7, 6, 7, 8, 9, 13, 4]  # Monday … Sunday
DAYS = 70


def _local(day, hour: float) -> datetime:
    return datetime.combine(day, datetime.min.time(), LOCAL_TZ).astimezone(now_utc().tzinfo) + timedelta(hours=hour)


def seed_operating_history(db) -> bool:
    business = db.scalar(select(Business).where(Business.slug == "freshwash-laundry-mikocheni"))
    if not business or db.scalar(select(Customer.id).where(Customer.phone == MARKER_PHONE)):
        return False
    rng = random.Random(4242)
    now = now_utc()
    today = now.astimezone(LOCAL_TZ).date()
    services = [s for s in db.scalars(select(Service).where(Service.business_id == business.id, Service.active.is_(True)))
                if s.price <= 15000]
    weights = [9 if s.name in ("Shirt", "Trouser") else 4 if s.pricing_model == "PER_KG" else 2 for s in services]

    # Customers: counter customers, plus app users who order through the marketplace.
    counter, app = [], []
    for i in range(70):
        name = f"{FIRST[i % len(FIRST)]} {LAST[(i * 7) % len(LAST)]}"
        phone = MARKER_PHONE if i == 0 else f"+25569{1000000 + i * 7919:07d}"[:13]
        if i % 3 == 0:
            user = User(phone=phone, role="CUSTOMER", full_name=name)
            db.add(user)
            db.flush()
            customer = Customer(user_id=user.id, name=name, phone=phone)
            app.append(customer)
        else:
            customer = Customer(name=name, phone=phone)
            counter.append(customer)
        db.add(customer)
    db.flush()
    seen: set[str] = set()
    regulars = counter[:12] + app[:6]  # the laundry's core

    def pick(pool: list[Customer]) -> Customer:
        if rng.random() < 0.55:
            core = [c for c in regulars if c in pool]
            if core:
                return rng.choice(core)
        fresh = [c for c in pool if c.id not in seen]
        return rng.choice(fresh if fresh and rng.random() < 0.6 else pool)

    refunded = stuck = False
    for back in range(DAYS, -1, -1):
        day = today - timedelta(days=back)
        growth = 0.85 + 0.3 * (DAYS - back) / DAYS
        count = max(1, round(WEEKDAY_ORDERS[day.weekday()] * growth + rng.uniform(-1.5, 1.5)))
        hours = sorted(rng.uniform(7.2, 19.5) for _ in range(count))
        for hour in hours:
            created = _local(day, hour)
            if created > now - timedelta(minutes=10):
                continue
            marketplace = rng.random() < 0.3
            customer = pick(app if marketplace else counter)
            seen.add(customer.id)
            source = "MARKETPLACE" if marketplace else rng.choices(["WALK_IN", "PHONE", "WHATSAPP"], [6, 2, 2])[0]
            pickup = marketplace and rng.random() < 0.6
            order = Order(order_number=new_order_number(), business_id=business.id, customer_id=customer.id, source=source,
                          fulfillment="PICKUP" if pickup else "DROP_OFF", created_at=created, status=S.NEW, discount=0,
                          payment_method="MOBILE_MONEY" if rng.random() < 0.4 else "CASH")
            chosen = list(dict.fromkeys(rng.choices(services, weights, k=rng.randint(1, 3))))
            for position, s in enumerate(chosen):
                qty = Decimal(rng.choice([2, 3, 4, 5, 6])) if s.pricing_model == "PER_KG" else Decimal(rng.randint(1, 6))
                order.items.append(OrderItem(service_id=s.id, name=s.name, pricing_model=s.pricing_model, unit_price=s.price,
                                             quantity=qty, line_total=line_total(s.price, qty), position=position))
            order.subtotal = sum(i.line_total for i in order.items)
            order.delivery_fee = business.pickup_fee if pickup else 0
            if not marketplace and rng.random() < 0.06:
                order.discount = min(order.subtotal // 2, rng.choice([500, 1000, 2000]))
            order.total = order.subtotal + order.delivery_fee - order.discount
            turnaround = max(s.turnaround_hours for s in chosen)
            start = created + timedelta(hours=3 if pickup else 0)
            order.due_at = start + timedelta(hours=turnaround)
            if pickup:
                order.pickup_window_start, order.pickup_window_end = created + timedelta(hours=2), start
                order.pickup_address = f"{rng.randint(1, 90)} Mikocheni B, Dar es Salaam"
            _progress(order, rng, now, start, turnaround, pickup, marketplace)
            order.updated_at = order.events[-1].created_at
            db.add(order)
            db.flush()

            paid_at = None
            if order.status == S.COMPLETED:
                paid_at = created if source == "WALK_IN" and rng.random() < 0.4 else order.completed_at - timedelta(minutes=5)
            elif order.status in (S.READY, S.DELIVERED, S.WASHING, S.IRONING) and source == "WALK_IN" and rng.random() < 0.3:
                paid_at = created
            status = "PAID" if paid_at else "PENDING"
            if order.status in (S.CANCELLED, S.REJECTED):
                status = "FAILED"
            payment = Payment(order_id=order.id, method=order.payment_method, amount=order.total, status=status,
                              paid_at=paid_at, created_at=created, updated_at=paid_at or created,
                              provider=("sandbox" if marketplace else "manual") if order.payment_method == "MOBILE_MONEY" else None,
                              failure_reason="ORDER_CLOSED" if status == "FAILED" else None)
            if not refunded and status == "PAID" and marketplace and back > 20:
                payment.status, payment.refunded_at = "REFUNDED", paid_at + timedelta(days=1)
                refunded = True
            if not stuck and back == 0 and order.payment_method == "MOBILE_MONEY" and marketplace and status == "PENDING":
                payment.status, payment.provider, payment.updated_at = "PROCESSING", "sandbox", now - timedelta(minutes=50)
                stuck = True
            order.payment_status = payment.status
            db.add(payment)
            if order.status == S.COMPLETED and marketplace:
                db.add(Commission(order_id=order.id, business_id=business.id, rate=Decimal("5.00"), base_amount=order.subtotal,
                                  amount=percentage_of(order.subtotal, Decimal("5.00")), created_at=order.completed_at))
    db.flush()
    first_orders = {}
    for cid, created in db.execute(select(Order.customer_id, Order.created_at).where(Order.business_id == business.id)):
        first_orders[cid] = min(created, first_orders.get(cid, created))
    linked = set(db.scalars(select(BusinessCustomer.customer_id).where(BusinessCustomer.business_id == business.id)))
    db.add_all([BusinessCustomer(business_id=business.id, customer_id=cid, created_at=at)
                for cid, at in first_orders.items() if cid not in linked])
    db.commit()
    return True


def _progress(order: Order, rng: random.Random, now: datetime, start: datetime, turnaround: int, pickup: bool,
              marketplace: bool) -> None:
    """Walks the order along the real state machine with plausible timings, stopping at `now`."""
    created = order.created_at
    if rng.random() < 0.05:
        closing = S.REJECTED if marketplace and rng.random() < 0.5 else S.CANCELLED
        _events(order, [(S.NEW, created), (closing, created + timedelta(minutes=rng.randint(10, 180)))])
        order.cancel_reason = "Customer changed plans" if closing == S.CANCELLED else "Fully booked today"
        if order.events[-1].created_at > now:
            order.events.pop()
        else:
            order.status = closing
        return
    if marketplace and now - created < timedelta(hours=3) and rng.random() < 0.6:
        _events(order, [(S.NEW, created)])  # still waiting for the laundry to accept
        return
    # Most orders are ready a little before the promise; about one in ten is late.
    ready_after = turnaround * (rng.uniform(1.05, 1.35) if rng.random() < 0.1 else rng.uniform(0.55, 0.95))
    ready = start + timedelta(hours=ready_after)
    accepted = created + timedelta(minutes=rng.randint(5, 40) if marketplace else 0)
    received = start + timedelta(minutes=rng.randint(10, 50)) if pickup else accepted
    span = ready - received
    plan = [(S.NEW, created), (S.ACCEPTED, accepted)]
    if pickup:
        plan.append((S.AWAITING_PICKUP, accepted + timedelta(minutes=5)))
    plan += [(S.RECEIVED, received), (S.WASHING, received + span * 0.15), (S.DRYING, received + span * 0.4),
             (S.IRONING, received + span * 0.6), (S.QUALITY_CHECK, received + span * 0.9), (S.READY, ready)]
    if pickup:
        out = ready + timedelta(hours=rng.uniform(1, 5))
        plan += [(S.OUT_FOR_DELIVERY, out), (S.DELIVERED, out + timedelta(minutes=rng.randint(20, 70)))]
    else:
        # Walk-in customers collect later; a few leave clothes for days.
        plan.append((S.DELIVERED, ready + timedelta(hours=rng.uniform(2, 30) if rng.random() < 0.9 else rng.uniform(60, 120))))
    plan.append((S.COMPLETED, plan[-1][1] + timedelta(minutes=2)))
    reached = [(status, at) for status, at in plan if at <= now]
    # Work in progress lags a little on busy days: some orders past their promise are still being processed.
    if len(reached) < len(plan) and reached[-1][0] in (S.WASHING, S.DRYING) and rng.random() < 0.5:
        order.due_at = min(order.due_at, now - timedelta(hours=rng.uniform(0.5, 6)))
    _events(order, reached)
    order.status = reached[-1][0]
    order.ready_at = next((at for status, at in reached if status == S.READY), None)
    if order.status == S.COMPLETED:
        order.completed_at = reached[-1][1]


def _events(order: Order, steps) -> None:
    previous = None
    for status, at in steps:
        order.events.append(OrderStatusEvent(from_status=previous, to_status=status, created_at=at))
        previous = status
