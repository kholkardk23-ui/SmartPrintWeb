"""Add short order number

Revision ID: 62651aaecd98
Revises: c709ac96e955
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "62651aaecd98"
down_revision: Union[str, Sequence[str], None] = "c709ac96e955"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add short customer-facing order numbers."""

    # 1. Add the column temporarily as nullable
    op.add_column(
        "orders",
        sa.Column(
            "order_number",
            sa.String(length=20),
            nullable=True,
        ),
    )

    # 2. Generate numbers for existing orders
    connection = op.get_bind()

    orders = connection.execute(
        sa.text(
            "SELECT id FROM orders ORDER BY created_at ASC"
        )
    ).fetchall()

    for number, row in enumerate(orders, start=1):
        order_number = f"SP-{number:06d}"

        connection.execute(
            sa.text(
                "UPDATE orders "
                "SET order_number = :order_number "
                "WHERE id = :id"
            ),
            {
                "order_number": order_number,
                "id": row[0],
            },
        )

    # 3. Make the column required
    with op.batch_alter_table("orders") as batch_op:
        batch_op.alter_column(
            "order_number",
            existing_type=sa.String(length=20),
            nullable=False,
        )

    # 4. Make order numbers unique
    op.create_index(
        "ix_orders_order_number",
        "orders",
        ["order_number"],
        unique=True,
    )


def downgrade() -> None:
    """Remove short customer-facing order numbers."""

    op.drop_index(
        "ix_orders_order_number",
        table_name="orders",
    )

    op.drop_column(
        "orders",
        "order_number",
    )