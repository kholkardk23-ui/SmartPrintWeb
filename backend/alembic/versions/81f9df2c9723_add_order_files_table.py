"""add order files table

Revision ID: 81f9df2c9723
Revises: 62651aaecd98
Create Date: 2026-10-04

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = "81f9df2c9723"
down_revision: Union[str, Sequence[str], None] = "62651aaecd98"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create order_files table if it does not already exist."""

    bind = op.get_bind()
    inspector = inspect(bind)

    if "order_files" in inspector.get_table_names():
        return

    op.create_table(
        "order_files",

        sa.Column(
            "id",
            sa.String(length=36),
            nullable=False,
        ),

        sa.Column(
            "order_id",
            sa.String(length=36),
            nullable=False,
        ),

        sa.Column(
            "file_id",
            sa.String(length=36),
            nullable=False,
        ),

        sa.Column(
            "file_order",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "selected_page_count",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "physical_sheet_count",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "total_amount",
            sa.Numeric(precision=10, scale=2),
            nullable=False,
        ),

        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
        ),

        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.id"],
            ondelete="CASCADE",
        ),

        sa.ForeignKeyConstraint(
            ["file_id"],
            ["files.id"],
            ondelete="CASCADE",
        ),

        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Drop order_files table if it exists."""

    bind = op.get_bind()
    inspector = inspect(bind)

    if "order_files" in inspector.get_table_names():
        op.drop_table("order_files")