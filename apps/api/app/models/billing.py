"""Commercial model: SaaS plans and subscriptions, invoices, commission rules, overrides, pilots, pricing audit.

Nothing here is hardcoded pricing: plans, prices, entitlements, commission rules and business terms are rows that
platform administrators manage. Rows that money was calculated from are never edited in place — prices and rules
are versioned by effective dates, invoices snapshot their amounts, and corrections are new rows.
Money is whole TZS in Integer columns (exact); rates and percentages are Numeric.
"""
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base
from .entities import utcnow, uuid


class SubscriptionPlan(Base):
    __tablename__ = "subscription_plans"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid)
    # Stable internal key (never shown to providers); names and prices are free to change.
    code: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(String(500), default="")
    benefits_json: Mapped[str] = mapped_column(Text, default="[]")  # ["Unlimited walk-in orders", ...]
    # ACTIVE: can be chosen; HIDDEN: kept for existing/assigned businesses only; RETIRED: no new subscriptions.
    status: Mapped[str] = mapped_column(String(10), default="ACTIVE")
    # The plan a business falls back to when nothing else applies. Exactly one plan carries this flag.
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    trial_days: Mapped[int] = mapped_column(Integer, default=0)
    grace_days: Mapped[int] = mapped_column(Integer, default=7)
    max_staff: Mapped[int | None] = mapped_column(Integer)  # None = unlimited
    max_branches: Mapped[int | None] = mapped_column(Integer)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    prices: Mapped[list["PlanPrice"]] = relationship(order_by="PlanPrice.effective_from", viewonly=True)
    features: Mapped[list["PlanFeature"]] = relationship(viewonly=True)


class PlanPrice(Base):
    """A plan's price for one billing interval over a time window. A price change is a new row, never an edit."""
    __tablename__ = "plan_prices"
    __table_args__ = (Index("ix_plan_prices_lookup", "plan_id", "interval", "effective_from"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid)
    plan_id: Mapped[str] = mapped_column(ForeignKey("subscription_plans.id"), index=True)
    interval: Mapped[str] = mapped_column(String(8))  # MONTHLY | ANNUAL
    amount: Mapped[int] = mapped_column(Integer)  # TZS
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PlanFeature(Base):
    __tablename__ = "plan_features"
    __table_args__ = (UniqueConstraint("plan_id", "feature_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid)
    plan_id: Mapped[str] = mapped_column(ForeignKey("subscription_plans.id", ondelete="CASCADE"), index=True)
    feature_key: Mapped[str] = mapped_column(String(40))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class BusinessSubscription(Base):
    """A business's SaaS plan. One current row per business (ended_at IS NULL); history is kept."""
    __tablename__ = "business_subscriptions"
    __table_args__ = (Index("uq_business_subscription_current", "business_id", unique=True,
                            postgresql_where="ended_at IS NULL"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid)
    business_id: Mapped[str] = mapped_column(ForeignKey("businesses.id"), index=True)
    plan_id: Mapped[str] = mapped_column(ForeignKey("subscription_plans.id"), index=True)
    interval: Mapped[str] = mapped_column(String(8), default="MONTHLY")
    # TRIALING | ACTIVE | PAST_DUE | EXPIRED | CANCELLED
    status: Mapped[str] = mapped_column(String(10), index=True)
    # Price per period after any business terms, as last invoiced; drives MRR. 0 for free or complimentary.
    price_amount: Mapped[int] = mapped_column(Integer, default=0)
    current_period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    current_period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, default=False)
    next_plan_id: Mapped[str | None] = mapped_column(ForeignKey("subscription_plans.id"))  # scheduled downgrade
    source: Mapped[str] = mapped_column(String(10), default="SELF")  # SELF | ADMIN | DEFAULT
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    plan: Mapped[SubscriptionPlan] = relationship(foreign_keys=[plan_id], viewonly=True)


class SubscriptionInvoice(Base):
    __tablename__ = "subscription_invoices"
    __table_args__ = (UniqueConstraint("subscription_id", "period_start", name="uq_invoice_period"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid)
    number: Mapped[str] = mapped_column(String(24), unique=True)
    business_id: Mapped[str] = mapped_column(ForeignKey("businesses.id"), index=True)
    subscription_id: Mapped[str] = mapped_column(ForeignKey("business_subscriptions.id"), index=True)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    subtotal: Mapped[int] = mapped_column(Integer)  # list price of the lines
    discount: Mapped[int] = mapped_column(Integer, default=0)  # business terms, complimentary, upgrade credit
    amount_due: Mapped[int] = mapped_column(Integer)
    amount_paid: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(8), index=True)  # OPEN | PAID | VOID
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    void_reason: Mapped[str | None] = mapped_column(String(255))
    lines: Mapped[list["InvoiceLine"]] = relationship(order_by="InvoiceLine.position", cascade="all, delete-orphan")


class InvoiceLine(Base):
    __tablename__ = "subscription_invoice_lines"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid)
    invoice_id: Mapped[str] = mapped_column(ForeignKey("subscription_invoices.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16))  # PLAN | MARKETPLACE_FEE | DISCOUNT | CREDIT
    description: Mapped[str] = mapped_column(String(200))
    amount: Mapped[int] = mapped_column(Integer)  # negative for discounts and credits
    position: Mapped[int] = mapped_column(Integer, default=0)


class SubscriptionPayment(Base):
    """Money received against an invoice. Only confirmed receipts are stored; nothing here is simulated."""
    __tablename__ = "subscription_payments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid)
    invoice_id: Mapped[str] = mapped_column(ForeignKey("subscription_invoices.id"), index=True)
    business_id: Mapped[str] = mapped_column(ForeignKey("businesses.id"), index=True)
    amount: Mapped[int] = mapped_column(Integer)
    method: Mapped[str] = mapped_column(String(14))  # CASH | BANK_TRANSFER | MOBILE_MONEY
    channel: Mapped[str] = mapped_column(String(10), default="MANUAL")  # MANUAL (recorded by finance) | PROVIDER
    reference: Mapped[str | None] = mapped_column(String(80), unique=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(64), unique=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    recorded_by: Mapped[str | None] = mapped_column(String(36))
    note: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CommissionRule(Base):
    """Marketplace commission terms over a time window. Immutable once created except for closing the window.

    scope: DEFAULT (everyone), BUSINESS (one laundry's standing rate), PROMOTION (time-limited; one laundry, or all
    when business_id is NULL). Precedence: business promotion > business rate > global promotion > default.
    """
    __tablename__ = "marketplace_commission_rules"
    __table_args__ = (Index("ix_commission_rules_lookup", "scope", "business_id", "effective_from"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid)
    scope: Mapped[str] = mapped_column(String(10))
    business_id: Mapped[str | None] = mapped_column(ForeignKey("businesses.id"), index=True)
    rate: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    min_commission: Mapped[int] = mapped_column(Integer, default=0)  # TZS per order; never above the basis
    include_pickup_fee: Mapped[bool] = mapped_column(Boolean, default=False)
    # True: the basis is the services subtotal after discounts. False: before discounts.
    discounts_reduce_basis: Mapped[bool] = mapped_column(Boolean, default=True)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str] = mapped_column(String(255), default="")
    # Set when the rule implements a Marketplace trial agreement (scope PROMOTION, one laundry).
    agreement_id: Mapped[str | None] = mapped_column(String(36), index=True)
    created_by: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CommercialOverride(Base):
    """Special SaaS terms for one business: free access to a plan, a fixed price, or a percentage discount."""
    __tablename__ = "commercial_overrides"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid)
    business_id: Mapped[str] = mapped_column(ForeignKey("businesses.id"), index=True)
    # COMPLIMENTARY_PLAN (value unused) | PLAN_PRICE (value = TZS per month) | PLAN_DISCOUNT (value = percent)
    type: Mapped[str] = mapped_column(String(20))
    plan_id: Mapped[str] = mapped_column(ForeignKey("subscription_plans.id"))
    value: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str] = mapped_column(String(255))
    pilot_enrollment_id: Mapped[str | None] = mapped_column(String(36))
    created_by: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_by: Mapped[str | None] = mapped_column(String(36))
    plan: Mapped[SubscriptionPlan] = relationship(viewonly=True)


class PilotProgram(Base):
    __tablename__ = "pilot_programs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid)
    name: Mapped[str] = mapped_column(String(120))
    plan_id: Mapped[str] = mapped_column(ForeignKey("subscription_plans.id"))
    duration_days: Mapped[int] = mapped_column(Integer)
    # What happens at the end: DOWNGRADE (back to the default plan) or INVOICE (offer the plan; an invoice is issued
    # and nothing is charged unless the provider pays it). Either way the provider is told in advance.
    transition_policy: Mapped[str] = mapped_column(String(10), default="DOWNGRADE")
    status: Mapped[str] = mapped_column(String(8), default="ACTIVE")  # ACTIVE | CLOSED
    notes: Mapped[str] = mapped_column(String(500), default="")
    created_by: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    plan: Mapped[SubscriptionPlan] = relationship(viewonly=True)


class PilotEnrollment(Base):
    __tablename__ = "pilot_enrollments"
    __table_args__ = (UniqueConstraint("program_id", "business_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid)
    program_id: Mapped[str] = mapped_column(ForeignKey("pilot_programs.id"), index=True)
    business_id: Mapped[str] = mapped_column(ForeignKey("businesses.id"), index=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(8), default="ACTIVE")  # ACTIVE | ENDED | REMOVED
    transitioned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    enrolled_by: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    program: Mapped[PilotProgram] = relationship(viewonly=True)


class PlatformSetting(Base):
    """Commercial switches administrators change at runtime (e.g. whether Marketplace needs a paid plan)."""
    __tablename__ = "platform_settings"
    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value_json: Mapped[str] = mapped_column(Text)
    updated_by: Mapped[str | None] = mapped_column(String(36))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class PricingAuditLog(Base):
    __tablename__ = "pricing_audit_logs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid)
    actor_id: Mapped[str | None] = mapped_column(String(36), index=True)
    action: Mapped[str] = mapped_column(String(40), index=True)
    entity: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[str] = mapped_column(String(64))
    business_id: Mapped[str | None] = mapped_column(String(36), index=True)
    before_json: Mapped[str | None] = mapped_column(Text)
    after_json: Mapped[str | None] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class MarketplaceAgreement(Base):
    """One version of a laundry's Marketplace commercial terms. Never edited after it ends; changes are new versions.

    kind TRIAL: commission `rate` for `duration_days`, counted from when the laundry can actually receive online orders;
    afterwards the standard terms (`standard_rate` is what the provider was told) once accepted.
    kind STANDARD: the laundry accepted the standard Marketplace terms (the commission rules in force).
    status: OFFERED (invitation not yet confirmed) | PENDING_START | ACTIVE | ENDED | CANCELLED
    """
    __tablename__ = "marketplace_agreements"
    __table_args__ = (Index("ix_marketplace_agreements_business", "business_id", "version"),
                      Index("ix_marketplace_agreements_status_end", "status", "ends_at"))
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid)
    business_id: Mapped[str] = mapped_column(ForeignKey("businesses.id"))
    version: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(14))
    rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    standard_rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    duration_days: Mapped[int | None] = mapped_column(Integer)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    extensions: Mapped[int] = mapped_column(Integer, default=0)
    # DEFAULT_POLICY | CUSTOM (admin-set terms) | INVITATION
    source: Mapped[str] = mapped_column(String(14), default="DEFAULT_POLICY")
    commission_rule_id: Mapped[str | None] = mapped_column(String(36))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accepted_by: Mapped[str | None] = mapped_column(String(36))
    end_reason: Mapped[str | None] = mapped_column(String(20))  # EXPIRED | ENDED_EARLY | SUPERSEDED | CANCELLED
    terms_json: Mapped[str] = mapped_column(Text, default="{}")  # exactly what the provider was shown
    created_by: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MarketplaceEvent(Base):
    """Participation history: every review decision, invitation, activation, suspension and trial change."""
    __tablename__ = "marketplace_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid)
    business_id: Mapped[str] = mapped_column(ForeignKey("businesses.id"), index=True)
    action: Mapped[str] = mapped_column(String(40))
    from_status: Mapped[str | None] = mapped_column(String(20))
    to_status: Mapped[str | None] = mapped_column(String(20))
    actor_id: Mapped[str | None] = mapped_column(String(36))  # None = the scheduled lifecycle job
    reason: Mapped[str] = mapped_column(String(500), default="")
    data_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
