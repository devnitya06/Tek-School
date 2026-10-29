"""Use institution digital profile configuration for agent onboarding.

Revision ID: a6c5d4e3f2b1
Revises: c8d7e6f5a4b3
Create Date: 2026-10-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a6c5d4e3f2b1"
down_revision: Union[str, None] = "c8d7e6f5a4b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    columns = sa.inspect(op.get_bind()).get_columns("agent_profiles")
    if any(column["name"] == "can_onboard_school" for column in columns):
        op.drop_column("agent_profiles", "can_onboard_school")


def downgrade() -> None:
    columns = sa.inspect(op.get_bind()).get_columns("agent_profiles")
    if not any(column["name"] == "can_onboard_school" for column in columns):
        op.add_column(
            "agent_profiles",
            sa.Column(
                "can_onboard_school",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )
