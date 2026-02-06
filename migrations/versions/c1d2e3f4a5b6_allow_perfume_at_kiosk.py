"""Allow perfume recipes to be produced at kiosks

Revision ID: c1d2e3f4a5b6
Revises: b6156e3f7782
Create Date: 2026-02-06 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c1d2e3f4a5b6'
down_revision = 'b6156e3f7782'
branch_labels = None
depends_on = None


def upgrade():
    # Update existing perfume recipes to allow production at kiosks
    op.execute(
        "UPDATE recipes SET can_produce_at_kiosk = 1 WHERE recipe_type = 'perfume' AND can_produce_at_kiosk = 0"
    )


def downgrade():
    # Revert perfume recipes to not producible at kiosks
    op.execute(
        "UPDATE recipes SET can_produce_at_kiosk = 0 WHERE recipe_type = 'perfume'"
    )
