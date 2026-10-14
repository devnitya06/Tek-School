"""Merge agent phase3 branch with assignment fields branch

Revision ID: e2f3a4b5c6d7
Revises: c1d2e3f4a5b6, d1e2f3a4b5c6
Create Date: 2026-10-14 11:51:00.000000

This is a merge migration that unifies two independent heads:
  - c1d2e3f4a5b6  (add_assignment_fields_to_business_inquiry_school)
  - d1e2f3a4b5c6  (add_agent_phase3)

No schema changes — only resolves the divergent branch history so
`alembic upgrade head` works without ambiguity.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e2f3a4b5c6d7"
down_revision: Union[str, tuple] = ("c1d2e3f4a5b6", "d1e2f3a4b5c6")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # No schema changes required — this migration only merges branches.
    pass


def downgrade() -> None:
    # No schema changes to reverse.
    pass
