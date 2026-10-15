"""Agent Phase 4: institution digital profile, verification and earnings

Revision ID: f4a5b6c7d8e9
Revises: e2f3a4b5c6d7
Create Date: 2026-10-14 17:00:00.000000

Changes:
  1. Add agent creator-tracking columns to schools table.
  2. Add confirmation flag columns to schools table.
  3. Add institution verification lifecycle columns to schools table.
  4. Add indexes for common filters.

All new columns are nullable with safe defaults. No existing data altered.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f4a5b6c7d8e9"
down_revision: Union[str, tuple] = "e2f3a4b5c6d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Agent creator-tracking
    op.add_column("schools", sa.Column("created_by_role", sa.String(32), nullable=True))
    op.add_column(
        "schools",
        sa.Column(
            "created_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column("schools", sa.Column("created_by_name", sa.String(255), nullable=True))
    op.add_column(
        "schools",
        sa.Column(
            "created_by_agent_profile_id",
            sa.Integer(),
            sa.ForeignKey("agent_profiles.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    # 2. Agent institution confirmations
    op.add_column(
        "schools",
        sa.Column(
            "confirms_educational_institution",
            sa.Boolean(),
            nullable=True,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "schools",
        sa.Column(
            "confirms_contact_information",
            sa.Boolean(),
            nullable=True,
            server_default=sa.text("false"),
        ),
    )
    op.add_column("schools", sa.Column("confirmation_educational_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("schools", sa.Column("confirmation_contact_at", sa.DateTime(timezone=True), nullable=True))

    # 3. Institution verification lifecycle
    op.add_column("schools", sa.Column("institution_verification_status", sa.String(32), nullable=True))
    op.add_column("schools", sa.Column("institution_submitted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "schools",
        sa.Column(
            "institution_submitted_by_agent_id",
            sa.Integer(),
            sa.ForeignKey("agent_profiles.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "schools",
        sa.Column(
            "institution_verified_by",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column("schools", sa.Column("institution_verified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("schools", sa.Column("institution_rejection_reason", sa.String(1000), nullable=True))

    # 4. Indexes
    op.create_index("ix_schools_institution_verification_status", "schools", ["institution_verification_status"])
    op.create_index("ix_schools_created_by_agent_profile_id", "schools", ["created_by_agent_profile_id"])


def downgrade() -> None:
    op.drop_index("ix_schools_created_by_agent_profile_id", table_name="schools")
    op.drop_index("ix_schools_institution_verification_status", table_name="schools")
    op.drop_column("schools", "institution_rejection_reason")
    op.drop_column("schools", "institution_verified_at")
    op.drop_column("schools", "institution_verified_by")
    op.drop_column("schools", "institution_submitted_by_agent_id")
    op.drop_column("schools", "institution_submitted_at")
    op.drop_column("schools", "institution_verification_status")
    op.drop_column("schools", "confirmation_contact_at")
    op.drop_column("schools", "confirmation_educational_at")
    op.drop_column("schools", "confirms_contact_information")
    op.drop_column("schools", "confirms_educational_institution")
    op.drop_column("schools", "created_by_agent_profile_id")
    op.drop_column("schools", "created_by_name")
    op.drop_column("schools", "created_by_user_id")
    op.drop_column("schools", "created_by_role")
