"""add youpi payment session fields

Revision ID: b28d4e91fc01
Revises: 9a3b7c1e5d2f
Create Date: 2026-11-02

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = "b28d4e91fc01"
down_revision: Union[str, Sequence[str], None] = "9a3b7c1e5d2f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add payment_session_id and is_paid to orders table if not present."""
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_columns = [col["name"] for col in inspector.get_columns("orders")]

    with op.batch_alter_table("orders") as batch_op:
        if "payment_session_id" not in existing_columns:
            batch_op.add_column(
                sa.Column("payment_session_id", sa.String(length=100), nullable=True)
            )
        if "is_paid" not in existing_columns:
            batch_op.add_column(
                sa.Column("is_paid", sa.Boolean(), nullable=False, server_default=sa.text("0"))
            )


def downgrade() -> None:
    """Drop payment session fields from orders table if they exist."""
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_columns = [col["name"] for col in inspector.get_columns("orders")]

    with op.batch_alter_table("orders") as batch_op:
        if "is_paid" in existing_columns:
            batch_op.drop_column("is_paid")
        if "payment_session_id" in existing_columns:
            batch_op.drop_column("payment_session_id")

