"""Idempotent development seed with realistic Dar es Salaam demo data.

Run explicitly with `python -m app.seed`, or automatically on startup when AUTO_SEED=true (development only).
Every amount is in whole TZS.
"""
import random
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select

from .core.security import hash_password
from .database import SessionLocal
from .domain import order_states as S
from .domain.clock import now_utc
from .models import (
    Business,
    BusinessCustomer,
    BusinessHours,
    BusinessOnboarding,
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
from .seed_operations import seed_operating_history
from .services.orders import new_order_number
from .services.reviews import recompute_rating

PASSWORD = "Demo123!"

WEEK = [("07:30", "20:00")] * 6 + [("09:00", "16:00")]
WEEK_CLOSED_SUNDAY = [("08:00", "19:00")] * 6 + [None]

FULL_MENU = [
    ("Wash & Iron", "Shirt", "PER_ITEM", 2000, 24, "Washed, pressed and on a hanger"),
    ("Wash & Iron", "Trouser", "PER_ITEM", 3000, 24, ""),
    ("Wash & Iron", "Dress", "PER_ITEM", 3500, 24, ""),
    ("Wash & Iron", "Kanzu", "PER_ITEM", 3500, 24, ""),
    ("Wash & Iron", "Kitenge outfit", "PER_ITEM", 4000, 24, "Colour-safe wash"),
    ("Wash & Fold", "Wash & Fold", "PER_KG", 4000, 24, "Everyday clothes, washed and folded. Priced per kg."),
    ("Dry Cleaning", "Suit (2 piece)", "PER_ITEM", 8000, 48, ""),
    ("Dry Cleaning", "Wedding gown", "PER_ITEM", 35000, 96, ""),
    ("Household", "Bedsheet set", "PER_ITEM", 5000, 24, ""),
    ("Household", "Duvet", "PER_ITEM", 15000, 48, ""),
    ("Household", "Curtains (per panel)", "PER_ITEM", 6000, 48, ""),
]

BUSINESSES = [
    # slug, name, owner email, owner name, area, address, lat, lng, phone, pickup, fee, marketplace status, rate,
    # menu filter, price delta, hours, description
    ("freshwash-laundry-mikocheni", "FreshWash Laundry", "owner@freshwash.co.tz", "Rehema Mollel", "Mikocheni",
     "Mwai Kibaki Rd, near Shoppers Plaza", -6.7668, 39.2452, "+255713220114", True, 2000, "ACTIVE", "5.00", None, 0, WEEK,
     "Neighbourhood laundry with same-day shirts. Pickup across Mikocheni, Msasani and Kawe."),
    ("cleanpro-masaki", "CleanPro", "owner@cleanpro.co.tz", "David Kimaro", "Masaki", "Haile Selassie Rd, Masaki",
     -6.7489, 39.2797, "+255754880231", False, 0, "ACTIVE", "5.00", None, 500, WEEK,
     "Dry cleaning specialists for suits, gowns and delicate fabrics."),
    ("safi-laundry-sinza", "Safi Laundry", "owner@safilaundry.co.tz", "Halima Said", "Sinza", "Sinza Mori, opposite Lion Hotel",
     -6.7785, 39.2232, "+255687440912", True, 1500, "ACTIVE", "5.00", {"Wash & Iron", "Wash & Fold", "Household"}, -200,
     WEEK_CLOSED_SUNDAY, "Affordable everyday laundry. Wash & fold by the kilo, ready in 24 hours."),
    ("bahari-dry-cleaners-mbezi", "Bahari Dry Cleaners", "owner@bahari.co.tz", "Joseph Mrema", "Mbezi Beach",
     "Africana Rd, Mbezi Beach", -6.7205, 39.2275, "+255715600733", True, 3000, "ACTIVE", "5.00", None, 1000, WEEK,
     "Careful hand-finishing for office wear and household linen."),
    ("upanga-express-laundry", "Upanga Express", "owner@upangaexpress.co.tz", "Fatma Hassan", "Upanga",
     "United Nations Rd, Upanga", -6.8079, 39.2860, "+255622310455", True, 2000, "ACTIVE", "5.00",
     {"Wash & Iron", "Wash & Fold"}, 0, WEEK_CLOSED_SUNDAY, "Fast turnaround for busy professionals in town."),
    # Uses Launder Business only; its marketplace application waits for admin review. It must NOT be publicly listed.
    ("t-laundry-mikocheni", "T-Laundry", "owner@t-laundry.co.tz", "Asha Mushi", "Mikocheni", "Mikocheni B, Dar es Salaam",
     -6.7734, 39.2301, "+255712345678", True, 2500, "PENDING_REVIEW", "5.00", None, 0, WEEK,
     "Premium, dependable laundry care for busy Dar es Salaam households."),
]

CUSTOMERS = [("Neema Juma", "+255712334901"), ("Baraka Said", "+255754102820"), ("Zawadi Omar", "+255687551004"),
             ("Emmanuel Lyimo", "+255713908112"), ("Grace Mwakyusa", "+255765220318"), ("Salum Bakari", "+255716004422")]

REVIEWS = [(5, "Shirts came back perfectly pressed. Pickup was on time."),
           (5, "Huduma nzuri sana, nguo safi na zinanukia vizuri."),
           (4, "Good quality. Delivery was a little late but they called ahead."),
           (5, "My go-to for suits. Never had a problem."),
           (4, "Bei nzuri na wanajali. Nitarudi tena."),
           (5, "Fast and friendly. The kitenge colours stayed bright.")]


def _hours(business: Business, week) -> None:
    for weekday, slot in enumerate(week):
        business.hours.append(BusinessHours(weekday=weekday, opens_at=slot[0] if slot else "08:00",
                                            closes_at=slot[1] if slot else "18:00", closed=slot is None))


def _history(db, business: Business, services: list[Service], customers: list[Customer], rng: random.Random, count: int,
             marketplace: bool) -> None:
    """Past orders spread over six weeks, with consistent events, payments, commissions and reviews."""
    per_item = [s for s in services if s.pricing_model == "PER_ITEM" and s.price <= 15000]
    statuses = [S.COMPLETED] * 6 + [S.NEW, S.ACCEPTED, S.WASHING, S.READY, S.CANCELLED]
    reviews = list(REVIEWS)
    rng.shuffle(reviews)
    for i in range(count):
        customer = customers[i % len(customers)]
        source = "MARKETPLACE" if marketplace and i % 2 == 0 else ["WALK_IN", "PHONE", "WHATSAPP"][i % 3]
        status = statuses[i % len(statuses)]
        created = now_utc() - timedelta(days=rng.randint(0 if status not in (S.COMPLETED, S.CANCELLED) else 3, 42),
                                        hours=rng.randint(0, 10))
        order = Order(order_number=new_order_number(), business_id=business.id, customer_id=customer.id, source=source,
                      status=status, fulfillment="DROP_OFF", payment_method="CASH", created_at=created, updated_at=created)
        lines = rng.sample(per_item, k=min(len(per_item), rng.randint(1, 3)))
        for position, s in enumerate(lines):
            qty = Decimal(rng.randint(1, 5))
            order.items.append(OrderItem(service_id=s.id, name=s.name, pricing_model=s.pricing_model, unit_price=s.price,
                                         quantity=qty, line_total=int(s.price * qty), position=position))
        order.subtotal = order.total = sum(x.line_total for x in order.items)
        path = {S.COMPLETED: [S.NEW, S.ACCEPTED, S.RECEIVED, S.WASHING, S.IRONING, S.READY, S.DELIVERED, S.COMPLETED],
                S.CANCELLED: [S.NEW, S.CANCELLED], S.NEW: [S.NEW], S.ACCEPTED: [S.NEW, S.ACCEPTED],
                S.WASHING: [S.NEW, S.ACCEPTED, S.RECEIVED, S.WASHING],
                S.READY: [S.NEW, S.ACCEPTED, S.RECEIVED, S.WASHING, S.IRONING, S.READY]}[status]
        previous = None
        for step, st in enumerate(path):
            order.events.append(OrderStatusEvent(from_status=previous, to_status=st, created_at=created + timedelta(hours=step * 3)))
            previous = st
        if status == S.CANCELLED:
            order.cancel_reason = "Customer changed plans"
        order.due_at = created + timedelta(hours=24)
        order.ready_at = next((e.created_at for e in order.events if e.to_status == S.READY), None)
        paid = status == S.COMPLETED
        order.payment_status = "PAID" if paid else ("FAILED" if status == S.CANCELLED else "PENDING")
        if paid:
            order.completed_at = created + timedelta(hours=len(path) * 3)
        db.add(order)
        db.flush()
        if not db.scalar(select(BusinessCustomer.id).where(BusinessCustomer.business_id == business.id,
                                                          BusinessCustomer.customer_id == customer.id)):
            db.add(BusinessCustomer(business_id=business.id, customer_id=customer.id, created_at=created))
            db.flush()
        db.add(Payment(order_id=order.id, method="CASH", amount=order.total, status=order.payment_status,
                       paid_at=order.completed_at if paid else None))
        if paid and source == "MARKETPLACE":
            rate = Decimal("5.00")
            db.add(Commission(order_id=order.id, business_id=business.id, rate=rate, base_amount=order.subtotal,
                              amount=int((Decimal(order.subtotal) * rate / 100).quantize(Decimal("1")))))
            if reviews and customer.user_id:
                rating, comment = reviews.pop()
                user = db.get(User, customer.user_id)
                db.add(Review(order_id=order.id, business_id=business.id, user_id=user.id, author_name=user.full_name,
                              rating=rating, comment=comment, created_at=order.completed_at))


def seed(db) -> bool:
    """Base demo data once; FreshWash's operating history is added separately (also to databases seeded earlier)."""
    created = _seed_base(db)
    return seed_operating_history(db) or created


def _seed_base(db) -> bool:
    if db.scalar(select(User.id).where(User.email == "admin@launder.co.tz")):
        return False
    rng = random.Random(255)
    db.add(User(email="admin@launder.co.tz", password_hash=hash_password("Admin123!"), full_name="Launder Admin", role="SUPER_ADMIN"))

    customers = []
    for name, phone in CUSTOMERS:
        user = User(phone=phone, role="CUSTOMER", full_name=name)
        db.add(user)
        db.flush()
        record = Customer(user_id=user.id, name=name, phone=phone)
        db.add(record)
        customers.append(record)
    db.flush()

    for (slug, name, email, owner_name, area, address, lat, lng, phone, pickup, fee, mp_status, rate, menu, delta, week,
         description) in BUSINESSES:
        owner = User(email=email, password_hash=hash_password(PASSWORD), full_name=owner_name, role="BUSINESS_OWNER")
        db.add(owner)
        db.flush()
        business = Business(owner_id=owner.id, name=name, slug=slug, description=description, phone=phone, address=address,
                            area=area, status="ACTIVE", verification_status="VERIFIED" if mp_status == "ACTIVE" else "UNVERIFIED",
                            latitude=lat, longitude=lng, pickup_enabled=pickup, pickup_fee=fee,
                            cover_image_url=f"/media/laundries/{slug}.jpg")
        _hours(business, week)
        db.add(business)
        db.flush()
        services = []
        for order_index, (category, sname, model, price, hours, sdesc) in enumerate(FULL_MENU):
            if menu and category not in menu:
                continue
            services.append(Service(business_id=business.id, category=category, name=sname, pricing_model=model,
                                    price=max(price + (delta if model == "PER_ITEM" and price < 10000 else 0), 500),
                                    turnaround_hours=hours, sort_order=order_index, description=sdesc))
        db.add_all(services)
        submitted = now_utc() - timedelta(days=60 if mp_status == "ACTIVE" else 2)
        db.add(MarketplaceAccount(business_id=business.id, status=mp_status, commission_rate=Decimal(rate),
                                  pickup_radius_km=Decimal("8"), contact_name=owner_name, submitted_at=submitted,
                                  approved_at=submitted + timedelta(days=1) if mp_status == "ACTIVE" else None))
        db.add(BusinessOnboarding(business_id=business.id, current_step=9, completed=True))
        db.flush()
        _history(db, business, services, customers, rng, count=14 if slug != "t-laundry-mikocheni" else 24,
                 marketplace=mp_status == "ACTIVE")
        if slug == "freshwash-laundry-mikocheni":
            db.add(User(email="staff@freshwash.co.tz", password_hash=hash_password(PASSWORD), full_name="Juma Ally",
                        role="STAFF", business_id=business.id))
    db.flush()
    for business in db.scalars(select(Business)):
        recompute_rating(db, business.id)
    db.commit()
    return True


def main() -> None:
    from .migrations import upgrade_to_head

    upgrade_to_head()
    with SessionLocal() as db:
        print("Seeded demo data." if seed(db) else "Demo data already present; nothing to do.")


if __name__ == "__main__":
    main()
