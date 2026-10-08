"""marketplace activation: separate review / commercial / listing states, agreements (trials), participation history

Existing Marketplace laundries keep trading exactly as before: approved and listed laundries get a STANDARD agreement
(they accepted the terms when they joined) and are placed in the launch cohort. Settings below are initial values;
administrators change them in Admin → Monetization → Marketplace settings.

Revision ID: 0005
Revises: 0004
"""
import json
import uuid

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

TS = sa.DateTime(timezone=True)
ID = sa.String(36)
PLAN_PAUSE_REASON = "Your current plan does not include a Marketplace listing"

SETTINGS = (
    ("marketplace_mode", "PUBLIC"),
    ("marketplace_self_enrollment", True),
    ("marketplace_invitations", True),
    ("marketplace_approval_required", True),
    ("marketplace_verification_required", False),
    ("marketplace_auto_activate", True),
    ("marketplace_trial_enabled", True),
    ("marketplace_trial_days", 30),
    ("marketplace_trial_rate", "0.00"),
    ("marketplace_trial_start", "WHEN_ORDERS_OPEN"),
    ("marketplace_trial_one_per_business", True),
    ("marketplace_trial_extension_allowed", True),
    ("marketplace_trial_max_extensions", 1),
    ("marketplace_acceptance_required", True),
    ("marketplace_reminder_days", [7, 2, 0]),
    ("marketplace_suspension_pauses_trial", True),
)


def upgrade() -> None:
    with op.batch_alter_table("marketplace_accounts") as b:
        b.add_column(sa.Column("review_status", sa.String(20), nullable=False, server_default="NOT_ENROLLED"))
        b.add_column(sa.Column("commercial_status", sa.String(10), nullable=False, server_default="NONE"))
        b.add_column(sa.Column("listing_status", sa.String(12), nullable=False, server_default="HIDDEN"))
        b.add_column(sa.Column("launch_cohort", sa.Boolean(), nullable=False, server_default=sa.false()))
        for name in ("terms_accepted_at", "post_trial_accepted_at", "invited_at", "first_listed_at", "suspended_at"):
            b.add_column(sa.Column(name, TS))
        b.add_column(sa.Column("invited_by", ID))
        b.add_column(sa.Column("invitation_note", sa.String(500)))
        b.add_column(sa.Column("status_reason", sa.String(500)))
    op.create_index("ix_marketplace_accounts_listing", "marketplace_accounts", ["listing_status", "commercial_status"])

    with op.batch_alter_table("orders") as b:
        b.add_column(sa.Column("commission_standard_rate", sa.Numeric(5, 2)))
        b.add_column(sa.Column("marketplace_agreement_id", ID))
    with op.batch_alter_table("commissions") as b:
        b.add_column(sa.Column("waived_amount", sa.Integer(), nullable=False, server_default="0"))
        b.add_column(sa.Column("agreement_id", ID))
    with op.batch_alter_table("marketplace_commission_rules") as b:
        b.add_column(sa.Column("agreement_id", ID))
    op.create_index("ix_marketplace_commission_rules_agreement_id", "marketplace_commission_rules", ["agreement_id"])

    op.create_table(
        "marketplace_agreements",
        sa.Column("id", ID, primary_key=True), sa.Column("business_id", ID, sa.ForeignKey("businesses.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False), sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("status", sa.String(14), nullable=False), sa.Column("rate", sa.Numeric(5, 2)),
        sa.Column("standard_rate", sa.Numeric(5, 2)), sa.Column("duration_days", sa.Integer()),
        sa.Column("starts_at", TS), sa.Column("ends_at", TS),
        sa.Column("extensions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source", sa.String(14), nullable=False), sa.Column("commission_rule_id", ID),
        sa.Column("accepted_at", TS), sa.Column("accepted_by", ID), sa.Column("end_reason", sa.String(20)),
        sa.Column("terms_json", sa.Text(), nullable=False), sa.Column("created_by", ID),
        sa.Column("created_at", TS, nullable=False),
        sa.UniqueConstraint("business_id", "version", name="uq_marketplace_agreement_version"),
        sa.CheckConstraint("rate IS NULL OR (rate >= 0 AND rate <= 50)", name="ck_marketplace_agreement_rate"),
    )
    op.create_index("ix_marketplace_agreements_business", "marketplace_agreements", ["business_id", "version"])
    op.create_index("ix_marketplace_agreements_status_end", "marketplace_agreements", ["status", "ends_at"])
    # At most one open trial or standard agreement per laundry, whatever happens concurrently.
    op.create_index("uq_marketplace_agreement_open", "marketplace_agreements", ["business_id"], unique=True,
                    postgresql_where=sa.text("status IN ('OFFERED', 'PENDING_START', 'ACTIVE')"))
    op.create_table(
        "marketplace_events",
        sa.Column("id", ID, primary_key=True), sa.Column("business_id", ID, sa.ForeignKey("businesses.id"), nullable=False),
        sa.Column("action", sa.String(40), nullable=False), sa.Column("from_status", sa.String(20)),
        sa.Column("to_status", sa.String(20)), sa.Column("actor_id", ID), sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("data_json", sa.Text(), nullable=False), sa.Column("created_at", TS, nullable=False),
    )
    op.create_index("ix_marketplace_events_business_id", "marketplace_events", ["business_id"])
    op.create_index("ix_marketplace_events_created_at", "marketplace_events", ["created_at"])

    bind = op.get_bind()
    # Backfill the separate states from the old single status.
    bind.execute(sa.text("UPDATE marketplace_accounts SET review_status = status "
                         "WHERE status IN ('NOT_ENROLLED', 'PENDING_REVIEW', 'REJECTED')"))
    bind.execute(sa.text(
        "UPDATE marketplace_accounts SET review_status = 'APPROVED', commercial_status = 'STANDARD', launch_cohort = true, "
        "terms_accepted_at = coalesce(submitted_at, approved_at), first_listed_at = approved_at, "
        "listing_status = CASE WHEN status = 'ACTIVE' THEN 'LISTED' "
        "WHEN rejection_reason = :pause THEN 'PAUSED_PLAN' ELSE 'SUSPENDED' END, "
        "status_reason = CASE WHEN status = 'SUSPENDED' THEN rejection_reason END, "
        "suspended_at = CASE WHEN status = 'SUSPENDED' THEN reviewed_at END, "
        "rejection_reason = NULL WHERE status IN ('ACTIVE', 'SUSPENDED')"), {"pause": PLAN_PAUSE_REASON})
    for business_id, approved_at in bind.execute(sa.text(
            "SELECT business_id, coalesce(approved_at, now()) FROM marketplace_accounts "
            "WHERE commercial_status = 'STANDARD'")).all():
        bind.execute(sa.text(
            "INSERT INTO marketplace_agreements (id, business_id, version, kind, status, source, starts_at, accepted_at, "
            "terms_json, created_at) VALUES (:id, :b, 1, 'STANDARD', 'ACTIVE', 'DEFAULT_POLICY', :at, :at, :terms, now())"),
            {"id": str(uuid.uuid4()), "b": business_id, "at": approved_at,
             "terms": json.dumps({"note": "Joined before Marketplace trials existed; standard terms"})})
    for key, value in SETTINGS:
        bind.execute(sa.text("INSERT INTO platform_settings (key, value_json, updated_at) VALUES (:k, :v, now()) "
                             "ON CONFLICT (key) DO NOTHING"), {"k": key, "v": json.dumps(value)})


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text(
        "UPDATE marketplace_accounts SET status = CASE "
        "WHEN listing_status = 'LISTED' AND commercial_status IN ('TRIAL', 'STANDARD') THEN 'ACTIVE' "
        "WHEN review_status = 'APPROVED' THEN 'SUSPENDED' "
        "WHEN review_status IN ('PENDING_REVIEW', 'REJECTED') THEN review_status ELSE 'NOT_ENROLLED' END"))
    bind.execute(sa.text("DELETE FROM platform_settings WHERE key LIKE 'marketplace\\_%' AND key <> 'marketplace_listing_fee'"))
    op.drop_table("marketplace_events")
    op.drop_table("marketplace_agreements")
    op.drop_index("ix_marketplace_commission_rules_agreement_id", "marketplace_commission_rules")
    with op.batch_alter_table("marketplace_commission_rules") as b:
        b.drop_column("agreement_id")
    with op.batch_alter_table("commissions") as b:
        b.drop_column("agreement_id")
        b.drop_column("waived_amount")
    with op.batch_alter_table("orders") as b:
        b.drop_column("marketplace_agreement_id")
        b.drop_column("commission_standard_rate")
    op.drop_index("ix_marketplace_accounts_listing", "marketplace_accounts")
    with op.batch_alter_table("marketplace_accounts") as b:
        for name in ("status_reason", "invitation_note", "invited_by", "suspended_at", "first_listed_at", "invited_at",
                     "post_trial_accepted_at", "terms_accepted_at", "launch_cohort", "listing_status", "commercial_status",
                     "review_status"):
            b.drop_column(name)
