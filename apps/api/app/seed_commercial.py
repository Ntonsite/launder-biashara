"""Development demo of the commercial model, built through the same services administrators use (so it is audited).
Plans and the default commission come from migration 0004; this only adds example business terms. Idempotent."""
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select

from .core.security import hash_password
from .domain.clock import now_utc
from .models import Business, PilotProgram, SubscriptionInvoice, SubscriptionPlan, User
from .services.billing import BillingService
from .services.pricing import PricingAdmin


def _business(db, slug: str) -> Business | None:
    return db.scalar(select(Business).where(Business.slug == slug))


def _paid_subscription(db, billing: BillingService, actor: User, business: Business, plan: SubscriptionPlan, interval: str,
                       method: str, reference: str) -> None:
    sub = billing._start(business, plan, interval, now_utc(), "ADMIN", allow_trial=False)
    db.commit()
    invoice = db.scalar(select(SubscriptionInvoice).where(SubscriptionInvoice.subscription_id == sub.id))
    if invoice and invoice.status == "OPEN":
        billing.record_payment(invoice, invoice.amount_due, method, reference, now_utc(), actor, None, "Demo payment")


def seed_commercial(db) -> bool:
    if db.scalar(select(PilotProgram.id)):
        return False
    for email, role, name in (("finance@launder.co.tz", "FINANCE_ADMIN", "Launder Finance"),
                              ("support@launder.co.tz", "ADMIN", "Launder Support")):
        if not db.scalar(select(User.id).where(User.email == email)):
            db.add(User(email=email, password_hash=hash_password("Admin123!"), full_name=name, role=role))
    db.flush()
    actor = db.scalar(select(User).where(User.role == "SUPER_ADMIN"))
    if not actor:
        return False
    plans = {p.code: p for p in db.scalars(select(SubscriptionPlan))}
    admin, billing = PricingAdmin(db, actor), BillingService(db)
    now = now_utc()

    pilot = admin.create_pilot("Provider pilot 2026", plans["PRO"].id, 90, "DOWNGRADE",
                               "Complimentary Pro for launch laundries; Marketplace stays optional.")
    if fresh := _business(db, "freshwash-laundry-mikocheni"):
        admin.enroll(pilot, fresh.id, now - timedelta(days=10))
    if clean := _business(db, "cleanpro-masaki"):
        admin.create_override(clean.id, "PLAN_PRICE", plans["PRO"].id, Decimal("20000"), now, None, "Early partner price")
        _paid_subscription(db, billing, actor, clean, plans["PRO"], "MONTHLY", "MOBILE_MONEY", "DEMO-CLEANPRO-001")
    if upanga := _business(db, "upanga-express-laundry"):
        _paid_subscription(db, billing, actor, upanga, plans["BUSINESS_PLUS"], "ANNUAL", "BANK_TRANSFER", "DEMO-UPANGA-001")
    if bahari := _business(db, "bahari-dry-cleaners-mbezi"):
        billing.change_plan(bahari, plans["PRO"], "MONTHLY", actor, "SELF", "Demo trial")
    if safi := _business(db, "safi-laundry-sinza"):
        admin.create_rule("BUSINESS", safi.id, Decimal("3.00"), 0, False, True, None, None, "Pilot partner rate")
    db.commit()
    return True
