"""create_orders_table

Revision ID: 665ca5ebe127
Revises: 
Create Date: 2026-09-04 23:17:30.321564

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '665ca5ebe127'
down_revision: Union[str, Sequence[str], None] = "cc54a9180a7a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema to create orders table."""
    op.create_table(
        'orders',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('file_id', sa.String(length=36), nullable=False),
        sa.Column('copies', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('color_mode', sa.String(length=20), nullable=False, server_default='bw'),
        sa.Column('duplex', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('page_range', sa.String(length=100), nullable=False, server_default='all'),
        sa.Column('selected_page_count', sa.Integer(), nullable=False),
        sa.Column('physical_sheet_count', sa.Integer(), nullable=False),
        sa.Column('price_per_page', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('total_amount', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('currency', sa.String(length=10), nullable=False, server_default='INR'),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='OPTIONS_SELECTED'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['file_id'], ['files.id'], name='fk_orders_files_id', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_orders_file_id'), 'orders', ['file_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_orders_file_id'), table_name='orders')
    op.drop_table('orders')

