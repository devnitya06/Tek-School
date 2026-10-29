"""Store agent experience as free-form text.

Revision ID: 9a7b6c5d4e3f
Revises: f4a5b6c7d8e9
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9a7b6c5d4e3f"
down_revision: Union[str, tuple] = "f4a5b6c7d8e9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    experience_type = op.get_bind().execute(
        sa.text(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_schema = current_schema() "
            "AND table_name = 'agent_profiles' AND column_name = 'experience'"
        )
    ).scalar_one_or_none()
    if experience_type != "text":
        op.alter_column(
            "agent_profiles",
            "experience",
            existing_type=sa.Enum(
                "fresher",
                "experienced",
                name="agent_experience_enum",
            ),
            type_=sa.Text(),
            postgresql_using="experience::text",
        )
    op.execute("DROP TYPE IF EXISTS agent_experience_enum")


def downgrade() -> None:
    op.execute(
        "CREATE TYPE agent_experience_enum AS ENUM ('fresher', 'experienced')"
    )
    op.alter_column(
        "agent_profiles",
        "experience",
        existing_type=sa.Text(),
        type_=sa.Enum(
            "fresher",
            "experienced",
            name="agent_experience_enum",
        ),
        postgresql_using="experience::agent_experience_enum",
    )
