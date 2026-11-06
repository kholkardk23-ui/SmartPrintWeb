"""add payment transactions table

Revision ID: d3a8e92f1b02
Revises: b28d4e91fc01
Create Date: 2026-11-05

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = "d3a8e92f1b02"
down_revision: Union[str, Sequence[str], None] = "b28d4e91fc01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create payment_transactions table if it does not already exist."""
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = inspector.get_table_names()

    if "payment_transactions" not in tables:
        op.create_table(
            "payment_transactions",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column(
                "order_id",
                sa.String(length=36),
                sa.ForeignKey("orders.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("txnid", sa.String(length=100), nullable=False),
            sa.Column("mihpayid", sa.String(length=100), nullable=True),
            sa.Column("amount", sa.Numeric(precision=10, scale=2), nullable=False),
            sa.Column("payment_gateway", sa.String(length=50), nullable=False, server_default="PAYU"),
            sa.Column("payment_mode", sa.String(length=50), nullable=True),
            sa.Column("payment_status", sa.String(length=50), nullable=False, server_default="INITIATED"),
            sa.Column("gateway_response", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index(
            "ix_payment_transactions_order_id",
            "payment_transactions",
            ["order_id"],
            unique=False,
        )
        op.create_index(
            "ix_payment_transactions_txnid",
            "payment_transactions",
            ["txnid"],
            unique=True,
        )
        op.create_index(
            "ix_payment_transactions_mihpayid",
            "payment_transactions",
            ["mihpayid"],
            unique=False,
        )


def downgrade() -> None:
    """Drop payment_transactions table if it exists."""
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = inspector.get_table_names()

    if "payment_transactions" in tables:
        op.drop_table("payment_transactions")

