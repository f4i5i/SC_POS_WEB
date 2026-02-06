"""Allow perfume recipes to be produced at kiosks and fix is_packaging flags

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

    # Fix oil ingredients wrongly marked as packaging
    # Set is_packaging=0 for any ingredient whose raw material is in the OIL category
    op.execute("""
        UPDATE recipe_ingredients SET is_packaging = 0
        WHERE raw_material_id IN (
            SELECT rm.id FROM raw_materials rm
            JOIN raw_material_categories rmc ON rm.category_id = rmc.id
            WHERE rmc.code = 'OIL'
        ) AND is_packaging = 1
    """)

    # Ensure bottle ingredients are marked as packaging
    op.execute("""
        UPDATE recipe_ingredients SET is_packaging = 1
        WHERE raw_material_id IN (
            SELECT rm.id FROM raw_materials rm
            JOIN raw_material_categories rmc ON rm.category_id = rmc.id
            WHERE rmc.code = 'BOTTLE'
        ) AND is_packaging = 0
    """)


def downgrade():
    # Revert perfume recipes to not producible at kiosks
    op.execute(
        "UPDATE recipes SET can_produce_at_kiosk = 0 WHERE recipe_type = 'perfume'"
    )
