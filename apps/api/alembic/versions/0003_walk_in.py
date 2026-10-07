"""walk-in orders: guest customers, partial payments, package pricing

Revision ID: 0003
Revises: 0002
"""
import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("customers") as b:
        b.alter_column("phone", existing_type=sa.String(20), nullable=True)
        b.add_column(sa.Column("is_guest", sa.Boolean(), nullable=False, server_default=sa.false()))
    with op.batch_alter_table("orders") as b:
        b.add_column(sa.Column("amount_paid", sa.Integer(), nullable=False, server_default="0"))
        b.add_column(sa.Column("guest_name", sa.String(120), nullable=True))
    op.execute("UPDATE orders SET amount_paid = total WHERE payment_status IN ('PAID', 'REFUNDED')")


def downgrade() -> None:
    with op.batch_alter_table("orders") as b:
        b.drop_column("guest_name")
        b.drop_column("amount_paid")
    with op.batch_alter_table("customers") as b:
        b.drop_column("is_guest")
        b.alter_column("phone", existing_type=sa.String(20), nullable=False)
