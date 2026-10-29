"""Normalize agent gender enum labels and existing values.

Revision ID: c8d7e6f5a4b3
Revises: d8f3a1c9b742
Create Date: 2026-10-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c8d7e6f5a4b3"
down_revision: Union[str, None] = "d8f3a1c9b742"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    gender_column_exists = bind.execute(
        sa.text(
            "SELECT EXISTS ("
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema = current_schema() "
            "AND table_name = 'agent_profiles' AND column_name = 'gender'"
            ")"
        )
    ).scalar_one()
    if not gender_column_exists:
        return

    op.execute(
        "CREATE TYPE agent_gender_enum_normalized AS ENUM "
        "('male', 'female', 'other')"
    )
    op.execute(
        """
        ALTER TABLE agent_profiles
        ALTER COLUMN gender TYPE agent_gender_enum_normalized
        USING (
            CASE lower(gender::text)
                WHEN 'male' THEN 'male'
                WHEN 'female' THEN 'female'
                WHEN 'other' THEN 'other'
                ELSE NULL
            END
        )::agent_gender_enum_normalized
        """
    )
    op.execute("DROP TYPE agent_gender_enum")
    op.execute(
        "ALTER TYPE agent_gender_enum_normalized RENAME TO agent_gender_enum"
    )


def downgrade() -> None:
    # Keep the canonical lower-case enum labels; reverting them would make
    # current application versions unable to deserialize stored values.
    pass
