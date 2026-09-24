"""add preferred_language to demo_requests

Revision ID: cd212503422c
Revises: b2a4d9f7f11a
Create Date: 2026-09-24

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'cd212503422c'
down_revision = 'b2a4d9f7f11a'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'demo_requests',
        sa.Column('preferred_language', sa.String(length=20), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('demo_requests', 'preferred_language')
