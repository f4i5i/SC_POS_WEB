"""Add kiosk_cost to products

Revision ID: f8a2c3d4e5f6
Revises: dee1b64351a7
Create Date: 2026-01-22 17:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f8a2c3d4e5f6'
down_revision = 'dee1b64351a7'
branch_labels = None
depends_on = None


def upgrade():
    # Add kiosk_cost column to products table
    try:
        with op.batch_alter_table('products', schema=None) as batch_op:
            batch_op.add_column(sa.Column('kiosk_cost', sa.Numeric(10, 2), nullable=True, server_default='0.00'))
    except Exception as e:
        print(f"Column may already exist: {e}")


def downgrade():
    with op.batch_alter_table('products', schema=None) as batch_op:
        batch_op.drop_column('kiosk_cost')
