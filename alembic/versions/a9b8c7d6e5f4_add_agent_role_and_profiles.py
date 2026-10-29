"""Add agent role and create agent_profiles table (full profile fields)

Revision ID: a9b8c7d6e5f4
Revises: e1a2b3c4d5e6
Create Date: 2026-10-12 12:40:00.000000

Two-step agent profile:
  Step 1 fields: first_name, last_name, phone, email, stipend_type
  Step 2 fields: gender, dob, qualification, university, designation,
                 experience, pin_code, division, district, state, landmark
  Permission flags: can_onboard_school, can_enroll_student, can_collect_fees,
                    can_do_followup, can_verify_documents, can_coordinate_events
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'a9b8c7d6e5f4'
down_revision: Union[str, tuple] = 'e1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Startup schema synchronization may have created this table before
    # Alembic recorded the corresponding revision.
    if sa.inspect(op.get_bind()).has_table("agent_profiles"):
        return

    # The existing project stores users.role as VARCHAR via TypeDecorator.
    # Adding 'agent' to the Python UserRole enum is sufficient - no ALTER TYPE.

    # 1. Create stipend_type_enum
    op.execute(
        "DO $$ BEGIN "
        "  CREATE TYPE stipend_type_enum AS ENUM ('WITH_STIPEND', 'WITHOUT_STIPEND'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; "
        "END $$;"
    )

    # 2. Create agent_gender_enum
    op.execute(
        "DO $$ BEGIN "
        "  CREATE TYPE agent_gender_enum AS ENUM ('male', 'female', 'other'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; "
        "END $$;"
    )

    # 3. Create agent_experience_enum
    op.execute(
        "DO $$ BEGIN "
        "  CREATE TYPE agent_experience_enum AS ENUM ('fresher', 'experienced'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; "
        "END $$;"
    )

    # 4. Create agent_profiles table
    op.create_table(
        'agent_profiles',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(),
                  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('agent_id', sa.String(length=20), nullable=False),

        # Step-1 fields
        sa.Column('first_name', sa.String(length=100), nullable=False),
        sa.Column('last_name',  sa.String(length=100), nullable=False),
        sa.Column('phone', sa.String(length=20), nullable=True),
        sa.Column('email', sa.String(length=255), nullable=True),
        sa.Column(
            'stipend_type',
            postgresql.ENUM('WITH_STIPEND', 'WITHOUT_STIPEND',
                             name='stipend_type_enum', create_type=False),
            nullable=False,
            server_default='WITHOUT_STIPEND',
        ),

        # Step-2 profile fields
        sa.Column(
            'gender',
            postgresql.ENUM('male', 'female', 'other',
                             name='agent_gender_enum', create_type=False),
            nullable=True,
        ),
        sa.Column('dob', sa.Date(), nullable=True),
        sa.Column('qualification', sa.String(length=255), nullable=True),
        sa.Column('university',    sa.String(length=255), nullable=True),
        sa.Column('designation',   sa.String(length=255), nullable=True),
        sa.Column(
            'experience',
            postgresql.ENUM('fresher', 'experienced',
                             name='agent_experience_enum', create_type=False),
            nullable=True,
        ),

        # Address / Location
        sa.Column('pin_code',  sa.String(length=10),  nullable=True),
        sa.Column('division',  sa.String(length=100), nullable=True),
        sa.Column('district',  sa.String(length=100), nullable=True),
        sa.Column('state',     sa.String(length=100), nullable=True),
        sa.Column('landmark',  sa.String(length=255), nullable=True),

        # Activity permission flags
        sa.Column('can_onboard_school',    sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('can_enroll_student',    sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('can_collect_fees',      sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('can_do_followup',       sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('can_verify_documents',  sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('can_coordinate_events', sa.Boolean(), nullable=False, server_default=sa.text('false')),

        # Profile completion
        sa.Column('profile_completed_step2', sa.Boolean(), nullable=False, server_default=sa.text('false')),

        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),

        # Constraints
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id',   name='uq_agent_profiles_user_id'),
        sa.UniqueConstraint('agent_id',  name='uq_agent_profiles_agent_id'),
    )

    op.create_index('ix_agent_profiles_id',       'agent_profiles', ['id'],       unique=False)
    op.create_index('ix_agent_profiles_user_id',  'agent_profiles', ['user_id'],  unique=True)
    op.create_index('ix_agent_profiles_agent_id', 'agent_profiles', ['agent_id'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_agent_profiles_agent_id', table_name='agent_profiles')
    op.drop_index('ix_agent_profiles_user_id',  table_name='agent_profiles')
    op.drop_index('ix_agent_profiles_id',        table_name='agent_profiles')
    op.drop_table('agent_profiles')
    op.execute("DROP TYPE IF EXISTS agent_experience_enum;")
    op.execute("DROP TYPE IF EXISTS agent_gender_enum;")
    op.execute("DROP TYPE IF EXISTS stipend_type_enum;")
