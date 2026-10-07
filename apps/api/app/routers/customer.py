import json
from typing import Literal

from fastapi import APIRouter, Depends, Header, Query, Response
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..core.errors import AppError, not_found
from ..database import get_db
from ..dependencies import require_customer
from ..domain import order_states as S
from ..domain.clock import now_utc
from ..domain.phone import normalize_tz_phone
from ..models import Address, Business, DeviceToken, Favourite, Notification, Order, User
from ..schemas.orders import AddressCreate, CancelRequest, CustomerOrderCreate, DeviceRegistration, MobileMoneyPayment, ReviewCreate
from ..services.marketplace import DiscoveryQuery, MarketplaceService
from ..services.orders import OrderService, customer_for_user, order_detail, order_summary
from ..services.payments import PaymentService, payment_out
from ..services.reviews import ReviewService
from .common import Page, page_params, paginate

router = APIRouter(prefix="/customer", tags=["Customer"])

GROUPS = {"active": S.ACTIVE - {S.COMPLETED}, "completed": {S.COMPLETED}, "cancelled": {S.CANCELLED, S.REJECTED}}


# ---- orders ------------------------------------------------------------------------------------------------------
@router.get("/orders")
def list_orders(group: Literal["active", "completed", "cancelled"] | None = None, page: Page = Depends(page_params),
                user: User = Depends(require_customer), db: Session = Depends(get_db)):
    customer = customer_for_user(db, user)
    stmt = select(Order).where(Order.customer_id == customer.id, Order.source == "MARKETPLACE")
    if group:
        stmt = stmt.where(Order.status.in_(GROUPS[group]))
    return paginate(db, stmt.order_by(Order.created_at.desc()), page, order_summary)


@router.post("/orders", status_code=201)
def place_order(payload: CustomerOrderCreate, response: Response,
                idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=64),
                user: User = Depends(require_customer), db: Session = Depends(get_db)):
    order, created = OrderService(db).create_marketplace_order(user, payload, idempotency_key)
    if not created:
        response.status_code = 200
    return order_detail(db, order, "customer")


@router.get("/orders/{order_id}")
def get_order(order_id: str, user: User = Depends(require_customer), db: Session = Depends(get_db)):
    return order_detail(db, OrderService(db).customer_order(user, order_id), "customer")


@router.post("/orders/{order_id}/cancel")
def cancel_order(order_id: str, payload: CancelRequest, user: User = Depends(require_customer), db: Session = Depends(get_db)):
    service = OrderService(db)
    return order_detail(db, service.customer_cancel(service.customer_order(user, order_id), user, payload.reason), "customer")


@router.post("/orders/{order_id}/confirm")
def confirm_order(order_id: str, user: User = Depends(require_customer), db: Session = Depends(get_db)):
    """Customer confirms they received their laundry: DELIVERED → COMPLETED."""
    service = OrderService(db)
    return order_detail(db, service.customer_confirm(service.customer_order(user, order_id), user), "customer")


@router.post("/orders/{order_id}/review", status_code=201)
def review_order(order_id: str, payload: ReviewCreate, user: User = Depends(require_customer), db: Session = Depends(get_db)):
    order = OrderService(db).customer_order(user, order_id)
    review = ReviewService(db).create(order, user, payload.rating, payload.comment)
    return {"id": review.id, "rating": review.rating, "comment": review.comment, "status": review.status}


@router.get("/orders/{order_id}/reorder")
def reorder(order_id: str, user: User = Depends(require_customer), db: Session = Depends(get_db)):
    """Rebuilds the cart from a previous order using today's prices and availability; never reuses stale prices."""
    service = OrderService(db)
    return service.reorder_quote(user, service.customer_order(user, order_id))


@router.post("/orders/{order_id}/payments/mobile-money")
def pay_mobile_money(order_id: str, payload: MobileMoneyPayment, user: User = Depends(require_customer),
                     db: Session = Depends(get_db)):
    order = OrderService(db).customer_order(user, order_id)
    try:
        phone = normalize_tz_phone(payload.phone)
    except ValueError as exc:
        raise AppError(422, "INVALID_PHONE", str(exc)) from exc
    return payment_out(PaymentService(db).start_mobile_money(order, phone, user.id))


# ---- addresses ---------------------------------------------------------------------------------------------------
def address_out(a: Address) -> dict:
    return {"id": a.id, "label": a.label, "line": a.line, "area": a.area, "city": a.city, "notes": a.notes,
            "latitude": a.latitude, "longitude": a.longitude, "is_default": a.is_default}


@router.get("/addresses")
def list_addresses(user: User = Depends(require_customer), db: Session = Depends(get_db)):
    rows = db.scalars(select(Address).where(Address.user_id == user.id).order_by(Address.is_default.desc(), Address.created_at.desc()))
    return {"items": [address_out(a) for a in rows]}


@router.post("/addresses", status_code=201)
def add_address(payload: AddressCreate, user: User = Depends(require_customer), db: Session = Depends(get_db)):
    count = len(db.scalars(select(Address.id).where(Address.user_id == user.id)).all())
    if count >= 10:
        raise AppError(409, "TOO_MANY_ADDRESSES", "You can save up to 10 addresses")
    is_default = payload.is_default or count == 0
    if is_default:
        db.execute(update(Address).where(Address.user_id == user.id).values(is_default=False))
    address = Address(user_id=user.id, **payload.model_dump(exclude={"is_default"}), is_default=is_default)
    db.add(address)
    db.commit()
    return address_out(address)


@router.delete("/addresses/{address_id}", status_code=204)
def delete_address(address_id: str, user: User = Depends(require_customer), db: Session = Depends(get_db)):
    address = db.scalar(select(Address).where(Address.id == address_id, Address.user_id == user.id))
    if not address:
        raise not_found("Address")
    db.delete(address)
    db.commit()


# ---- favourites --------------------------------------------------------------------------------------------------
@router.get("/favourites")
def list_favourites(lat: float | None = Query(None, ge=-90, le=90), lng: float | None = Query(None, ge=-180, le=180),
                    user: User = Depends(require_customer), db: Session = Depends(get_db)):
    service = MarketplaceService(db)
    ids = set(db.scalars(select(Favourite.business_id).where(Favourite.user_id == user.id)))
    if not ids:
        return {"items": []}
    # Reuse discovery so favourites carry the same card shape; filter to the saved ids afterwards.
    result = service.discover(DiscoveryQuery(lat=lat, lng=lng, radius_km=50, page_size=50, favourite_ids=ids,
                                             sort="distance" if lat is not None else "rating"))
    return {"items": [x for x in result["items"] if x["id"] in ids]}


@router.put("/favourites/{slug}", status_code=204)
def add_favourite(slug: str, user: User = Depends(require_customer), db: Session = Depends(get_db)):
    business = db.scalar(select(Business).where(Business.slug == slug))
    if not business:
        raise not_found("Laundry")
    if not db.scalar(select(Favourite.id).where(Favourite.user_id == user.id, Favourite.business_id == business.id)):
        db.add(Favourite(user_id=user.id, business_id=business.id))
        db.commit()


@router.delete("/favourites/{slug}", status_code=204)
def remove_favourite(slug: str, user: User = Depends(require_customer), db: Session = Depends(get_db)):
    business = db.scalar(select(Business).where(Business.slug == slug))
    if business:
        fav = db.scalar(select(Favourite).where(Favourite.user_id == user.id, Favourite.business_id == business.id))
        if fav:
            db.delete(fav)
            db.commit()


# ---- notifications -----------------------------------------------------------------------------------------------
@router.get("/notifications")
def notifications(page: Page = Depends(page_params), user: User = Depends(require_customer), db: Session = Depends(get_db)):
    stmt = select(Notification).where(Notification.user_id == user.id).order_by(Notification.created_at.desc())
    return paginate(db, stmt, page, lambda n: {"id": n.id, "kind": n.kind, "order_id": n.order_id, "data": json.loads(n.data_json),
                                                "read": n.read_at is not None, "created_at": n.created_at})


@router.post("/notifications/read", status_code=204)
def mark_read(user: User = Depends(require_customer), db: Session = Depends(get_db)):
    db.execute(update(Notification).where(Notification.user_id == user.id, Notification.read_at.is_(None)).values(read_at=now_utc()))
    db.commit()


@router.post("/devices", status_code=204)
def register_device(payload: DeviceRegistration, user: User = Depends(require_customer), db: Session = Depends(get_db)):
    """Stores a push token for when a push provider is configured. Registering does not send anything."""
    existing = db.scalar(select(DeviceToken).where(DeviceToken.token == payload.token))
    if existing:
        existing.user_id, existing.platform = user.id, payload.platform
    else:
        db.add(DeviceToken(user_id=user.id, token=payload.token, platform=payload.platform))
    db.commit()

