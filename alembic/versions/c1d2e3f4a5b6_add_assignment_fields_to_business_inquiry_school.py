"""Add assignment fields to business_inquiry_school

Revision ID: c1d2e3f4a5b6
Revises: e1a2b3c4d5e6
Create Date: 2026-09-29 15:10:00.000000

Adds per-school employee assignment fields to business_inquiry_school.
No existing columns are modified. All new columns are nullable so that
existing rows require no data backfill.

New columns:
    assigned_to_name         VARCHAR(255)  -- employee name (set when assigning)
    assigned_to_designation  VARCHAR(100)  -- optional designation
    assigned_to_phone        VARCHAR(20)   -- optional phone
    assigned_to_email        VARCHAR(255)  -- optional email
    assigned_at              TIMESTAMPTZ   -- server-set when assignment written/updated
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "c1d2e3f4a5b6"
down_revision: Union[str, None] = "e1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "business_inquiry_school",
        sa.Column("assigned_to_name", sa.String(255), nullable=True),
    )
    op.add_column(
        "business_inquiry_school",
        sa.Column("assigned_to_designation", sa.String(100), nullable=True),
    )
    op.add_column(
        "business_inquiry_school",
        sa.Column("assigned_to_phone", sa.String(20), nullable=True),
    )
    op.add_column(
        "business_inquiry_school",
        sa.Column("assigned_to_email", sa.String(255), nullable=True),
    )
    op.add_column(
        "business_inquiry_school",
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("business_inquiry_school", "assigned_at")
    op.drop_column("business_inquiry_school", "assigned_to_email")
    op.drop_column("business_inquiry_school", "assigned_to_phone")
    op.drop_column("business_inquiry_school", "assigned_to_designation")
    op.drop_column("business_inquiry_school", "assigned_to_name")
