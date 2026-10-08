"""commercial model: plans, subscriptions, invoices, commission rules and ledger, overrides, pilots, pricing audit

Initial plans (Starter free, Pro TZS 25,000, Business Plus TZS 60,000) and the 5 % default commission are seed values
written once here; administrators change them afterwards without code changes.

Revision ID: 0004
Revises: 0003
"""
import json
import uuid
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

TS = sa.DateTime(timezone=True)
ID = sa.String(36)

PLANS = [
    # code, name, description, benefits, default?, trial days, grace days, staff, branches, monthly, annual, features
    ("STARTER", "Starter", "Everything a small laundry needs to take and track orders.",
     ["Walk-in and counter orders", "Order tracking and slips", "End-of-day report", "Up to 2 team members"],
     True, 0, 7, 2, 1, 0, 0, ["walk_in_orders", "marketplace_eligible"]),
    ("PRO", "Pro", "Know your customers and your numbers.",
     ["Everything in Starter", "Customer profiles and follow-up", "Weekly and monthly reports",
      "Business performance and insights", "CSV exports", "Cashier, driver and manager roles", "Up to 10 team members"],
     False, 14, 7, 10, 1, 25000, 250000,
     ["walk_in_orders", "customer_crm", "advanced_reports", "data_export", "team_roles", "performance_insights",
      "marketplace_eligible"]),
    ("BUSINESS_PLUS", "Business Plus", "For busy laundries with a bigger team.",
     ["Everything in Pro", "Up to 50 team members", "Up to 5 branches (as multi-branch arrives)", "Priority support"],
     False, 14, 14, 50, 5, 60000, 600000,
     ["walk_in_orders", "customer_crm", "advanced_reports", "data_export", "team_roles", "performance_insights",
      "marketplace_eligible"]),
]


def upgrade() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)  # seed prices/rules apply to all history
    op.create_table(
        "subscription_plans",
        sa.Column("id", ID, primary_key=True), sa.Column("code", sa.String(40), nullable=False, unique=True),
        sa.Column("name", sa.String(80), nullable=False), sa.Column("description", sa.String(500), nullable=False),
        sa.Column("benefits_json", sa.Text(), nullable=False), sa.Column("status", sa.String(10), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False), sa.Column("trial_days", sa.Integer(), nullable=False),
        sa.Column("grace_days", sa.Integer(), nullable=False), sa.Column("max_staff", sa.Integer()),
        sa.Column("max_branches", sa.Integer()), sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("created_at", TS, nullable=False), sa.Column("updated_at", TS, nullable=False),
    )
    op.create_index("uq_subscription_plans_default", "subscription_plans", ["is_default"], unique=True,
                    postgresql_where=sa.text("is_default"))
    op.create_table(
        "plan_prices",
        sa.Column("id", ID, primary_key=True), sa.Column("plan_id", ID, sa.ForeignKey("subscription_plans.id"), nullable=False),
        sa.Column("interval", sa.String(8), nullable=False), sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("effective_from", TS, nullable=False), sa.Column("effective_to", TS),
        sa.Column("created_by", ID), sa.Column("created_at", TS, nullable=False),
        sa.CheckConstraint("amount >= 0", name="ck_plan_price_amount"),
        sa.CheckConstraint("effective_to IS NULL OR effective_to > effective_from", name="ck_plan_price_window"),
    )
    op.create_index("ix_plan_prices_plan_id", "plan_prices", ["plan_id"])
    op.create_index("ix_plan_prices_lookup", "plan_prices", ["plan_id", "interval", "effective_from"])
    op.create_table(
        "plan_features",
        sa.Column("id", ID, primary_key=True),
        sa.Column("plan_id", ID, sa.ForeignKey("subscription_plans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("feature_key", sa.String(40), nullable=False), sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("plan_id", "feature_key"),
    )
    op.create_index("ix_plan_features_plan_id", "plan_features", ["plan_id"])
    op.create_table(
        "business_subscriptions",
        sa.Column("id", ID, primary_key=True), sa.Column("business_id", ID, sa.ForeignKey("businesses.id"), nullable=False),
        sa.Column("plan_id", ID, sa.ForeignKey("subscription_plans.id"), nullable=False),
        sa.Column("interval", sa.String(8), nullable=False), sa.Column("status", sa.String(10), nullable=False),
        sa.Column("price_amount", sa.Integer(), nullable=False),
        sa.Column("current_period_start", TS, nullable=False), sa.Column("current_period_end", TS, nullable=False),
        sa.Column("trial_ends_at", TS), sa.Column("cancel_at_period_end", sa.Boolean(), nullable=False),
        sa.Column("next_plan_id", ID, sa.ForeignKey("subscription_plans.id")), sa.Column("source", sa.String(10), nullable=False),
        sa.Column("created_at", TS, nullable=False), sa.Column("ended_at", TS),
    )
    op.create_index("ix_business_subscriptions_business_id", "business_subscriptions", ["business_id"])
    op.create_index("ix_business_subscriptions_plan_id", "business_subscriptions", ["plan_id"])
    op.create_index("ix_business_subscriptions_status", "business_subscriptions", ["status"])
    op.create_index("uq_business_subscription_current", "business_subscriptions", ["business_id"], unique=True,
                    postgresql_where=sa.text("ended_at IS NULL"))
    op.execute("CREATE SEQUENCE IF NOT EXISTS invoice_number_seq START 1001")
    op.create_table(
        "subscription_invoices",
        sa.Column("id", ID, primary_key=True), sa.Column("number", sa.String(24), nullable=False, unique=True),
        sa.Column("business_id", ID, sa.ForeignKey("businesses.id"), nullable=False),
        sa.Column("subscription_id", ID, sa.ForeignKey("business_subscriptions.id"), nullable=False),
        sa.Column("period_start", TS, nullable=False), sa.Column("period_end", TS, nullable=False),
        sa.Column("subtotal", sa.Integer(), nullable=False), sa.Column("discount", sa.Integer(), nullable=False),
        sa.Column("amount_due", sa.Integer(), nullable=False), sa.Column("amount_paid", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(8), nullable=False), sa.Column("issued_at", TS, nullable=False),
        sa.Column("due_at", TS, nullable=False), sa.Column("paid_at", TS), sa.Column("void_reason", sa.String(255)),
        sa.UniqueConstraint("subscription_id", "period_start", name="uq_invoice_period"),
        sa.CheckConstraint("amount_due >= 0 AND amount_paid >= 0 AND amount_paid <= amount_due", name="ck_invoice_amounts"),
    )
    for col in ("business_id", "subscription_id", "status", "issued_at"):
        op.create_index(f"ix_subscription_invoices_{col}", "subscription_invoices", [col])
    op.create_table(
        "subscription_invoice_lines",
        sa.Column("id", ID, primary_key=True),
        sa.Column("invoice_id", ID, sa.ForeignKey("subscription_invoices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False), sa.Column("description", sa.String(200), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False), sa.Column("position", sa.Integer(), nullable=False),
    )
    op.create_index("ix_subscription_invoice_lines_invoice_id", "subscription_invoice_lines", ["invoice_id"])
    op.create_table(
        "subscription_payments",
        sa.Column("id", ID, primary_key=True),
        sa.Column("invoice_id", ID, sa.ForeignKey("subscription_invoices.id"), nullable=False),
        sa.Column("business_id", ID, sa.ForeignKey("businesses.id"), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False), sa.Column("method", sa.String(14), nullable=False),
        sa.Column("channel", sa.String(10), nullable=False), sa.Column("reference", sa.String(80), unique=True),
        sa.Column("idempotency_key", sa.String(64), unique=True), sa.Column("received_at", TS, nullable=False),
        sa.Column("recorded_by", ID), sa.Column("note", sa.String(255), nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.CheckConstraint("amount > 0", name="ck_subscription_payment_amount"),
    )
    for col in ("invoice_id", "business_id", "received_at"):
        op.create_index(f"ix_subscription_payments_{col}", "subscription_payments", [col])
    op.create_table(
        "marketplace_commission_rules",
        sa.Column("id", ID, primary_key=True), sa.Column("scope", sa.String(10), nullable=False),
        sa.Column("business_id", ID, sa.ForeignKey("businesses.id")), sa.Column("rate", sa.Numeric(5, 2), nullable=False),
        sa.Column("min_commission", sa.Integer(), nullable=False), sa.Column("include_pickup_fee", sa.Boolean(), nullable=False),
        sa.Column("discounts_reduce_basis", sa.Boolean(), nullable=False),
        sa.Column("effective_from", TS, nullable=False), sa.Column("effective_to", TS),
        sa.Column("reason", sa.String(255), nullable=False), sa.Column("created_by", ID), sa.Column("created_at", TS, nullable=False),
        sa.CheckConstraint("rate >= 0 AND rate <= 50", name="ck_commission_rate"),
        sa.CheckConstraint("min_commission >= 0", name="ck_commission_min"),
        sa.CheckConstraint("effective_to IS NULL OR effective_to > effective_from", name="ck_commission_window"),
        sa.CheckConstraint("(scope = 'DEFAULT' AND business_id IS NULL) OR (scope = 'BUSINESS' AND business_id IS NOT NULL) "
                           "OR scope = 'PROMOTION'", name="ck_commission_scope"),
        sa.CheckConstraint("scope <> 'PROMOTION' OR effective_to IS NOT NULL", name="ck_promotion_has_end"),
    )
    op.create_index("ix_marketplace_commission_rules_business_id", "marketplace_commission_rules", ["business_id"])
    op.create_index("ix_commission_rules_lookup", "marketplace_commission_rules", ["scope", "business_id", "effective_from"])
    op.create_table(
        "commercial_overrides",
        sa.Column("id", ID, primary_key=True), sa.Column("business_id", ID, sa.ForeignKey("businesses.id"), nullable=False),
        sa.Column("type", sa.String(20), nullable=False), sa.Column("plan_id", ID, sa.ForeignKey("subscription_plans.id"), nullable=False),
        sa.Column("value", sa.Numeric(12, 2), nullable=False), sa.Column("effective_from", TS, nullable=False),
        sa.Column("expires_at", TS), sa.Column("reason", sa.String(255), nullable=False),
        sa.Column("pilot_enrollment_id", ID), sa.Column("created_by", ID), sa.Column("created_at", TS, nullable=False),
        sa.Column("revoked_at", TS), sa.Column("revoked_by", ID),
        sa.CheckConstraint("expires_at IS NULL OR expires_at > effective_from", name="ck_override_window"),
    )
    op.create_index("ix_commercial_overrides_business_id", "commercial_overrides", ["business_id"])
    op.create_table(
        "pilot_programs",
        sa.Column("id", ID, primary_key=True), sa.Column("name", sa.String(120), nullable=False),
        sa.Column("plan_id", ID, sa.ForeignKey("subscription_plans.id"), nullable=False),
        sa.Column("duration_days", sa.Integer(), nullable=False), sa.Column("transition_policy", sa.String(10), nullable=False),
        sa.Column("status", sa.String(8), nullable=False), sa.Column("notes", sa.String(500), nullable=False),
        sa.Column("created_by", ID), sa.Column("created_at", TS, nullable=False),
    )
    op.create_table(
        "pilot_enrollments",
        sa.Column("id", ID, primary_key=True), sa.Column("program_id", ID, sa.ForeignKey("pilot_programs.id"), nullable=False),
        sa.Column("business_id", ID, sa.ForeignKey("businesses.id"), nullable=False),
        sa.Column("starts_at", TS, nullable=False), sa.Column("ends_at", TS, nullable=False),
        sa.Column("status", sa.String(8), nullable=False), sa.Column("transitioned_at", TS),
        sa.Column("enrolled_by", ID), sa.Column("created_at", TS, nullable=False),
        sa.UniqueConstraint("program_id", "business_id"),
    )
    op.create_index("ix_pilot_enrollments_program_id", "pilot_enrollments", ["program_id"])
    op.create_index("ix_pilot_enrollments_business_id", "pilot_enrollments", ["business_id"])
    op.create_table(
        "platform_settings",
        sa.Column("key", sa.String(60), primary_key=True), sa.Column("value_json", sa.Text(), nullable=False),
        sa.Column("updated_by", ID), sa.Column("updated_at", TS, nullable=False),
    )
    op.create_table(
        "pricing_audit_logs",
        sa.Column("id", ID, primary_key=True), sa.Column("actor_id", ID), sa.Column("action", sa.String(40), nullable=False),
        sa.Column("entity", sa.String(40), nullable=False), sa.Column("entity_id", sa.String(64), nullable=False),
        sa.Column("business_id", ID), sa.Column("before_json", sa.Text()), sa.Column("after_json", sa.Text()),
        sa.Column("reason", sa.String(255), nullable=False), sa.Column("created_at", TS, nullable=False),
    )
    for col in ("actor_id", "action", "business_id", "created_at"):
        op.create_index(f"ix_pricing_audit_logs_{col}", "pricing_audit_logs", [col])

    # Orders remember the commission terms they were placed under.
    with op.batch_alter_table("orders") as b:
        b.add_column(sa.Column("commission_rule_id", ID))
        b.add_column(sa.Column("commission_rate", sa.Numeric(5, 2)))

    # Commission table becomes a ledger: EARNED / REVERSED entries, one of each per order at most.
    with op.batch_alter_table("commissions") as b:
        b.add_column(sa.Column("entry_type", sa.String(10), nullable=False, server_default="EARNED"))
        b.add_column(sa.Column("rule_id", ID))
        b.add_column(sa.Column("basis_json", sa.Text(), nullable=False, server_default="{}"))
    op.execute("ALTER TABLE commissions DROP CONSTRAINT IF EXISTS commissions_order_id_key")
    op.create_unique_constraint("uq_commission_order_entry", "commissions", ["order_id", "entry_type"])
    op.create_index("ix_commissions_order_id", "commissions", ["order_id"])
    op.create_index("ix_commissions_business_created", "commissions", ["business_id", "created_at"])

    # ---- initial values ---------------------------------------------------------------------------------------------
    bind = op.get_bind()
    for order, (code, name, desc, benefits, default, trial, grace, staff, branches, monthly, annual, features) in enumerate(PLANS):
        plan_id = str(uuid.uuid4())
        bind.execute(sa.text(
            "INSERT INTO subscription_plans (id, code, name, description, benefits_json, status, is_default, trial_days, "
            "grace_days, max_staff, max_branches, sort_order, created_at, updated_at) VALUES (:id, :code, :name, :desc, "
            ":benefits, 'ACTIVE', :default, :trial, :grace, :staff, :branches, :order, now(), now())"),
            {"id": plan_id, "code": code, "name": name, "desc": desc, "benefits": json.dumps(benefits), "default": default,
             "trial": trial, "grace": grace, "staff": staff, "branches": branches, "order": order})
        for interval, amount in (("MONTHLY", monthly), ("ANNUAL", annual)):
            bind.execute(sa.text("INSERT INTO plan_prices (id, plan_id, interval, amount, effective_from, created_at) "
                                 "VALUES (:id, :plan, :interval, :amount, :from, now())"),
                         {"id": str(uuid.uuid4()), "plan": plan_id, "interval": interval, "amount": amount, "from": now})
        for key in features:
            bind.execute(sa.text("INSERT INTO plan_features (id, plan_id, feature_key, enabled) VALUES (:id, :plan, :key, true)"),
                         {"id": str(uuid.uuid4()), "plan": plan_id, "key": key})

    default_rule = str(uuid.uuid4())
    bind.execute(sa.text(
        "INSERT INTO marketplace_commission_rules (id, scope, rate, min_commission, include_pickup_fee, "
        "discounts_reduce_basis, effective_from, reason, created_at) VALUES (:id, 'DEFAULT', 5.00, 0, false, true, :from, "
        "'Launch default: 5 % of laundry services on completed Marketplace orders', now())"),
        {"id": default_rule, "from": now})
    # Any laundry that had a non-default rate keeps it as a business rule.
    for business_id, rate in bind.execute(sa.text(
            "SELECT business_id, commission_rate FROM marketplace_accounts WHERE commission_rate <> 5.00")).all():
        bind.execute(sa.text(
            "INSERT INTO marketplace_commission_rules (id, scope, business_id, rate, min_commission, include_pickup_fee, "
            "discounts_reduce_basis, effective_from, reason, created_at) VALUES (:id, 'BUSINESS', :b, :rate, 0, false, true, "
            ":from, 'Carried over from the marketplace account', now())"),
            {"id": str(uuid.uuid4()), "b": business_id, "rate": rate, "from": now})
    op.execute(sa.text("UPDATE commissions SET rule_id = :rule WHERE rule_id IS NULL").bindparams(rule=default_rule))
    with op.batch_alter_table("marketplace_accounts") as b:
        b.drop_column("commission_rate")
    for key, value in (("marketplace_listing_fee", 0), ("subscription_payment_instructions",
                       "Pay by M-Pesa, Mixx by Yas or Airtel Money to Launder, or by bank transfer, quoting your invoice "
                       "number. Launder confirms your payment and updates your plan."),
                       ("trial_reminder_days", 7), ("invoice_payment_terms_days", 7)):
        bind.execute(sa.text("INSERT INTO platform_settings (key, value_json, updated_at) VALUES (:k, :v, now())"),
                     {"k": key, "v": json.dumps(value)})


def downgrade() -> None:
    with op.batch_alter_table("marketplace_accounts") as b:
        b.add_column(sa.Column("commission_rate", sa.Numeric(5, 2), nullable=False, server_default="5.00"))
    op.drop_index("ix_commissions_business_created", "commissions")
    op.drop_index("ix_commissions_order_id", "commissions")
    op.drop_constraint("uq_commission_order_entry", "commissions")
    op.execute("DELETE FROM commissions WHERE entry_type <> 'EARNED'")
    op.create_unique_constraint("commissions_order_id_key", "commissions", ["order_id"])
    with op.batch_alter_table("commissions") as b:
        b.drop_column("basis_json")
        b.drop_column("rule_id")
        b.drop_column("entry_type")
    with op.batch_alter_table("orders") as b:
        b.drop_column("commission_rate")
        b.drop_column("commission_rule_id")
    for table in ("pricing_audit_logs", "platform_settings", "pilot_enrollments", "pilot_programs", "commercial_overrides",
                  "marketplace_commission_rules", "subscription_payments", "subscription_invoice_lines",
                  "subscription_invoices", "business_subscriptions", "plan_features", "plan_prices", "subscription_plans"):
        op.drop_table(table)
    op.execute("DROP SEQUENCE IF EXISTS invoice_number_seq")
