"""Add monthly stipend rate snapshots and configuration effective date.

Revision ID: b7c8d9e0f123
Revises: 9a7b6c5d4e3f
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b7c8d9e0f123"
down_revision: Union[str, tuple] = "9a7b6c5d4e3f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    payment_columns = (
        {column["name"] for column in inspector.get_columns("agent_payment_configs")}
        if inspector.has_table("agent_payment_configs")
        else set()
    )
    if (
        {
            "stipend_monthly_is_enabled",
            "stipend_monthly_rate",
            "stipend_effective_from",
            "effective_from",
        }.issubset(payment_columns)
        and inspector.has_table("agent_stipend_rates")
    ):
        return

    op.add_column(
        "agent_payment_configs",
        sa.Column(
            "stipend_monthly_is_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "agent_payment_configs",
        sa.Column(
            "stipend_monthly_rate",
            sa.Numeric(12, 2),
            nullable=False,
            server_default="0.00",
        ),
    )
    op.add_column(
        "agent_payment_configs",
        sa.Column("stipend_effective_from", sa.Date(), nullable=True),
    )
    op.add_column(
        "agent_payment_configs",
        sa.Column(
            "effective_from",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_table(
        "agent_stipend_rates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("agent_profile_id", sa.Integer(), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("monthly_rate", sa.Numeric(12, 2), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["agent_profile_id"],
            ["agent_profiles.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "agent_profile_id",
            "effective_from",
            name="uq_agent_stipend_rate_effective_from",
        ),
    )
    op.create_index(
        "ix_agent_stipend_rates_agent_profile_id",
        "agent_stipend_rates",
        ["agent_profile_id"],
    )
    op.create_index(
        "ix_agent_stipend_rates_effective_from",
        "agent_stipend_rates",
        ["effective_from"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_agent_stipend_rates_effective_from",
        table_name="agent_stipend_rates",
    )
    op.drop_index(
        "ix_agent_stipend_rates_agent_profile_id",
        table_name="agent_stipend_rates",
    )
    op.drop_table("agent_stipend_rates")
    op.drop_column("agent_payment_configs", "effective_from")
    op.drop_column("agent_payment_configs", "stipend_effective_from")
    op.drop_column("agent_payment_configs", "stipend_monthly_rate")
    op.drop_column("agent_payment_configs", "stipend_monthly_is_enabled")
