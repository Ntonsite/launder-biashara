"""Persistence model.

Money: Tanzanian shillings have no minor unit in practice, so every amount is stored as an exact integer number of
TZS. Rates and fractional quantities (kg) use Numeric and are combined with Decimal arithmetic; nothing monetary
ever passes through a float.
"""
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base


def uuid() -> str:
    return str(uuid4())


def utcnow() -> datetime:
    return datetime.now(UTC)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid)
    email: Mapped[str | None] = mapped_column(String(255), unique=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(20), unique=True, index=True)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(120), default="")
    # SUPER_ADMIN, ADMIN, CUSTOMER; business roles: BUSINESS_OWNER, BRANCH_MANAGER, CASHIER, STAFF, DRIVER
    role: Mapped[str] = mapped_column(String(20), index=True)
    # Staff and managers belong to a business; owners are linked through Business.owner_id.
    business_id: Mapped[str | None] = mapped_column(ForeignKey("businesses.id", use_alter=True, name="fk_users_business"), index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    language: Mapped[str] = mapped_column(String(2), default="en")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    # All tokens issued from one login share a family; reuse of a rotated token revokes the family.
    family_id: Mapped[str] = mapped_column(String(36), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class OtpChallenge(Base):
    __tablename__ = "otp_challenges"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid)
    phone: Mapped[str] = mapped_column(String(20), index=True)
    code_hash: Mapped[str] = mapped_column(String(64))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Business(Base):
    __tablename__ = "businesses"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    slug: Mapped[str] = mapped_column(String(180), unique=True, index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    phone: Mapped[str] = mapped_column(String(20), default="")
    address: Mapped[str] = mapped_column(String(255), default="")
    area: Mapped[str] = mapped_column(String(80))
    city: Mapped[str] = mapped_column(String(80), default="Dar es Salaam")
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    verification_status: Mapped[str] = mapped_column(String(20), default="UNVERIFIED")
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    # Maintained from published reviews by ReviewService; never written by clients.
    rating: Mapped[Decimal] = mapped_column(Numeric(3, 2), default=Decimal("0"))
    review_count: Mapped[int] = mapped_column(Integer, default=0)
    pickup_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    pickup_fee: Mapped[int] = mapped_column(Integer, default=0)
    cover_image_url: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    hours: Mapped[list["BusinessHours"]] = relationship(order_by="BusinessHours.weekday", cascade="all, delete-orphan")
    marketplace: Mapped["MarketplaceAccount | None"] = relationship(uselist=False, viewonly=True)


class BusinessHours(Base):
    __tablename__ = "business_hours"
    __table_args__ = (UniqueConstraint("business_id", "weekday"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid)
    business_id: Mapped[str] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    weekday: Mapped[int] = mapped_column(Integer)  # 0 = Monday
    opens_at: Mapped[str] = mapped_column(String(5), default="08:00")  # HH:MM local time, lexically comparable
    closes_at: Mapped[str] = mapped_column(String(5), default="18:00")
    closed: Mapped[bool] = mapped_column(Boolean, default=False)


class Branch(Base):
    __tablename__ = "branches"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid)
    business_id: Mapped[str] = mapped_column(ForeignKey("businesses.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    address: Mapped[str] = mapped_column(String(255))
    city: Mapped[str] = mapped_column(String(80), default="Dar es Salaam")
    region: Mapped[str] = mapped_column(String(80), default="Dar es Salaam")
    phone: Mapped[str] = mapped_column(String(20))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class BusinessOnboarding(Base):
    __tablename__ = "business_onboarding"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid)
    business_id: Mapped[str] = mapped_column(ForeignKey("businesses.id"), unique=True, index=True)
    current_step: Mapped[int] = mapped_column(Integer, default=1)
    data_json: Mapped[str] = mapped_column(Text, default="{}")
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Service(Base):
    __tablename__ = "services"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid)
    business_id: Mapped[str] = mapped_column(ForeignKey("businesses.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(String(500), default="")
    category: Mapped[str] = mapped_column(String(80), default="Wash & Iron")
    # PER_ITEM | PER_KG | PACKAGE (a fixed-price bundle, e.g. "Family bag up to 6 kg"), counted in whole units
    pricing_model: Mapped[str] = mapped_column(String(10), default="PER_ITEM")
    price: Mapped[int] = mapped_column(Integer)  # TZS
    turnaround_hours: Mapped[int] = mapped_column(Integer, default=24)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class MarketplaceAccount(Base):
    __tablename__ = "marketplace_accounts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid)
    business_id: Mapped[str] = mapped_column(ForeignKey("businesses.id"), unique=True, index=True)
    # Summary shown to people, derived from the three separate states below (services/marketplace_program.py):
    # NOT_ENROLLED | INVITED | DRAFT | PENDING_REVIEW | CHANGES_REQUESTED | REJECTED | APPROVED | TRIAL_ACTIVE | ACTIVE
    # | TRIAL_EXPIRED | SUSPENDED
    status: Mapped[str] = mapped_column(String(20), index=True, default="NOT_ENROLLED")
    # Application review: NOT_ENROLLED | INVITED | DRAFT | PENDING_REVIEW | CHANGES_REQUESTED | APPROVED | REJECTED
    review_status: Mapped[str] = mapped_column(String(20), default="NOT_ENROLLED")
    # Commercial terms: NONE | TRIAL (trial agreement pending or running) | STANDARD | EXPIRED (trial over, not accepted)
    commercial_status: Mapped[str] = mapped_column(String(10), default="NONE")
    # Public listing: HIDDEN | LISTED | SUSPENDED (admin) | PAUSED_PLAN (plan does not include Marketplace)
    listing_status: Mapped[str] = mapped_column(String(12), default="HIDDEN")
    # Included while the Marketplace runs as a controlled launch pilot.
    launch_cohort: Mapped[bool] = mapped_column(Boolean, default=False)
    terms_accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The provider agreed to continue at the standard terms after the trial.
    post_trial_accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    invited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    invited_by: Mapped[str | None] = mapped_column(String(36))
    invitation_note: Mapped[str | None] = mapped_column(String(500))
    first_listed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    suspended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status_reason: Mapped[str | None] = mapped_column(String(500))
    # Commission terms live in marketplace_commission_rules (versioned), not on the account.
    pickup_radius_km: Mapped[Decimal] = mapped_column(Numeric(5, 1), default=Decimal("8"))
    contact_name: Mapped[str | None] = mapped_column(String(120))
    registration_number: Mapped[str | None] = mapped_column(String(60))
    tin: Mapped[str | None] = mapped_column(String(30))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_by: Mapped[str | None] = mapped_column(String(36))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejection_reason: Mapped[str | None] = mapped_column(String(500))
    business: Mapped[Business] = relationship(viewonly=True)


class Customer(Base):
    """A business-facing customer record (CRM). Marketplace customers are additionally linked to a User."""
    __tablename__ = "customers"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    # Null only for a laundry's shared "walk-in guest" record, used when a customer leaves no details.
    phone: Mapped[str | None] = mapped_column(String(20), unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(255))
    is_guest: Mapped[bool] = mapped_column(Boolean, default=False)


class BusinessCustomer(Base):
    """A customer as known to one laundry (its CRM list). Created with the first order or added at the counter."""
    __tablename__ = "business_customers"
    __table_args__ = (UniqueConstraint("business_id", "customer_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid)
    business_id: Mapped[str] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"), index=True)
    notes: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    customer: Mapped[Customer] = relationship(viewonly=True)


class Address(Base):
    __tablename__ = "addresses"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    label: Mapped[str] = mapped_column(String(40), default="Home")
    line: Mapped[str] = mapped_column(String(255))
    area: Mapped[str] = mapped_column(String(80), default="")
    city: Mapped[str] = mapped_column(String(80), default="Dar es Salaam")
    notes: Mapped[str] = mapped_column(String(255), default="")
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Favourite(Base):
    __tablename__ = "favourites"
    __table_args__ = (UniqueConstraint("user_id", "business_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    business_id: Mapped[str] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        Index("ix_orders_business_created", "business_id", "created_at"),
        Index("ix_orders_business_status", "business_id", "status"),
        Index("ix_orders_business_due", "business_id", "due_at"),
        Index("ix_orders_business_completed", "business_id", "completed_at"),
        Index("ix_orders_business_customer", "business_id", "customer_id", "created_at"),
        UniqueConstraint("customer_id", "idempotency_key", name="uq_orders_customer_idempotency"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid)
    order_number: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    business_id: Mapped[str] = mapped_column(ForeignKey("businesses.id"), index=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), index=True)
    source: Mapped[str] = mapped_column(String(20))  # MARKETPLACE | WALK_IN | PHONE | WHATSAPP
    status: Mapped[str] = mapped_column(String(20), index=True)
    fulfillment: Mapped[str] = mapped_column(String(10), default="DROP_OFF")  # PICKUP | DROP_OFF
    pickup_address: Mapped[str | None] = mapped_column(String(255))
    pickup_notes: Mapped[str | None] = mapped_column(String(255))
    pickup_latitude: Mapped[float | None] = mapped_column(Float)
    pickup_longitude: Mapped[float | None] = mapped_column(Float)
    pickup_window_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pickup_window_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payment_method: Mapped[str] = mapped_column(String(15), default="CASH")  # CASH | MOBILE_MONEY
    # PENDING | PROCESSING | PARTIAL | PAID | FAILED | REFUNDED (PARTIAL: some money received, balance owed)
    payment_status: Mapped[str] = mapped_column(String(12), index=True, default="PENDING")
    # Sum of PAID payments; balance = total - amount_paid.
    amount_paid: Mapped[int] = mapped_column(Integer, default=0)
    subtotal: Mapped[int] = mapped_column(Integer, default=0)
    delivery_fee: Mapped[int] = mapped_column(Integer, default=0)
    # Counter discount in TZS: total = subtotal + delivery_fee - discount.
    discount: Mapped[int] = mapped_column(Integer, default=0)
    total: Mapped[int] = mapped_column(Integer)
    notes: Mapped[str] = mapped_column(String(500), default="")
    # Marketplace orders only: the commission rule and rate in force when the order was placed. Later rule changes
    # never re-price an existing order.
    commission_rule_id: Mapped[str | None] = mapped_column(String(36))
    commission_rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    # The rate that would have applied without a trial (for "commission waived"), and the agreement version in force.
    commission_standard_rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    marketplace_agreement_id: Mapped[str | None] = mapped_column(String(36))
    # Optional name written on a guest walk-in order's slip ("Mama Asha"); the customer record stays the shared guest.
    guest_name: Mapped[str | None] = mapped_column(String(120))
    # When the laundry promised the clothes would be ready. Drives "due today" and "overdue".
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # First time the order reached READY; compared with due_at for on-time performance.
    ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    idempotency_key: Mapped[str | None] = mapped_column(String(64))
    cancel_reason: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    items: Mapped[list["OrderItem"]] = relationship(cascade="all, delete-orphan", order_by="OrderItem.position")
    events: Mapped[list["OrderStatusEvent"]] = relationship(cascade="all, delete-orphan", order_by="OrderStatusEvent.created_at")
    business: Mapped[Business] = relationship(viewonly=True)
    customer: Mapped[Customer] = relationship(viewonly=True)


class OrderItem(Base):
    """Prices are snapshotted at order time; the live Service row may change later."""
    __tablename__ = "order_items"
    __table_args__ = (Index("ix_order_items_service", "service_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    service_id: Mapped[str | None] = mapped_column(ForeignKey("services.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(120))
    pricing_model: Mapped[str] = mapped_column(String(10))
    unit_price: Mapped[int] = mapped_column(Integer)
    quantity: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    line_total: Mapped[int] = mapped_column(Integer)
    position: Mapped[int] = mapped_column(Integer, default=0)


class OrderStatusEvent(Base):
    __tablename__ = "order_status_events"
    __table_args__ = (Index("ix_order_events_status_at", "to_status", "created_at"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    from_status: Mapped[str | None] = mapped_column(String(20))
    to_status: Mapped[str] = mapped_column(String(20))
    actor_id: Mapped[str | None] = mapped_column(String(36))
    note: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Payment(Base):
    __tablename__ = "payments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    method: Mapped[str] = mapped_column(String(15))
    # PENDING → PROCESSING → PAID | FAILED;  PAID → REFUNDED;  FAILED → PROCESSING (retry)
    status: Mapped[str] = mapped_column(String(12), index=True, default="PENDING")
    amount: Mapped[int] = mapped_column(Integer)
    provider: Mapped[str | None] = mapped_column(String(30))
    provider_reference: Mapped[str | None] = mapped_column(String(80), unique=True)
    payer_phone: Mapped[str | None] = mapped_column(String(20))
    failure_reason: Mapped[str | None] = mapped_column(String(255))
    recorded_by: Mapped[str | None] = mapped_column(String(36))
    # Money in (paid_at) and back out (refunded_at) are reported on the day they happen, not the order date.
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    refunded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Commission(Base):
    """Commission ledger. One EARNED entry when a Marketplace order completes, at most one REVERSED entry (negative
    amount) if its payment is refunded. Entries are never edited; sums give the net."""
    __tablename__ = "commissions"
    __table_args__ = (UniqueConstraint("order_id", "entry_type", name="uq_commission_order_entry"),
                      Index("ix_commissions_business_created", "business_id", "created_at"))
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), index=True)
    business_id: Mapped[str] = mapped_column(ForeignKey("businesses.id"), index=True)
    entry_type: Mapped[str] = mapped_column(String(10), default="EARNED")  # EARNED | REVERSED
    rule_id: Mapped[str | None] = mapped_column(String(36))
    rate: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    base_amount: Mapped[int] = mapped_column(Integer)
    amount: Mapped[int] = mapped_column(Integer)
    # How the basis was built (services, discount, pickup fee, minimum applied) — for disputes and audits.
    basis_json: Mapped[str] = mapped_column(Text, default="{}")
    # Commission not charged because the order was placed under a Marketplace trial (negative on a reversal).
    waived_amount: Mapped[int] = mapped_column(Integer, default=0)
    agreement_id: Mapped[str | None] = mapped_column(String(36))
    status: Mapped[str] = mapped_column(String(12), default="ACCRUED")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DayClose(Base):
    """End-of-day review. A snapshot plus the cash actually counted; it does not lock any transaction."""
    __tablename__ = "day_closes"
    __table_args__ = (UniqueConstraint("business_id", "business_date"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid)
    business_id: Mapped[str] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    business_date: Mapped[date] = mapped_column(Date)
    expected_cash: Mapped[int] = mapped_column(Integer)
    counted_cash: Mapped[int | None] = mapped_column(Integer)
    snapshot_json: Mapped[str] = mapped_column(Text, default="{}")
    note: Mapped[str] = mapped_column(String(500), default="")
    closed_by: Mapped[str] = mapped_column(String(36))
    closed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Review(Base):
    __tablename__ = "reviews"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), unique=True)
    business_id: Mapped[str] = mapped_column(ForeignKey("businesses.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    author_name: Mapped[str] = mapped_column(String(120), default="")
    rating: Mapped[int] = mapped_column(Integer)
    comment: Mapped[str] = mapped_column(String(1000), default="")
    status: Mapped[str] = mapped_column(String(12), default="PUBLISHED")  # PUBLISHED | HIDDEN
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Notification(Base):
    """In-app notification. `kind` is a stable key the clients localise; no translated text is stored."""
    __tablename__ = "notifications"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    order_id: Mapped[str | None] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"))
    data_json: Mapped[str] = mapped_column(Text, default="{}")
    # NOT_CONFIGURED until a push provider is wired; we never claim a push was delivered.
    push_status: Mapped[str] = mapped_column(String(16), default="NOT_CONFIGURED")
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class DeviceToken(Base):
    __tablename__ = "device_tokens"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token: Mapped[str] = mapped_column(String(512), unique=True)
    platform: Mapped[str] = mapped_column(String(10))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid)
    actor_id: Mapped[str | None] = mapped_column(String(36), index=True)
    action: Mapped[str] = mapped_column(String(60), index=True)
    entity: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[str] = mapped_column(String(36))
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
