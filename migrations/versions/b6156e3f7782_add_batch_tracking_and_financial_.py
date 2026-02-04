"""Add batch tracking and financial control tables

Revision ID: b6156e3f7782
Revises: a1b2c3d4e5f6
Create Date: 2026-02-05 01:19:02.247929

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b6156e3f7782'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    # Add denomination columns to day_closes
    with op.batch_alter_table('day_closes', schema=None) as batch_op:
        batch_op.add_column(sa.Column('denom_5000', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('denom_1000', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('denom_500', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('denom_100', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('denom_50', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('denom_20', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('denom_10', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('denom_5', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('denom_2', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('denom_1', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('counted_total', sa.Numeric(precision=12, scale=2), nullable=True))
        batch_op.add_column(sa.Column('cash_in', sa.Numeric(precision=12, scale=2), nullable=True))
        batch_op.add_column(sa.Column('cash_out', sa.Numeric(precision=12, scale=2), nullable=True))
        batch_op.add_column(sa.Column('variance_status', sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column('variance_approved_by', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('variance_approved_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('variance_reason', sa.Text(), nullable=True))

    # Create product_batches table
    op.create_table('product_batches',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('location_id', sa.Integer(), nullable=False),
        sa.Column('batch_number', sa.String(length=64), nullable=False),
        sa.Column('manufacture_date', sa.Date(), nullable=True),
        sa.Column('expiry_date', sa.Date(), nullable=True),
        sa.Column('initial_quantity', sa.Numeric(precision=12, scale=4), nullable=False),
        sa.Column('current_quantity', sa.Numeric(precision=12, scale=4), nullable=False),
        sa.Column('reserved_quantity', sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column('unit_cost', sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column('total_cost', sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column('supplier_id', sa.Integer(), nullable=True),
        sa.Column('purchase_order_id', sa.Integer(), nullable=True),
        sa.Column('received_date', sa.Date(), nullable=True),
        sa.Column('received_by', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=True),
        sa.Column('disposed_date', sa.Date(), nullable=True),
        sa.Column('disposed_by', sa.Integer(), nullable=True),
        sa.Column('disposal_reason', sa.Text(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['disposed_by'], ['users.id'], ),
        sa.ForeignKeyConstraint(['location_id'], ['locations.id'], ),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ),
        sa.ForeignKeyConstraint(['purchase_order_id'], ['purchase_orders.id'], ),
        sa.ForeignKeyConstraint(['received_by'], ['users.id'], ),
        sa.ForeignKeyConstraint(['supplier_id'], ['suppliers.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('product_id', 'location_id', 'batch_number', name='uix_batch_product_location')
    )
    op.create_index(op.f('ix_product_batches_batch_number'), 'product_batches', ['batch_number'], unique=False)
    op.create_index(op.f('ix_product_batches_expiry_date'), 'product_batches', ['expiry_date'], unique=False)
    op.create_index(op.f('ix_product_batches_location_id'), 'product_batches', ['location_id'], unique=False)
    op.create_index(op.f('ix_product_batches_product_id'), 'product_batches', ['product_id'], unique=False)

    # Create batch_movements table
    op.create_table('batch_movements',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('batch_id', sa.Integer(), nullable=False),
        sa.Column('movement_type', sa.String(length=32), nullable=False),
        sa.Column('quantity', sa.Numeric(precision=12, scale=4), nullable=False),
        sa.Column('quantity_before', sa.Numeric(precision=12, scale=4), nullable=False),
        sa.Column('quantity_after', sa.Numeric(precision=12, scale=4), nullable=False),
        sa.Column('reference_type', sa.String(length=32), nullable=True),
        sa.Column('reference_id', sa.Integer(), nullable=True),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['batch_id'], ['product_batches.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_batch_movements_batch_id'), 'batch_movements', ['batch_id'], unique=False)
    op.create_index(op.f('ix_batch_movements_created_at'), 'batch_movements', ['created_at'], unique=False)

    # Create expiry_alerts table
    op.create_table('expiry_alerts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('batch_id', sa.Integer(), nullable=False),
        sa.Column('alert_type', sa.String(length=32), nullable=False),
        sa.Column('alert_date', sa.Date(), nullable=False),
        sa.Column('expiry_date', sa.Date(), nullable=False),
        sa.Column('notification_sent', sa.Boolean(), nullable=True),
        sa.Column('notification_sent_at', sa.DateTime(), nullable=True),
        sa.Column('notification_method', sa.String(length=32), nullable=True),
        sa.Column('action_taken', sa.String(length=64), nullable=True),
        sa.Column('action_date', sa.Date(), nullable=True),
        sa.Column('action_by', sa.Integer(), nullable=True),
        sa.Column('action_notes', sa.Text(), nullable=True),
        sa.Column('is_resolved', sa.Boolean(), nullable=True),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['action_by'], ['users.id'], ),
        sa.ForeignKeyConstraint(['batch_id'], ['product_batches.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_expiry_alerts_batch_id'), 'expiry_alerts', ['batch_id'], unique=False)


def downgrade():
    # Drop expiry_alerts table
    op.drop_index(op.f('ix_expiry_alerts_batch_id'), table_name='expiry_alerts')
    op.drop_table('expiry_alerts')

    # Drop batch_movements table
    op.drop_index(op.f('ix_batch_movements_created_at'), table_name='batch_movements')
    op.drop_index(op.f('ix_batch_movements_batch_id'), table_name='batch_movements')
    op.drop_table('batch_movements')

    # Drop product_batches table
    op.drop_index(op.f('ix_product_batches_product_id'), table_name='product_batches')
    op.drop_index(op.f('ix_product_batches_location_id'), table_name='product_batches')
    op.drop_index(op.f('ix_product_batches_expiry_date'), table_name='product_batches')
    op.drop_index(op.f('ix_product_batches_batch_number'), table_name='product_batches')
    op.drop_table('product_batches')

    # Remove denomination columns from day_closes
    with op.batch_alter_table('day_closes', schema=None) as batch_op:
        batch_op.drop_column('variance_reason')
        batch_op.drop_column('variance_approved_at')
        batch_op.drop_column('variance_approved_by')
        batch_op.drop_column('variance_status')
        batch_op.drop_column('cash_out')
        batch_op.drop_column('cash_in')
        batch_op.drop_column('counted_total')
        batch_op.drop_column('denom_1')
        batch_op.drop_column('denom_2')
        batch_op.drop_column('denom_5')
        batch_op.drop_column('denom_10')
        batch_op.drop_column('denom_20')
        batch_op.drop_column('denom_50')
        batch_op.drop_column('denom_100')
        batch_op.drop_column('denom_500')
        batch_op.drop_column('denom_1000')
        batch_op.drop_column('denom_5000')
