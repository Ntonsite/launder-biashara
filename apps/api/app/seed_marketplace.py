"""Development demo of Marketplace activation, built through the same services admins and laundries use (audited).

* Mwenge Wash Hub      — applied, approved, 30-day commission-free trial started 23 days ago, with Marketplace orders.
* Kawe Fresh Laundry   — invited by Launder with a custom 45-day trial; has not confirmed yet.
* Kariakoo Quick Wash  — its trial ended without accepting the standard terms: new Marketplace orders are paused.
Idempotent."""
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select

from .core.security import hash_password
from .domain import order_states as S
from .domain.clock import now_utc
from .models import (
    Business,
    BusinessCustomer,
    BusinessHours,
    BusinessOnboarding,
    CommissionRule,
    Customer,
    MarketplaceAccount,
    Order,
    OrderItem,
    OrderStatusEvent,
    Payment,
    Service,
    User,
)
from .services.commission import CommissionService
from .services.marketplace_program import MarketplaceProgram
from .services.orders import new_order_number

PASSWORD = "Demo123!"
MENU = [("Wash & Iron", "Shirt", 1800), ("Wash & Iron", "Trouser", 2500), ("Wash & Iron", "Dress", 4000),
        ("Dry Cleaning", "Suit (2 piece)", 12000), ("Household", "Bedsheet", 3000)]
LAUNDRIES = [
    ("mwenge-wash-hub", "Mwenge Wash Hub", "owner@mwengewash.co.tz", "Peter Mushi", "Mwenge", "Sam Nujoma Rd, Mwenge",
     -6.7681, 39.2240, "+255713500611"),
    ("kawe-fresh-laundry", "Kawe Fresh Laundry", "owner@kawefresh.co.tz", "Neema Lyimo", "Kawe", "Kawe Beach Rd",
     -6.7290, 39.2280, "+255754600712"),
    ("kariakoo-quick-wash", "Kariakoo Quick Wash", "owner@kariakooquick.co.tz", "Hamisi Juma", "Kariakoo",
     "Msimbazi St, Kariakoo", -6.8190, 39.2730, "+255687700813"),
]


def _laundry(db, slug, name, email, owner_name, area, address, lat, lng, phone) -> tuple[User, Business, list[Service]]:
    owner = User(email=email, password_hash=hash_password(PASSWORD), full_name=owner_name, role="BUSINESS_OWNER")
    db.add(owner)
    db.flush()
    business = Business(owner_id=owner.id, name=name, slug=slug, phone=phone, address=address, area=area, status="ACTIVE",
                        verification_status="UNVERIFIED", latitude=lat, longitude=lng, pickup_enabled=False,
                        description=f"{name}: everyday laundry and dry cleaning in {area}.")
    for weekday in range(7):
        business.hours.append(BusinessHours(weekday=weekday, opens_at="08:00", closes_at="19:00", closed=weekday == 6))
    db.add(business)
    db.flush()
    services = [Service(business_id=business.id, category=c, name=n, pricing_model="PER_ITEM", price=p, turnaround_hours=24,
                        sort_order=i) for i, (c, n, p) in enumerate(MENU)]
    db.add_all(services)
    db.add_all([BusinessOnboarding(business_id=business.id, current_step=9, completed=True),
                MarketplaceAccount(business_id=business.id, status="NOT_ENROLLED")])
    db.flush()
    return owner, business, services


def _shift_trial(db, business: Business, days: int) -> None:
    """Pretend the trial started `days` ago (demo only)."""
    program = MarketplaceProgram(db)
    trial = program.open_agreement(business.id)
    account = program.account(business.id)
    delta = timedelta(days=days)
    trial.starts_at, trial.ends_at = trial.starts_at - delta, trial.ends_at - delta
    rule = db.get(CommissionRule, trial.commission_rule_id)
    rule.effective_from, rule.effective_to = rule.effective_from - delta, rule.effective_to - delta
    account.approved_at = account.first_listed_at = trial.starts_at
    account.submitted_at = account.terms_accepted_at = trial.starts_at - timedelta(days=1)
    db.flush()


def _trial_orders(db, business: Business, services: list[Service], customers: list[Customer], days_ago: list[int]) -> None:
    for i, ago in enumerate(days_ago):
        customer = customers[i % len(customers)]
        created = now_utc() - timedelta(days=ago, hours=3)
        completed = ago >= 2
        status = S.COMPLETED if completed else S.ACCEPTED
        order = Order(order_number=new_order_number(), business_id=business.id, customer_id=customer.id, source="MARKETPLACE",
                      status=status, fulfillment="DROP_OFF", payment_method="CASH", created_at=created, updated_at=created,
                      due_at=created + timedelta(hours=24))
        for position, s in enumerate(services[i % 3: i % 3 + 2]):
            qty = Decimal(1 + (i + position) % 3)
            order.items.append(OrderItem(service_id=s.id, name=s.name, pricing_model=s.pricing_model, unit_price=s.price,
                                         quantity=qty, line_total=int(s.price * qty), position=position))
        order.subtotal = order.total = sum(x.line_total for x in order.items)
        path = [S.NEW, S.ACCEPTED, S.RECEIVED, S.WASHING, S.READY, S.DELIVERED, S.COMPLETED] if completed else [S.NEW, S.ACCEPTED]
        for step, (a, b) in enumerate(zip([None, *path[:-1]], path, strict=False)):
            order.events.append(OrderStatusEvent(from_status=a, to_status=b, created_at=created + timedelta(hours=step * 3)))
        if completed:
            order.ready_at = created + timedelta(hours=12)
            order.completed_at = created + timedelta(hours=18)
            order.payment_status, order.amount_paid = "PAID", order.total
        db.add(order)
        db.flush()
        CommissionService(db).snapshot(order)
        if not db.scalar(select(BusinessCustomer.id).where(BusinessCustomer.business_id == business.id,
                                                          BusinessCustomer.customer_id == customer.id)):
            db.add(BusinessCustomer(business_id=business.id, customer_id=customer.id, created_at=created))
        db.add(Payment(order_id=order.id, method="CASH", amount=order.total, status=order.payment_status,
                       paid_at=order.completed_at))
        db.flush()
        if completed:
            CommissionService(db).earn(order)


def seed_marketplace(db) -> bool:
    if db.scalar(select(Business.id).where(Business.slug == LAUNDRIES[0][0])):
        return False
    admin = db.scalar(select(User).where(User.email == "admin@launder.co.tz"))
    finance = db.scalar(select(User).where(User.email == "finance@launder.co.tz")) or admin
    if not admin:
        return False
    customers = list(db.scalars(select(Customer).where(Customer.user_id.is_not(None)).order_by(Customer.name).limit(5)))
    application = {"contact_name": "", "pickup_radius_km": 6, "accept_terms": True}

    # 1. Applied → approved → trial running (23 of 30 days used), with orders.
    owner, mwenge, services = _laundry(db, *LAUNDRIES[0])
    MarketplaceProgram(db, owner).submit(mwenge, {**application, "contact_name": owner.full_name})
    MarketplaceProgram(db, admin).approve(MarketplaceProgram(db).account(mwenge.id), "Good setup, clear prices")
    _shift_trial(db, mwenge, 23)
    _trial_orders(db, mwenge, services, customers, [21, 18, 15, 11, 8, 5, 1])

    # 2. Invited by Launder with individual terms (45 days, 0 %).
    _, kawe, _ = _laundry(db, *LAUNDRIES[1])
    MarketplaceProgram(db, finance).invite(kawe, "Strong walk-in business; we'd like you in the launch group.", 45,
                                           Decimal("0"), launch_cohort=True)

    # 3. Trial ended without accepting the standard terms.
    owner, kariakoo, services = _laundry(db, *LAUNDRIES[2])
    MarketplaceProgram(db, owner).submit(kariakoo, {**application, "contact_name": owner.full_name})
    MarketplaceProgram(db, admin).approve(MarketplaceProgram(db).account(kariakoo.id), "Approved")
    _shift_trial(db, kariakoo, 34)
    _trial_orders(db, kariakoo, services, customers[2:], [30, 26, 12])
    db.commit()
    MarketplaceProgram(db).run()  # ends Kariakoo's trial, reminds Mwenge (7 days left)
    return True
