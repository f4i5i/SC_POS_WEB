"""Add is_made_to_order field

Revision ID: dee1b64351a7
Revises: b6bb3cbb8470
Create Date: 2026-01-17 22:08:41.211505

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'dee1b64351a7'
down_revision = 'b6bb3cbb8470'
branch_labels = None
depends_on = None


def upgrade():
    # Add is_made_to_order column to products table
    # Note: Column may already exist if added manually
    try:
        with op.batch_alter_table('products', schema=None) as batch_op:
            batch_op.add_column(sa.Column('is_made_to_order', sa.Boolean(), nullable=True, default=False))
    except Exception as e:
        print(f"Column may already exist: {e}")


def downgrade():
    with op.batch_alter_table('products', schema=None) as batch_op:
        batch_op.drop_column('is_made_to_order')
