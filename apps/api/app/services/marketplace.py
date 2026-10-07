from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import and_, exists, func, literal, or_, select
from sqlalchemy.orm import Session

from ..core.errors import AppError, not_found
from ..domain.clock import LOCAL_TZ, now_local
from ..domain.money import line_total
from ..models import Business, BusinessHours, Favourite, MarketplaceAccount, Review, Service

# Curated neighbourhoods for manual location choice when GPS is denied or unavailable.
AREAS = [
    ("Mikocheni", -6.7690, 39.2470), ("Masaki", -6.7470, 39.2790), ("Oysterbay", -6.7740, 39.2850),
    ("Msasani", -6.7550, 39.2650), ("Sinza", -6.7790, 39.2230), ("Mwenge", -6.7680, 39.2240),
    ("Kinondoni", -6.7870, 39.2560), ("Upanga", -6.8080, 39.2830), ("Kariakoo", -6.8190, 39.2730),
    ("Mbezi Beach", -6.7180, 39.2260), ("Ubungo", -6.7920, 39.2100), ("Kigamboni", -6.8530, 39.3100),
    ("Mikocheni B", -6.7600, 39.2390), ("Kijitonyama", -6.7730, 39.2380), ("Ada Estate", -6.7890, 39.2730),
]

PICKUP_SLOT_HOURS = 2
PICKUP_LEAD_MINUTES = 60
MAX_RADIUS_KM = 50


def marketplace_visible():
    return and_(MarketplaceAccount.status == "ACTIVE", Business.status == "ACTIVE")


def _geography(lat_col, lng_col):
    return func.geography(func.ST_SetSRID(func.ST_MakePoint(lng_col, lat_col), 4326))


class Geo:
    """PostGIS geography distance expressions (indexed by ix_businesses_geog)."""

    def __init__(self, db: Session):
        self.db = db

    def distance_km(self, lat: float, lng: float):
        return func.ST_Distance(_geography(Business.latitude, Business.longitude), _geography(literal(lat), literal(lng))) / 1000.0

    def within_km(self, lat: float, lng: float, radius_km: float):
        here = _geography(literal(lat), literal(lng))
        return func.ST_DWithin(_geography(Business.latitude, Business.longitude), here, radius_km * 1000)


def open_now_clause(at: datetime | None = None):
    at = at or now_local()
    hm = at.strftime("%H:%M")
    return exists().where(BusinessHours.business_id == Business.id, BusinessHours.weekday == at.weekday(),
                          BusinessHours.closed.is_(False), BusinessHours.opens_at <= hm, BusinessHours.closes_at > hm)


def is_open(hours: list[BusinessHours], at: datetime | None = None) -> bool:
    at = at or now_local()
    hm = at.strftime("%H:%M")
    return any(h.weekday == at.weekday() and not h.closed and h.opens_at <= hm < h.closes_at for h in hours)


def hours_out(hours: list[BusinessHours]) -> list[dict]:
    return [{"weekday": h.weekday, "opens_at": h.opens_at, "closes_at": h.closes_at, "closed": h.closed} for h in hours]


def _min_price(model: str):
    return (select(func.min(Service.price)).where(Service.business_id == Business.id, Service.active.is_(True),
                                                  Service.pricing_model == model).correlate(Business).scalar_subquery())


@dataclass
class DiscoveryQuery:
    lat: float | None = None
    lng: float | None = None
    radius_km: float = 15
    q: str | None = None
    service: str | None = None
    open_now: bool = False
    pickup: bool = False
    min_rating: float | None = None
    sort: str | None = None
    page: int = 1
    page_size: int = 20
    favourite_ids: set[str] = field(default_factory=set)


class MarketplaceService:
    def __init__(self, db: Session):
        self.db = db
        self.geo = Geo(db)

    # ---- discovery -------------------------------------------------------------------------------------------
    def discover(self, p: DiscoveryQuery) -> dict:
        has_point = p.lat is not None and p.lng is not None
        distance = self.geo.distance_km(p.lat, p.lng) if has_point else literal(None)
        item_price, kg_price = _min_price("PER_ITEM"), _min_price("PER_KG")
        open_col = open_now_clause()
        stmt = (select(Business, MarketplaceAccount.pickup_radius_km, distance.label("distance_km"), open_col.label("open_now"),
                       item_price.label("item_price"), kg_price.label("kg_price"))
                .join(MarketplaceAccount, MarketplaceAccount.business_id == Business.id)
                .where(marketplace_visible()))
        if has_point:
            stmt = stmt.where(self.geo.within_km(p.lat, p.lng, min(p.radius_km, MAX_RADIUS_KM)))
        if p.q:
            term = f"%{p.q.strip()}%"
            stmt = stmt.where(or_(Business.name.ilike(term), Business.area.ilike(term),
                                  exists().where(Service.business_id == Business.id, Service.active.is_(True), Service.name.ilike(term))))
        if p.service:
            term = f"%{p.service.strip()}%"
            stmt = stmt.where(exists().where(Service.business_id == Business.id, Service.active.is_(True),
                                             or_(Service.category.ilike(term), Service.name.ilike(term))))
        if p.open_now:
            stmt = stmt.where(open_col)
        if p.pickup:
            stmt = stmt.where(Business.pickup_enabled.is_(True))
            if has_point:
                stmt = stmt.where(distance <= MarketplaceAccount.pickup_radius_km)
        if p.min_rating:
            stmt = stmt.where(Business.rating >= p.min_rating)

        sort = p.sort or ("distance" if has_point else "rating")
        if sort == "distance" and has_point:
            stmt = stmt.order_by(distance.asc(), Business.name)
        elif sort == "price":
            stmt = stmt.order_by(func.coalesce(item_price, kg_price).asc(), Business.name)
        else:
            stmt = stmt.order_by(Business.rating.desc(), Business.review_count.desc(), Business.name)

        total = self.db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
        rows = self.db.execute(stmt.offset((p.page - 1) * p.page_size).limit(p.page_size)).all()
        items = [self._card(b, radius, dist, bool(is_open), ip, kp, b.id in p.favourite_ids)
                 for b, radius, dist, is_open, ip, kp in rows]
        return {"items": items, "total": total, "page": p.page, "page_size": p.page_size,
                "location": {"lat": p.lat, "lng": p.lng, "radius_km": p.radius_km} if has_point else None}

    @staticmethod
    def _card(b: Business, radius, distance, open_now: bool, item_price, kg_price, favourite: bool) -> dict:
        distance = round(float(distance), 2) if distance is not None else None
        starting = {"amount": item_price, "unit": "PER_ITEM"} if item_price is not None else (
            {"amount": kg_price, "unit": "PER_KG"} if kg_price is not None else None)
        return {"id": b.id, "slug": b.slug, "name": b.name, "area": b.area, "city": b.city, "rating": float(b.rating),
                "review_count": b.review_count, "distance_km": distance, "open_now": open_now,
                "pickup_enabled": b.pickup_enabled, "pickup_radius_km": float(radius),
                "pickup_available": b.pickup_enabled and (distance is None or distance <= float(radius)),
                "starting_price": starting, "cover_image_url": b.cover_image_url, "cover_thumb_url": thumb(b.cover_image_url),
                "latitude": b.latitude, "longitude": b.longitude, "is_favourite": favourite}

    # ---- storefront ------------------------------------------------------------------------------------------
    def visible_business(self, slug: str) -> tuple[Business, MarketplaceAccount]:
        row = self.db.execute(select(Business, MarketplaceAccount).join(MarketplaceAccount)
                              .where(Business.slug == slug, marketplace_visible())).first()
        if not row:
            raise not_found("Laundry")
        return row[0], row[1]

    def storefront(self, slug: str, lat: float | None, lng: float | None, favourite_ids: set[str]) -> dict:
        business, account = self.visible_business(slug)
        services = list(self.db.scalars(select(Service).where(Service.business_id == business.id, Service.active.is_(True))
                                        .order_by(Service.sort_order, Service.name)))
        groups: dict[str, list] = {}
        for s in services:
            groups.setdefault(s.category, []).append(service_out(s))
        distance = None
        if lat is not None and lng is not None and business.latitude is not None:
            distance = self.db.scalar(select(self.geo.distance_km(lat, lng)).where(Business.id == business.id))
        reviews = self.recent_reviews(business.id, limit=5)
        turnaround = min((s.turnaround_hours for s in services), default=None)
        card = self._card(business, account.pickup_radius_km, distance, is_open(business.hours),
                          min((s.price for s in services if s.pricing_model == "PER_ITEM"), default=None),
                          min((s.price for s in services if s.pricing_model == "PER_KG"), default=None),
                          business.id in favourite_ids)
        return {**card, "description": business.description, "address": business.address, "phone": business.phone,
                "pickup_fee": business.pickup_fee, "fastest_turnaround_hours": turnaround,
                "hours": hours_out(business.hours), "today": self._today(business.hours),
                "service_groups": [{"category": k, "services": v} for k, v in groups.items()], "reviews": reviews}

    @staticmethod
    def _today(hours: list[BusinessHours]) -> dict | None:
        wd = now_local().weekday()
        h = next((x for x in hours if x.weekday == wd), None)
        return {"opens_at": h.opens_at, "closes_at": h.closes_at, "closed": h.closed} if h else None

    def recent_reviews(self, business_id: str, limit: int = 20, offset: int = 0) -> list[dict]:
        rows = self.db.scalars(select(Review).where(Review.business_id == business_id, Review.status == "PUBLISHED")
                               .order_by(Review.created_at.desc()).offset(offset).limit(limit))
        return [{"id": r.id, "rating": r.rating, "comment": r.comment, "author": first_name(r.author_name),
                 "created_at": r.created_at} for r in rows]

    # ---- pickup windows --------------------------------------------------------------------------------------
    def pickup_slots(self, business: Business, days: int = 3, now: datetime | None = None) -> list[dict]:
        now = now or now_local()
        earliest = now + timedelta(minutes=PICKUP_LEAD_MINUTES)
        by_day = {h.weekday: h for h in business.hours}
        slots = []
        for offset in range(days):
            day = (now + timedelta(days=offset)).date()
            h = by_day.get(day.weekday())
            if not h or h.closed:
                continue
            start = datetime.combine(day, time.fromisoformat(h.opens_at), LOCAL_TZ)
            close = datetime.combine(day, time.fromisoformat(h.closes_at), LOCAL_TZ)
            while start + timedelta(hours=PICKUP_SLOT_HOURS) <= close:
                if start >= earliest:
                    slots.append({"start": start.isoformat(), "end": (start + timedelta(hours=PICKUP_SLOT_HOURS)).isoformat()})
                start += timedelta(hours=PICKUP_SLOT_HOURS)
        return slots

    # ---- pricing ---------------------------------------------------------------------------------------------
    def quote(self, business: Business, items: list, fulfillment: str) -> "Quote":
        ids = [i.service_id for i in items]
        services = {s.id: s for s in self.db.scalars(select(Service).where(Service.id.in_(ids), Service.business_id == business.id))}
        quote = Quote()
        merged: dict[str, Decimal] = {}
        for item in items:  # the same service twice in one cart is one line
            merged[item.service_id] = merged.get(item.service_id, Decimal(0)) + Decimal(item.quantity)
        for position, (service_id, qty) in enumerate(merged.items()):
            s = services.get(service_id)
            if not s or not s.active:
                quote.unavailable.append(service_id)
                continue
            if s.pricing_model in ("PER_ITEM", "PACKAGE") and qty != qty.to_integral_value():
                raise AppError(422, "INVALID_QUANTITY", f"{s.name} must be ordered in whole items")
            if s.pricing_model == "PER_KG" and (qty * 2) != (qty * 2).to_integral_value():
                raise AppError(422, "INVALID_QUANTITY", f"{s.name} is priced in 0.5 kg steps")
            quote.lines.append({"service_id": s.id, "name": s.name, "category": s.category, "pricing_model": s.pricing_model,
                                "unit_price": s.price, "quantity": qty, "line_total": line_total(s.price, qty),
                                "position": position})
        quote.subtotal = sum(line["line_total"] for line in quote.lines)
        if fulfillment == "PICKUP":
            if not business.pickup_enabled:
                raise AppError(409, "PICKUP_UNAVAILABLE", "This laundry does not offer pickup")
            quote.delivery_fee = business.pickup_fee
        quote.total = quote.subtotal + quote.delivery_fee
        return quote


@dataclass
class Quote:
    lines: list[dict] = field(default_factory=list)
    unavailable: list[str] = field(default_factory=list)
    subtotal: int = 0
    delivery_fee: int = 0
    total: int = 0

    def out(self) -> dict:
        return {"items": [{**line, "quantity": float(line["quantity"])} for line in self.lines],
                "unavailable_service_ids": self.unavailable, "subtotal": self.subtotal,
                "delivery_fee": self.delivery_fee, "total": self.total, "currency": "TZS"}


def service_out(s: Service) -> dict:
    return {"id": s.id, "name": s.name, "description": s.description, "category": s.category, "pricing_model": s.pricing_model,
            "price": s.price, "turnaround_hours": s.turnaround_hours, "sort_order": s.sort_order, "active": s.active}


def thumb(url: str | None) -> str | None:
    """Bundled media ships a 480px `-sm` variant for list cards on slow connections."""
    if url and url.startswith("/media/") and url.endswith(".jpg"):
        return url[:-4] + "-sm.jpg"
    return url


def first_name(full: str) -> str:
    parts = (full or "").split()
    if not parts:
        return ""
    return parts[0] + (f" {parts[-1][0]}." if len(parts) > 1 else "")


def favourite_ids(db: Session, user_id: str | None) -> set[str]:
    if not user_id:
        return set()
    return set(db.scalars(select(Favourite.business_id).where(Favourite.user_id == user_id)))
