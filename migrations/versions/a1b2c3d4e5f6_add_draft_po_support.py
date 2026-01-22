"""Add draft PO support fields

Revision ID: a1b2c3d4e5f6
Revises: f8a2c3d4e5f6
Create Date: 2026-01-22 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = 'f8a2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    # Add is_auto_generated column to purchase_orders table
    try:
        with op.batch_alter_table('purchase_orders', schema=None) as batch_op:
            batch_op.add_column(sa.Column('is_auto_generated', sa.Boolean(), nullable=True, server_default='0'))
    except Exception as e:
        print(f"Column is_auto_generated may already exist: {e}")

    # Add source_type column to purchase_orders table
    try:
        with op.batch_alter_table('purchase_orders', schema=None) as batch_op:
            batch_op.add_column(sa.Column('source_type', sa.String(32), nullable=True, server_default='manual'))
    except Exception as e:
        print(f"Column source_type may already exist: {e}")


def downgrade():
    with op.batch_alter_table('purchase_orders', schema=None) as batch_op:
        batch_op.drop_column('source_type')
        batch_op.drop_column('is_auto_generated')
