"""add error_logs table and is_developer field

Revision ID: ff4d33dfdc6d
Revises: c1d2e3f4a5b6
Create Date: 2026-02-08 00:29:44.243165

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = 'ff4d33dfdc6d'
down_revision = 'c1d2e3f4a5b6'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_tables = inspector.get_table_names()

    if 'error_logs' not in existing_tables:
        op.create_table('error_logs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('timestamp', sa.DateTime(), nullable=False),
    sa.Column('error_type', sa.String(length=128), nullable=False),
    sa.Column('error_message', sa.Text(), nullable=False),
    sa.Column('traceback', sa.Text(), nullable=True),
    sa.Column('request_url', sa.String(length=512), nullable=True),
    sa.Column('request_method', sa.String(length=10), nullable=True),
    sa.Column('request_data', sa.Text(), nullable=True),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('ip_address', sa.String(length=64), nullable=True),
    sa.Column('user_agent', sa.String(length=512), nullable=True),
    sa.Column('status_code', sa.Integer(), nullable=True),
    sa.Column('blueprint', sa.String(length=64), nullable=True),
    sa.Column('endpoint', sa.String(length=128), nullable=True),
    sa.Column('is_resolved', sa.Boolean(), nullable=True),
    sa.Column('resolved_by', sa.Integer(), nullable=True),
    sa.Column('resolved_at', sa.DateTime(), nullable=True),
    sa.Column('resolution_notes', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['resolved_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
        )
        with op.batch_alter_table('error_logs', schema=None) as batch_op:
            batch_op.create_index('ix_error_logs_error_type', ['error_type'], unique=False)
            batch_op.create_index('ix_error_logs_status_code', ['status_code'], unique=False)
            batch_op.create_index('ix_error_logs_timestamp', ['timestamp'], unique=False)
            batch_op.create_index('ix_error_logs_type_timestamp', ['error_type', 'timestamp'], unique=False)

    existing_columns = [c['name'] for c in inspector.get_columns('users')]
    if 'is_developer' not in existing_columns:
        with op.batch_alter_table('users', schema=None) as batch_op:
            batch_op.add_column(sa.Column('is_developer', sa.Boolean(), nullable=True))


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('is_developer')

    with op.batch_alter_table('error_logs', schema=None) as batch_op:
        batch_op.drop_index('ix_error_logs_type_timestamp')
        batch_op.drop_index('ix_error_logs_timestamp')
        batch_op.drop_index('ix_error_logs_status_code')
        batch_op.drop_index('ix_error_logs_error_type')

    op.drop_table('error_logs')
