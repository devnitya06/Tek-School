"""Create demo management tables

Revision ID: a1b2c3d4e5f6
Revises: fa70edb0e479
Create Date: 2026-09-17 12:25:00.000000

Creates the following tables for the Demo Management System:
  - demo_configurations
  - demo_requests
  - demo_request_images
  - demo_otps
  - demo_access_attempts
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'fa70edb0e479'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── demo_configurations ──────────────────────────────────────────────────
    op.create_table(
        'demo_configurations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('start_time', sa.Time(), nullable=False),
        sa.Column('end_time', sa.Time(), nullable=False),
        sa.Column('user_limit', sa.Integer(), nullable=False),
        sa.Column('demo_days', postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column('presented_by', sa.String(length=255), nullable=False),
        sa.Column('demonstration_link', sa.String(length=1024), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_demo_configurations_id'), 'demo_configurations', ['id'], unique=False)

    # ── demo_requests ────────────────────────────────────────────────────────
    op.create_table(
        'demo_requests',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('request_code', sa.String(length=20), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('user_category', sa.String(length=50), nullable=False),
        sa.Column('institution_name', sa.String(length=255), nullable=False),
        sa.Column('full_name', sa.String(length=255), nullable=False),
        sa.Column('designation', sa.String(length=255), nullable=True),
        sa.Column('phone', sa.String(length=20), nullable=False),
        sa.Column('institution_address', sa.Text(), nullable=True),
        sa.Column('area_of_interest', sa.JSON(), nullable=True),
        sa.Column('config_id', sa.Integer(), nullable=False),
        sa.Column('demo_date', sa.Date(), nullable=False),
        sa.Column('start_time', sa.Time(), nullable=False),
        sa.Column('end_time', sa.Time(), nullable=False),
        sa.Column('presented_by', sa.String(length=255), nullable=False),
        sa.Column('demonstration_link', sa.String(length=1024), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='PENDING'),
        sa.Column('access_code', sa.String(length=6), nullable=True),
        sa.Column('feedback_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['config_id'], ['demo_configurations.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('request_code'),
    )
    op.create_index(op.f('ix_demo_requests_id'), 'demo_requests', ['id'], unique=False)
    op.create_index(op.f('ix_demo_requests_request_code'), 'demo_requests', ['request_code'], unique=True)
    op.create_index(op.f('ix_demo_requests_email'), 'demo_requests', ['email'], unique=False)
    op.create_index(op.f('ix_demo_requests_phone'), 'demo_requests', ['phone'], unique=False)
    op.create_index(op.f('ix_demo_requests_config_id'), 'demo_requests', ['config_id'], unique=False)
    op.create_index(op.f('ix_demo_requests_demo_date'), 'demo_requests', ['demo_date'], unique=False)
    op.create_index(op.f('ix_demo_requests_status'), 'demo_requests', ['status'], unique=False)
    op.create_index(op.f('ix_demo_requests_created_at'), 'demo_requests', ['created_at'], unique=False)
    # Composite index for slot capacity queries
    op.create_index(
        'ix_demo_requests_slot',
        'demo_requests',
        ['config_id', 'demo_date', 'start_time', 'status'],
        unique=False,
    )

    # ── demo_request_images ──────────────────────────────────────────────────
    op.create_table(
        'demo_request_images',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('demo_request_id', sa.Integer(), nullable=False),
        sa.Column('image_url', sa.String(length=1024), nullable=False),
        sa.Column('file_name', sa.String(length=255), nullable=True),
        sa.Column('file_size', sa.BigInteger(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['demo_request_id'], ['demo_requests.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_demo_request_images_id'), 'demo_request_images', ['id'], unique=False)
    op.create_index(
        op.f('ix_demo_request_images_demo_request_id'),
        'demo_request_images',
        ['demo_request_id'],
        unique=False,
    )

    # ── demo_otps ────────────────────────────────────────────────────────────
    op.create_table(
        'demo_otps',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('otp_code', sa.String(length=6), nullable=False),
        sa.Column('is_verified', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('attempt_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('resend_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('request_payload', sa.JSON(), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_demo_otps_id'), 'demo_otps', ['id'], unique=False)
    op.create_index(op.f('ix_demo_otps_email'), 'demo_otps', ['email'], unique=False)

    # ── demo_access_attempts ──────────────────────────────────────────────────
    op.create_table(
        'demo_access_attempts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('attempt_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('window_start', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_demo_access_attempts_id'), 'demo_access_attempts', ['id'], unique=False)
    op.create_index(
        op.f('ix_demo_access_attempts_email'), 'demo_access_attempts', ['email'], unique=False
    )


def downgrade() -> None:
    op.drop_table('demo_access_attempts')
    op.drop_table('demo_otps')
    op.drop_index(op.f('ix_demo_request_images_demo_request_id'), table_name='demo_request_images')
    op.drop_table('demo_request_images')
    op.drop_index('ix_demo_requests_slot', table_name='demo_requests')
    op.drop_index(op.f('ix_demo_requests_created_at'), table_name='demo_requests')
    op.drop_index(op.f('ix_demo_requests_status'), table_name='demo_requests')
    op.drop_index(op.f('ix_demo_requests_demo_date'), table_name='demo_requests')
    op.drop_index(op.f('ix_demo_requests_config_id'), table_name='demo_requests')
    op.drop_index(op.f('ix_demo_requests_phone'), table_name='demo_requests')
    op.drop_index(op.f('ix_demo_requests_email'), table_name='demo_requests')
    op.drop_index(op.f('ix_demo_requests_request_code'), table_name='demo_requests')
    op.drop_table('demo_requests')
    op.drop_index(op.f('ix_demo_configurations_id'), table_name='demo_configurations')
    op.drop_table('demo_configurations')
