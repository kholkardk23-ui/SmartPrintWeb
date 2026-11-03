"""add payment fields to orders

Revision ID: 9a3b7c1e5d2f
Revises: 81f9df2c9723
Create Date: 2026-11-02

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = "9a3b7c1e5d2f"
down_revision: Union[str, Sequence[str], None] = "81f9df2c9723"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add payment_status, payment_reference, and payment_timestamp to orders table if not present."""
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_columns = [col["name"] for col in inspector.get_columns("orders")]

    with op.batch_alter_table("orders") as batch_op:
        if "payment_status" not in existing_columns:
            batch_op.add_column(
                sa.Column("payment_status", sa.String(length=50), nullable=True, server_default="PENDING")
            )
        if "payment_reference" not in existing_columns:
            batch_op.add_column(
                sa.Column("payment_reference", sa.String(length=100), nullable=True)
            )
        if "payment_timestamp" not in existing_columns:
            batch_op.add_column(
                sa.Column("payment_timestamp", sa.DateTime(), nullable=True)
            )


def downgrade() -> None:
    """Drop payment fields from orders table if they exist."""
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_columns = [col["name"] for col in inspector.get_columns("orders")]

    with op.batch_alter_table("orders") as batch_op:
        if "payment_timestamp" in existing_columns:
            batch_op.drop_column("payment_timestamp")
        if "payment_reference" in existing_columns:
            batch_op.drop_column("payment_reference")
        if "payment_status" in existing_columns:
            batch_op.drop_column("payment_status")

