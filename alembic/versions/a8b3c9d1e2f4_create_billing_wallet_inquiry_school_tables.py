"""Create billing wallet and inquiry school tables

Revision ID: a8b3c9d1e2f4
Revises: fa70edb0e479
Create Date: 2026-09-25 19:25:00.000000

Creates:
    digital_profile_price_config   - pricing tiers per education associate
    wallet_recharge_config         - platform recharge limits
    wallet_recharge_bonus          - bonus slabs for recharge amounts
    school_wallet                  - one wallet per school
    wallet_transactions            - full ledger / audit trail
    business_inquiry_school        - per-school seen-state + billing junction

Does NOT modify any existing tables (backward compatible).
The existing BusinessInquiry table is left untouched.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "a8b3c9d1e2f4"
down_revision: Union[str, None] = "fa70edb0e479"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. digital_profile_price_config
    # ------------------------------------------------------------------
    op.create_table(
        "digital_profile_price_config",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("education_associate", sa.String(64), nullable=False),
        sa.Column(
            "education_offered",
            postgresql.ARRAY(sa.String()),
            nullable=False,
        ),
        sa.Column("first_two_viewer_price", sa.Numeric(12, 2), nullable=False, server_default="50.00"),
        sa.Column("next_five_viewer_price", sa.Numeric(12, 2), nullable=False, server_default="20.00"),
        sa.Column("all_other_viewer_price", sa.Numeric(12, 2), nullable=False, server_default="10.00"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
    )
    op.create_index(
        "ix_dppc_education_associate",
        "digital_profile_price_config",
        ["education_associate"],
    )

    # ------------------------------------------------------------------
    # 2. wallet_recharge_config
    # ------------------------------------------------------------------
    op.create_table(
        "wallet_recharge_config",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("min_recharge_amount", sa.Numeric(12, 2), nullable=False, server_default="500.00"),
        sa.Column("max_recharge_amount", sa.Numeric(12, 2), nullable=False, server_default="20000.00"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
    )

    # ------------------------------------------------------------------
    # 3. wallet_recharge_bonus
    # ------------------------------------------------------------------
    op.create_table(
        "wallet_recharge_bonus",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "recharge_config_id",
            sa.Integer(),
            sa.ForeignKey("wallet_recharge_config.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("recharge_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("bonus_percentage", sa.Numeric(5, 2), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_wrb_config_id",
        "wallet_recharge_bonus",
        ["recharge_config_id"],
    )
    op.create_index(
        "ix_wrb_recharge_amount",
        "wallet_recharge_bonus",
        ["recharge_amount"],
    )

    # ------------------------------------------------------------------
    # 4. school_wallet
    # ------------------------------------------------------------------
    op.create_table(
        "school_wallet",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "school_id",
            sa.String(),
            sa.ForeignKey("schools.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("balance", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
        sa.Column("currency", sa.String(8), nullable=False, server_default="INR"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_school_wallet_school_id", "school_wallet", ["school_id"])

    # ------------------------------------------------------------------
    # 5. wallet_transactions
    # ------------------------------------------------------------------
    op.create_table(
        "wallet_transactions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "school_id",
            sa.String(),
            sa.ForeignKey("schools.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("transaction_type", sa.String(32), nullable=False),
        sa.Column("transaction_status", sa.String(32), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("bonus_amount", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
        sa.Column("total_credit", sa.Numeric(12, 2), nullable=False),
        sa.Column("balance_before", sa.Numeric(12, 2), nullable=True),
        sa.Column("balance_after", sa.Numeric(12, 2), nullable=True),
        sa.Column("currency", sa.String(8), nullable=False, server_default="INR"),
        sa.Column("reference_type", sa.String(64), nullable=True),
        sa.Column("reference_id", sa.String(128), nullable=True),
        sa.Column("payment_provider", sa.String(32), nullable=True),
        sa.Column("payment_order_id", sa.String(128), nullable=True),
        sa.Column("payment_payment_id", sa.String(128), nullable=True),
        sa.Column("payment_signature", sa.String(256), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_wallet_txn_school_id", "wallet_transactions", ["school_id"])
    op.create_index("ix_wallet_txn_type", "wallet_transactions", ["transaction_type"])
    op.create_index("ix_wallet_txn_status", "wallet_transactions", ["transaction_status"])
    op.create_index("ix_wallet_txn_created_at", "wallet_transactions", ["created_at"])
    op.create_index(
        "ix_wallet_txn_school_status",
        "wallet_transactions",
        ["school_id", "transaction_status"],
    )
    op.create_index(
        "ix_wallet_txn_school_type",
        "wallet_transactions",
        ["school_id", "transaction_type"],
    )

    # ------------------------------------------------------------------
    # 6. business_inquiry_school (junction)
    # ------------------------------------------------------------------
    op.create_table(
        "business_inquiry_school",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "business_inquiry_id",
            sa.Integer(),
            sa.ForeignKey("business_inquiry.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "school_id",
            sa.String(),
            sa.ForeignKey("schools.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("is_seen", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("viewer_number", sa.Integer(), nullable=True),
        sa.Column("price_per_view", sa.Numeric(12, 2), nullable=True),
        sa.Column("amount_deducted", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
        sa.Column(
            "wallet_transaction_id",
            sa.Integer(),
            sa.ForeignKey("wallet_transactions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("remark", sa.Text(), nullable=True),
        sa.Column("remark_status", sa.String(50), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("business_inquiry_id", "school_id", name="uq_biz_inquiry_school"),
    )
    op.create_index("ix_bis_inquiry_id", "business_inquiry_school", ["business_inquiry_id"])
    op.create_index("ix_bis_school_id", "business_inquiry_school", ["school_id"])
    op.create_index(
        "ix_bis_school_seen",
        "business_inquiry_school",
        ["school_id", "is_seen"],
    )

    # ------------------------------------------------------------------
    # 7. Seed default recharge config + bonus slabs
    # ------------------------------------------------------------------
    op.execute(
        """
        INSERT INTO wallet_recharge_config (min_recharge_amount, max_recharge_amount)
        VALUES (500.00, 20000.00)
        """
    )
    op.execute(
        """
        INSERT INTO wallet_recharge_bonus (recharge_config_id, recharge_amount, bonus_percentage)
        SELECT id, 5000.00, 20.00 FROM wallet_recharge_config ORDER BY id LIMIT 1
        """
    )
    op.execute(
        """
        INSERT INTO wallet_recharge_bonus (recharge_config_id, recharge_amount, bonus_percentage)
        SELECT id, 10000.00, 15.00 FROM wallet_recharge_config ORDER BY id LIMIT 1
        """
    )
    op.execute(
        """
        INSERT INTO wallet_recharge_bonus (recharge_config_id, recharge_amount, bonus_percentage)
        SELECT id, 20000.00, 20.00 FROM wallet_recharge_config ORDER BY id LIMIT 1
        """
    )


def downgrade() -> None:
    op.drop_table("business_inquiry_school")
    op.drop_table("wallet_transactions")
    op.drop_table("school_wallet")
    op.drop_table("wallet_recharge_bonus")
    op.drop_table("wallet_recharge_config")
    op.drop_table("digital_profile_price_config")
