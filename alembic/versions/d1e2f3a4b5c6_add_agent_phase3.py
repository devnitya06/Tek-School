"""Agent Phase 3: payment accounts, withdrawals, withdrawal history

Revision ID: d1e2f3a4b5c6
Revises: c4d5e6f7a8b9
Create Date: 2026-10-13 19:00:00.000000

Changes:
  1. Create agent_payment_accounts table
  2. Create agent_withdrawals table (with unique transaction_id)
  3. Create agent_withdrawal_history table
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d1e2f3a4b5c6"
down_revision: Union[str, tuple] = "c4d5e6f7a8b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. agent_payment_accounts
    op.create_table(
        "agent_payment_accounts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("agent_profile_id", sa.Integer(), nullable=False),
        sa.Column("account_holder_name", sa.String(255), nullable=False),
        sa.Column("payment_method", sa.String(32), nullable=False),
        sa.Column("upi_id", sa.String(128), nullable=True),
        sa.Column("bank_account_number", sa.String(64), nullable=True),
        sa.Column("ifsc_code", sa.String(20), nullable=True),
        sa.Column("bank_name", sa.String(255), nullable=True),
        sa.Column("branch_name", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["agent_profile_id"], ["agent_profiles.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("agent_profile_id", name="uq_agent_payment_account_profile"),
    )
    op.create_index("ix_agent_payment_accounts_id", "agent_payment_accounts", ["id"])
    op.create_index("ix_agent_payment_accounts_profile", "agent_payment_accounts", ["agent_profile_id"])
    op.create_index("ix_agent_payment_accounts_method", "agent_payment_accounts", ["payment_method"])

    # 2. agent_withdrawals
    op.create_table(
        "agent_withdrawals",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("agent_profile_id", sa.Integer(), nullable=False),
        sa.Column("requested_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="PENDING"),
        sa.Column("agent_remarks", sa.Text(), nullable=True),
        # Payment snapshot
        sa.Column("payment_method_snapshot", sa.String(32), nullable=True),
        sa.Column("upi_id_snapshot", sa.String(128), nullable=True),
        sa.Column("bank_account_masked_snapshot", sa.String(64), nullable=True),
        sa.Column("ifsc_snapshot", sa.String(20), nullable=True),
        sa.Column("bank_name_snapshot", sa.String(255), nullable=True),
        sa.Column("account_holder_name_snapshot", sa.String(255), nullable=True),
        # Admin review
        sa.Column("admin_remarks", sa.Text(), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        # Payment details
        sa.Column("transaction_id", sa.String(128), nullable=True, unique=True),
        sa.Column("transaction_date", sa.Date(), nullable=True),
        sa.Column("actual_paid_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("payment_proof_url", sa.Text(), nullable=True),
        sa.Column("payment_proof_s3_key", sa.Text(), nullable=True),
        sa.Column("paid_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        # Reservation guard
        sa.Column("reservation_released", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["agent_profile_id"], ["agent_profiles.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("transaction_id", name="uq_agent_withdrawal_transaction_id"),
    )
    op.create_index("ix_agent_withdrawals_id", "agent_withdrawals", ["id"])
    op.create_index("ix_agent_withdrawals_profile_status", "agent_withdrawals", ["agent_profile_id", "status"])
    op.create_index("ix_agent_withdrawals_created", "agent_withdrawals", ["created_at"])
    op.create_index("ix_agent_withdrawals_status", "agent_withdrawals", ["status"])

    # 3. agent_withdrawal_history
    op.create_table(
        "agent_withdrawal_history",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("withdrawal_id", sa.Integer(), nullable=False),
        sa.Column("agent_profile_id", sa.Integer(), nullable=False),
        sa.Column("from_status", sa.String(32), nullable=True),
        sa.Column("to_status", sa.String(32), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("transaction_id", sa.String(128), nullable=True),
        sa.Column("transaction_date", sa.Date(), nullable=True),
        sa.Column("payment_proof_url", sa.Text(), nullable=True),
        sa.Column("actual_paid_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["withdrawal_id"], ["agent_withdrawals.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_withdrawal_history_withdrawal", "agent_withdrawal_history", ["withdrawal_id"])
    op.create_index("ix_withdrawal_history_agent", "agent_withdrawal_history", ["agent_profile_id"])
    op.create_index("ix_withdrawal_history_created", "agent_withdrawal_history", ["created_at"])


def downgrade() -> None:
    op.drop_table("agent_withdrawal_history")
    op.drop_table("agent_withdrawals")
    op.drop_table("agent_payment_accounts")
