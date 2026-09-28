"""Add soft delete fields to users and account_deletion_otps table

Revision ID: e1a2b3c4d5e6
Revises: cd212503422c, a8b3c9d1e2f4
Create Date: 2026-09-28 11:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e1a2b3c4d5e6'
down_revision: Union[str, tuple] = ('cd212503422c', 'a8b3c9d1e2f4')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add soft-delete columns to users table and create account_deletion_otps table."""

    # ------------------------------------------------------------------
    # 1. Soft-delete columns on users
    # ------------------------------------------------------------------
    op.add_column(
        'users',
        sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default=sa.text('false'))
    )
    op.add_column(
        'users',
        sa.Column('deleted_at', sa.DateTime(), nullable=True)
    )
    op.add_column(
        'users',
        sa.Column('deleted_by', sa.Integer(), nullable=True)
    )
    op.add_column(
        'users',
        sa.Column('deletion_reason', sa.String(), nullable=True)
    )

    # Index for fast deleted-user queries (admin panel)
    op.create_index('ix_users_is_deleted', 'users', ['is_deleted'], unique=False)

    # ------------------------------------------------------------------
    # 2. Dedicated OTP table for account deletion
    # ------------------------------------------------------------------
    op.create_table(
        'account_deletion_otps',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('otp_hash', sa.String(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('max_attempts', sa.Integer(), nullable=False, server_default='5'),
        sa.Column('is_verified', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()')),
        sa.Column('verified_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_account_deletion_otps_id', 'account_deletion_otps', ['id'], unique=False)
    op.create_index('ix_account_deletion_otps_user_id', 'account_deletion_otps', ['user_id'], unique=False)


def downgrade() -> None:
    """Remove soft-delete columns from users and drop account_deletion_otps table."""
    op.drop_index('ix_account_deletion_otps_user_id', table_name='account_deletion_otps')
    op.drop_index('ix_account_deletion_otps_id', table_name='account_deletion_otps')
    op.drop_table('account_deletion_otps')

    op.drop_index('ix_users_is_deleted', table_name='users')
    op.drop_column('users', 'deletion_reason')
    op.drop_column('users', 'deleted_by')
    op.drop_column('users', 'deleted_at')
    op.drop_column('users', 'is_deleted')
