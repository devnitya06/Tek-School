"""Agent Phase 2: payment configuration, earnings ledger, wants_initial_bonus

Revision ID: c4d5e6f7a8b9
Revises: a9b8c7d6e5f4
Create Date: 2026-10-12 17:45:00.000000

Changes:
  1. Add wants_initial_bonus (BOOLEAN NOT NULL DEFAULT FALSE) to agent_profiles
  2. Create agent_payment_configs table (one per agent, UNIQUE on agent_profile_id)
  3. Create agent_earnings table (immutable ledger, UNIQUE on agent_profile_id+type+ref)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c4d5e6f7a8b9'
down_revision: Union[str, tuple] = 'a9b8c7d6e5f4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if (
        inspector.has_table("agent_payment_configs")
        and inspector.has_table("agent_earnings")
        and any(
            column["name"] == "wants_initial_bonus"
            for column in inspector.get_columns("agent_profiles")
        )
    ):
        return

    # 1. Add wants_initial_bonus to agent_profiles
    op.add_column(
        'agent_profiles',
        sa.Column(
            'wants_initial_bonus',
            sa.Boolean(),
            nullable=False,
            server_default=sa.text('false'),
        )
    )

    # 2. Create agent_payment_configs
    op.create_table(
        'agent_payment_configs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('agent_profile_id', sa.Integer(), nullable=False),

        # Institution Digital Profile
        sa.Column('idp_is_enabled', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('idp_rate', sa.Numeric(12, 2), nullable=False, server_default='0.00'),

        # Daily Stipend
        sa.Column('stipend_is_enabled', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('stipend_daily_rate', sa.Numeric(12, 2), nullable=False, server_default='0.00'),

        # Physical Verification
        sa.Column('pv_is_enabled', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('pv_rate', sa.Numeric(12, 2), nullable=False, server_default='0.00'),

        # Online Demonstration
        sa.Column('od_is_enabled', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('od_rate', sa.Numeric(12, 2), nullable=False, server_default='0.00'),

        # Offline Demonstration
        sa.Column('offd_is_enabled', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('offd_rate', sa.Numeric(12, 2), nullable=False, server_default='0.00'),

        # Other Activities
        sa.Column('oa_is_enabled', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('oa_rate', sa.Numeric(12, 2), nullable=False, server_default='0.00'),

        # Initial Bonus
        sa.Column('initial_bonus', sa.Numeric(12, 2), nullable=False, server_default='0.00'),
        sa.Column('is_bonus_withdrawn', sa.Boolean(), nullable=False, server_default=sa.text('false')),

        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),

        # Audit
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('updated_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),

        # Constraints
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('agent_profile_id', name='uq_agent_payment_config_profile'),
        sa.ForeignKeyConstraint(['agent_profile_id'], ['agent_profiles.id'], ondelete='CASCADE'),
    )
    op.create_index('ix_agent_payment_configs_id', 'agent_payment_configs', ['id'], unique=False)
    op.create_index('ix_agent_payment_configs_agent_profile_id', 'agent_payment_configs', ['agent_profile_id'], unique=True)

    # 3. Create agent_earnings
    op.create_table(
        'agent_earnings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('agent_profile_id', sa.Integer(), nullable=False),
        sa.Column('earning_type', sa.String(64), nullable=False),
        sa.Column('status', sa.String(32), nullable=False, server_default='PENDING'),
        sa.Column('reference_type', sa.String(64), nullable=True),
        sa.Column('reference_id', sa.String(128), nullable=True),
        sa.Column('applied_rate', sa.Numeric(12, 2), nullable=False),
        sa.Column('amount', sa.Numeric(12, 2), nullable=False),
        sa.Column('earning_date', sa.Date(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('approved_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),

        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'agent_profile_id', 'earning_type', 'reference_id',
            name='uq_agent_earning_type_ref'
        ),
        sa.ForeignKeyConstraint(['agent_profile_id'], ['agent_profiles.id'], ondelete='CASCADE'),
    )
    op.create_index('ix_agent_earnings_id', 'agent_earnings', ['id'], unique=False)
    op.create_index('ix_agent_earnings_agent_profile_id', 'agent_earnings', ['agent_profile_id'], unique=False)
    op.create_index('ix_agent_earnings_earning_type', 'agent_earnings', ['earning_type'], unique=False)
    op.create_index('ix_agent_earnings_status', 'agent_earnings', ['status'], unique=False)
    op.create_index('ix_agent_earnings_reference_id', 'agent_earnings', ['reference_id'], unique=False)
    op.create_index('ix_agent_earnings_created_at', 'agent_earnings', ['created_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_agent_earnings_created_at', table_name='agent_earnings')
    op.drop_index('ix_agent_earnings_reference_id', table_name='agent_earnings')
    op.drop_index('ix_agent_earnings_status', table_name='agent_earnings')
    op.drop_index('ix_agent_earnings_earning_type', table_name='agent_earnings')
    op.drop_index('ix_agent_earnings_agent_profile_id', table_name='agent_earnings')
    op.drop_index('ix_agent_earnings_id', table_name='agent_earnings')
    op.drop_table('agent_earnings')

    op.drop_index('ix_agent_payment_configs_agent_profile_id', table_name='agent_payment_configs')
    op.drop_index('ix_agent_payment_configs_id', table_name='agent_payment_configs')
    op.drop_table('agent_payment_configs')

    op.drop_column('agent_profiles', 'wants_initial_bonus')
