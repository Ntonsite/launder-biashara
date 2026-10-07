"""business operations: due dates, discounts, payment timestamps, CRM link, day close, analytics indexes

Revision ID: 0002
Revises: 0001
"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("orders") as b:
        b.add_column(sa.Column("discount", sa.Integer(), nullable=False, server_default="0"))
        b.add_column(sa.Column("due_at", sa.DateTime(timezone=True), nullable=True))
        b.add_column(sa.Column("ready_at", sa.DateTime(timezone=True), nullable=True))
        b.create_index("ix_orders_business_status", ["business_id", "status"])
        b.create_index("ix_orders_business_due", ["business_id", "due_at"])
        b.create_index("ix_orders_business_completed", ["business_id", "completed_at"])
        b.create_index("ix_orders_business_customer", ["business_id", "customer_id", "created_at"])
    with op.batch_alter_table("payments") as b:
        b.add_column(sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True))
        b.add_column(sa.Column("refunded_at", sa.DateTime(timezone=True), nullable=True))
        b.create_index("ix_payments_paid_at", ["paid_at"])
        b.create_index("ix_payments_refunded_at", ["refunded_at"])
    op.create_index("ix_order_events_status_at", "order_status_events", ["to_status", "created_at"])
    op.create_index("ix_order_items_service", "order_items", ["service_id"])

    op.create_table(
        "business_customers",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("business_id", sa.String(36), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("customer_id", sa.String(36), sa.ForeignKey("customers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("notes", sa.String(500), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("business_id", "customer_id"),
    )
    op.create_index("ix_business_customers_business_id", "business_customers", ["business_id"])
    op.create_index("ix_business_customers_customer_id", "business_customers", ["customer_id"])
    op.create_table(
        "day_closes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("business_id", sa.String(36), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("expected_cash", sa.Integer(), nullable=False),
        sa.Column("counted_cash", sa.Integer(), nullable=True),
        sa.Column("snapshot_json", sa.Text(), nullable=False),
        sa.Column("note", sa.String(500), nullable=False),
        sa.Column("closed_by", sa.String(36), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("business_id", "business_date"),
    )
    op.create_index("ix_day_closes_business_id", "day_closes", ["business_id"])

    # Backfill existing rows so history is reportable.
    op.execute("""
        UPDATE orders o SET due_at = COALESCE(o.pickup_window_end, o.created_at) + make_interval(hours => COALESCE((
            SELECT MAX(s.turnaround_hours) FROM order_items i JOIN services s ON s.id = i.service_id WHERE i.order_id = o.id
        ), 24))
    """)
    op.execute("""
        UPDATE orders o SET ready_at = e.at FROM (
            SELECT order_id, MIN(created_at) AS at FROM order_status_events WHERE to_status = 'READY' GROUP BY order_id
        ) e WHERE e.order_id = o.id
    """)
    op.execute("UPDATE payments SET paid_at = updated_at WHERE status IN ('PAID', 'REFUNDED')")
    op.execute("UPDATE payments SET refunded_at = updated_at WHERE status = 'REFUNDED'")
    op.execute("""
        INSERT INTO business_customers (id, business_id, customer_id, notes, created_at)
        SELECT gen_random_uuid()::text, business_id, customer_id, '', MIN(created_at) FROM orders GROUP BY business_id, customer_id
    """)


def downgrade() -> None:
    op.drop_table("day_closes")
    op.drop_table("business_customers")
    op.drop_index("ix_order_items_service", "order_items")
    op.drop_index("ix_order_events_status_at", "order_status_events")
    with op.batch_alter_table("payments") as b:
        b.drop_index("ix_payments_refunded_at")
        b.drop_index("ix_payments_paid_at")
        b.drop_column("refunded_at")
        b.drop_column("paid_at")
    with op.batch_alter_table("orders") as b:
        for name in ("ix_orders_business_customer", "ix_orders_business_completed", "ix_orders_business_due",
                     "ix_orders_business_status"):
            b.drop_index(name)
        b.drop_column("ready_at")
        b.drop_column("due_at")
        b.drop_column("discount")
