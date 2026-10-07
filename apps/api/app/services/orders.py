import secrets
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..core.errors import AppError, not_found
from ..domain import order_states as S
from ..domain.clock import as_utc, now_utc
from ..domain.money import percentage_of
from ..domain.phone import normalize_tz_phone
from ..models import (
    Address,
    Business,
    Commission,
    Customer,
    MarketplaceAccount,
    Order,
    OrderItem,
    OrderStatusEvent,
    Payment,
    Review,
    Service,
    User,
)
from ..schemas.business import BusinessOrderCreate
from ..schemas.orders import CartItem, CustomerOrderCreate
from .audit import audit
from .marketplace import MarketplaceService
from .notifications import notify_status
from .payments import PaymentService, payment_out

_ALPHABET = "ACDEFGHJKMNPQRTUVWXY3479"  # no 0/O, 1/I/L, 2/Z, 5/S, 6/B, 8 — easy to read over the phone


def new_order_number() -> str:
    return "LN-" + "".join(secrets.choice(_ALPHABET) for _ in range(6))


def customer_for_user(db: Session, user: User) -> Customer:
    record = db.scalar(select(Customer).where(Customer.user_id == user.id))
    if not record:
        raise AppError(409, "PROFILE_INCOMPLETE", "Customer profile not found. Please sign in again.")
    return record


class OrderService:
    def __init__(self, db: Session):
        self.db = db
        self.market = MarketplaceService(db)

    # ---- creation --------------------------------------------------------------------------------------------
    def _insert(self, order: Order) -> Order:
        """Inserts with a random human-readable number, retrying the (rare) collision."""
        for _ in range(5):
            order.order_number = new_order_number()
            try:
                with self.db.begin_nested():
                    self.db.add(order)
                    self.db.flush()
                return order
            except IntegrityError as exc:
                if "order_number" not in str(exc.orig).lower():
                    raise
        raise AppError(503, "TRY_AGAIN", "Could not allocate an order number. Please retry.")

    def create_marketplace_order(self, user: User, payload: CustomerOrderCreate, idempotency_key: str) -> tuple[Order, bool]:
        customer = customer_for_user(self.db, user)
        existing = self.db.scalar(select(Order).where(Order.customer_id == customer.id, Order.idempotency_key == idempotency_key))
        if existing:
            return existing, False
        if not user.full_name:
            raise AppError(409, "PROFILE_INCOMPLETE", "Please add your name before placing an order")

        business, account = self.market.visible_business(payload.laundry_slug)
        quote = self.market.quote(business, payload.items, payload.fulfillment)
        if quote.unavailable:
            raise AppError(409, "SERVICE_UNAVAILABLE", "Some services are no longer available", {"quote": quote.out()})
        if payload.expected_total is not None and payload.expected_total != quote.total:
            raise AppError(409, "PRICE_CHANGED", "Prices have changed since you added these items", {"quote": quote.out()})

        order = Order(business_id=business.id, customer_id=customer.id, source="MARKETPLACE", status=S.NEW,
                      fulfillment=payload.fulfillment, payment_method=payload.payment_method, payment_status="PENDING",
                      subtotal=quote.subtotal, delivery_fee=quote.delivery_fee, total=quote.total, notes=payload.notes,
                      idempotency_key=idempotency_key)
        if payload.fulfillment == "PICKUP":
            self._apply_pickup(order, business, account, user, payload)
        elif payload.pickup_window_start:
            order.pickup_window_start = payload.pickup_window_start  # optional drop-off time

        for line in quote.lines:
            order.items.append(OrderItem(service_id=line["service_id"], name=line["name"], pricing_model=line["pricing_model"],
                                         unit_price=line["unit_price"], quantity=line["quantity"], line_total=line["line_total"],
                                         position=line["position"]))
        order.events.append(OrderStatusEvent(from_status=None, to_status=S.NEW, actor_id=user.id))
        try:
            self._insert(order)
        except IntegrityError:
            # Same idempotency key submitted concurrently: the other request won, return its order.
            self.db.rollback()
            winner = self.db.scalar(select(Order).where(Order.customer_id == customer.id, Order.idempotency_key == idempotency_key))
            if winner:
                return winner, False
            raise
        self.db.add(Payment(order_id=order.id, method=payload.payment_method, amount=order.total, status="PENDING"))
        audit(self.db, user.id, "ORDER_PLACED", "order", order.id, business_id=business.id, total=order.total)
        self.db.commit()
        return order, True

    def _apply_pickup(self, order: Order, business: Business, account: MarketplaceAccount, user: User, payload: CustomerOrderCreate):
        if payload.address_id:
            saved = self.db.scalar(select(Address).where(Address.id == payload.address_id, Address.user_id == user.id))
            if not saved:
                raise not_found("Address")
            line, area, notes, lat, lng = saved.line, saved.area, saved.notes, saved.latitude, saved.longitude
        elif payload.address:
            a = payload.address
            line, area, notes, lat, lng = a.line, a.area, a.notes, a.latitude, a.longitude
        else:
            raise AppError(422, "ADDRESS_REQUIRED", "A pickup address is required")
        if lat is not None and lng is not None and business.latitude is not None:
            from ..database import _haversine_km  # same formula as the SQLite geo function; precision is ample here
            if _haversine_km(lat, lng, business.latitude, business.longitude) > float(account.pickup_radius_km):
                raise AppError(409, "OUTSIDE_PICKUP_AREA", "This address is outside the laundry's pickup area")
        if not payload.pickup_window_start:
            raise AppError(422, "PICKUP_TIME_REQUIRED", "Choose a pickup time")
        requested = as_utc(payload.pickup_window_start)
        slot = next((s for s in self.market.pickup_slots(business, days=7)
                     if as_utc(datetime.fromisoformat(s["start"])) == requested), None)
        if not slot:
            raise AppError(409, "PICKUP_SLOT_UNAVAILABLE", "That pickup time is no longer available")
        order.pickup_address = f"{line}, {area}".strip(", ") if area and area not in line else line
        order.pickup_notes, order.pickup_latitude, order.pickup_longitude = notes or None, lat, lng
        order.pickup_window_start = requested
        order.pickup_window_end = as_utc(datetime.fromisoformat(slot["end"]))

    def create_business_order(self, business: Business, actor: User, payload: BusinessOrderCreate) -> Order:
        try:
            phone = normalize_tz_phone(payload.phone)
        except ValueError as exc:
            raise AppError(422, "INVALID_PHONE", str(exc)) from exc
        customer = self.db.scalar(select(Customer).where(Customer.phone == phone))
        if not customer:
            customer = Customer(name=payload.customer_name, phone=phone)
            self.db.add(customer)
            self.db.flush()
        order = Order(business_id=business.id, customer_id=customer.id, source=payload.source, status=S.NEW,
                      fulfillment=payload.fulfillment, payment_method=payload.payment_method, notes=payload.notes)
        if payload.items:
            quote = self.market.quote(business, payload.items, "DROP_OFF")
            if quote.unavailable:
                raise AppError(409, "SERVICE_UNAVAILABLE", "Some services are not active", {"quote": quote.out()})
            for line in quote.lines:
                order.items.append(OrderItem(service_id=line["service_id"], name=line["name"], pricing_model=line["pricing_model"],
                                             unit_price=line["unit_price"], quantity=line["quantity"],
                                             line_total=line["line_total"], position=line["position"]))
            order.subtotal = order.total = quote.subtotal
        elif payload.total:
            order.subtotal = order.total = payload.total
        else:
            raise AppError(422, "ITEMS_REQUIRED", "Add at least one service or an order amount")
        # Counter orders are accepted the moment the laundry enters them.
        order.status = S.ACCEPTED
        order.events.append(OrderStatusEvent(from_status=None, to_status=S.NEW, actor_id=actor.id))
        order.events.append(OrderStatusEvent(from_status=S.NEW, to_status=S.ACCEPTED, actor_id=actor.id))
        self._insert(order)
        self.db.add(Payment(order_id=order.id, method=payload.payment_method, amount=order.total, status="PENDING"))
        audit(self.db, actor.id, "ORDER_CREATED", "order", order.id, source=payload.source, total=order.total)
        self.db.commit()
        return order

    # ---- lifecycle -------------------------------------------------------------------------------------------
    def transition(self, order: Order, target: str, actor: User, note: str = "") -> Order:
        target = target.upper()
        if target not in S.ALL_STATUSES:
            raise AppError(422, "INVALID_STATUS", f"Unknown status {target}")
        if not S.can_transition(order.status, target, order.fulfillment):
            raise AppError(409, "INVALID_TRANSITION", f"An order cannot move from {order.status} to {target}",
                           {"allowed": S.allowed_next(order.status, order.fulfillment)})
        if target == S.COMPLETED and order.payment_status != "PAID":
            raise AppError(409, "PAYMENT_REQUIRED", "Record the payment before completing this order")
        if target in (S.REJECTED, S.CANCELLED) and not note:
            raise AppError(422, "REASON_REQUIRED", "Give a reason so the customer knows what happened")
        return self._apply(order, target, actor.id, note)

    def _apply(self, order: Order, target: str, actor_id: str | None, note: str) -> Order:
        previous = order.status
        values = {"status": target, "updated_at": now_utc()}
        if target == S.COMPLETED:
            values["completed_at"] = now_utc()
        if target in (S.REJECTED, S.CANCELLED):
            values["cancel_reason"] = note
        # Optimistic concurrency: the update only applies if nobody moved the order since we read it.
        changed = self.db.execute(update(Order).where(Order.id == order.id, Order.status == previous).values(**values)).rowcount
        if changed != 1:
            self.db.rollback()
            raise AppError(409, "STALE_ORDER", "This order was updated by someone else. Refresh and try again.")
        self.db.add(OrderStatusEvent(order_id=order.id, from_status=previous, to_status=target, actor_id=actor_id, note=note or None))
        self.db.refresh(order)
        if target == S.COMPLETED:
            self._record_commission(order)
        if target in (S.REJECTED, S.CANCELLED):
            payment = PaymentService(self.db).latest(order.id)
            if payment and payment.status in ("PENDING", "PROCESSING"):
                payment.status, payment.failure_reason = "FAILED", "ORDER_CLOSED"
                order.payment_status = "FAILED"
        notify_status(self.db, order, target)
        audit(self.db, actor_id, "ORDER_STATUS_CHANGED", "order", order.id, from_status=previous, to_status=target)
        self.db.commit()
        self.db.refresh(order)
        return order

    def _record_commission(self, order: Order) -> None:
        if order.source != "MARKETPLACE":
            return
        account = self.db.scalar(select(MarketplaceAccount).where(MarketplaceAccount.business_id == order.business_id))
        rate = Decimal(account.commission_rate) if account else Decimal("0")
        # Commission is charged on the laundry services, not on the pickup fee passed through to the customer.
        self.db.add(Commission(order_id=order.id, business_id=order.business_id, rate=rate, base_amount=order.subtotal,
                               amount=percentage_of(order.subtotal, rate)))

    def customer_cancel(self, order: Order, user: User, reason: str) -> Order:
        if not S.customer_can_cancel(order.status):
            raise AppError(409, "CANNOT_CANCEL", "This order can no longer be cancelled. Contact the laundry.")
        return self._apply(order, S.CANCELLED, user.id, reason or "Cancelled by customer")

    def customer_confirm(self, order: Order, user: User) -> Order:
        if order.status != S.DELIVERED:
            raise AppError(409, "INVALID_TRANSITION", "Only delivered orders can be confirmed")
        if order.payment_status != "PAID":
            raise AppError(409, "PAYMENT_REQUIRED", "The laundry still needs to confirm your payment")
        return self._apply(order, S.COMPLETED, user.id, "Confirmed by customer")

    # ---- queries ---------------------------------------------------------------------------------------------
    def customer_order(self, user: User, order_id: str) -> Order:
        customer = customer_for_user(self.db, user)
        order = self.db.scalar(select(Order).where(Order.id == order_id, Order.customer_id == customer.id))
        if not order:
            raise not_found("Order")
        return order

    def reorder_quote(self, user: User, order: Order) -> dict:
        business = self.db.get(Business, order.business_id)
        try:
            business, _ = self.market.visible_business(business.slug)
        except AppError:
            raise AppError(409, "LAUNDRY_UNAVAILABLE", "This laundry is not taking marketplace orders right now") from None
        current = {s.id: s for s in self.db.scalars(select(Service).where(Service.business_id == business.id))}
        lines, changes = [], []
        for item in order.items:
            s = current.get(item.service_id) if item.service_id else None
            if not s or not s.active:
                changes.append({"type": "UNAVAILABLE", "name": item.name})
                continue
            if s.price != item.unit_price:
                changes.append({"type": "PRICE_CHANGED", "name": s.name, "old_price": item.unit_price, "new_price": s.price})
            lines.append(CartItem(service_id=s.id, quantity=Decimal(item.quantity)))
        quote = self.market.quote(business, lines, "DROP_OFF") if lines else None
        return {"laundry": {"slug": business.slug, "name": business.name, "pickup_enabled": business.pickup_enabled},
                "quote": quote.out() if quote else None, "changes": changes}


def order_summary(order: Order, business: Business | None = None) -> dict:
    business = business or order.business
    return {"id": order.id, "order_number": order.order_number, "status": order.status, "fulfillment": order.fulfillment,
            "payment_status": order.payment_status, "payment_method": order.payment_method, "total": order.total,
            "item_count": float(sum(Decimal(i.quantity) for i in order.items if i.pricing_model == "PER_ITEM")),
            "items_preview": [i.name for i in order.items[:3]], "created_at": order.created_at,
            "pickup_window_start": order.pickup_window_start, "source": order.source,
            "laundry": {"id": business.id, "slug": business.slug, "name": business.name, "area": business.area,
                        "cover_image_url": business.cover_image_url}}


def order_detail(db: Session, order: Order, audience: str) -> dict:
    review = db.scalar(select(Review).where(Review.order_id == order.id))
    payment = PaymentService(db).latest(order.id)
    data = {
        **order_summary(order),
        "subtotal": order.subtotal, "delivery_fee": order.delivery_fee, "notes": order.notes,
        "pickup_address": order.pickup_address, "pickup_notes": order.pickup_notes,
        "pickup_window_end": order.pickup_window_end, "cancel_reason": order.cancel_reason,
        "completed_at": order.completed_at, "updated_at": order.updated_at,
        "items": [{"service_id": i.service_id, "name": i.name, "pricing_model": i.pricing_model, "unit_price": i.unit_price,
                   "quantity": float(i.quantity), "line_total": i.line_total} for i in order.items],
        "events": [{"status": e.to_status, "from_status": e.from_status, "note": e.note, "at": e.created_at} for e in order.events],
        "stages": S.stage_for_customer(order.status, order.fulfillment),
        "payment": payment_out(payment),
        "review": {"rating": review.rating, "comment": review.comment, "status": review.status} if review else None,
        "can_cancel": S.customer_can_cancel(order.status),
        "can_review": order.status in (S.DELIVERED, S.COMPLETED) and review is None and order.source == "MARKETPLACE",
        "can_confirm": order.status == S.DELIVERED and order.payment_status == "PAID",
        "can_pay": order.payment_method == "MOBILE_MONEY" and order.payment_status in ("PENDING", "FAILED")
        and order.status not in (S.CANCELLED, S.REJECTED),
    }
    if audience == "business":
        customer = order.customer
        data["customer"] = {"id": customer.id, "name": customer.name, "phone": customer.phone}
        data["allowed_next"] = S.allowed_next(order.status, order.fulfillment)
        data["pickup_latitude"], data["pickup_longitude"] = order.pickup_latitude, order.pickup_longitude
    return data


def count_since(db: Session, business_id: str, hours: int) -> int:
    return db.scalar(select(func.count(Order.id)).where(Order.business_id == business_id,
                                                        Order.created_at >= now_utc() - timedelta(hours=hours))) or 0
