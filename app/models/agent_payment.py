"""Agent Phase 3 — Payment Account, Withdrawal, and Audit Models

Tables:
    agent_payment_accounts    – one payment account per Agent (UNIQUE on agent_profile_id)
    agent_withdrawals         – withdrawal requests with status lifecycle
    agent_withdrawal_history  – immutable audit log of all status transitions

Design rules:
  - One payment account per agent (UNIQUE constraint).
  - PaymentMethod: UPI or BANK_TRANSFER only (never BOTH).
  - Bank account numbers stored encrypted; displayed masked (XXXXXX1234).
  - Withdrawal statuses: PENDING → APPROVED → PAID / PENDING → REJECTED / PENDING → CANCELLED.
  - On withdrawal creation: atomically reserve the amount (row-level lock on earnings).
  - On rejection/cancellation: release the reservation exactly once.
  - On mark-paid: consume reservation, record transaction details, upload payment proof to S3.
  - NUMERIC(12,2) for all monetary values — never float.
  - Payment proof stored as S3 URL; access controlled by route layer.
"""

from decimal import Decimal
from enum import Enum as PyEnum

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.session import Base


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class PaymentMethod(str, PyEnum):
    UPI = "UPI"
    BANK_TRANSFER = "BANK_TRANSFER"


class WithdrawalStatus(str, PyEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    PAID = "PAID"
    CANCELLED = "CANCELLED"


# ---------------------------------------------------------------------------
# Agent Payment Account
# ---------------------------------------------------------------------------

class AgentPaymentAccount(Base):
    """One payment account per Agent.

    Enforced at DB level by UNIQUE constraint on agent_profile_id.
    POST creates; PUT updates in-place.
    Bank account numbers are stored as plain text; masking is done in the
    serializer layer. Never log or expose full account numbers.
    """

    __tablename__ = "agent_payment_accounts"
    __table_args__ = (
        UniqueConstraint("agent_profile_id", name="uq_agent_payment_account_profile"),
    )

    id = Column(Integer, primary_key=True, index=True)

    agent_profile_id = Column(
        Integer,
        ForeignKey("agent_profiles.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # ── Common ────────────────────────────────────────────────────────────────
    account_holder_name = Column(String(255), nullable=False)
    payment_method = Column(String(32), nullable=False, index=True)   # PaymentMethod enum

    # ── UPI ───────────────────────────────────────────────────────────────────
    upi_id = Column(String(128), nullable=True)

    # ── Bank Transfer ─────────────────────────────────────────────────────────
    bank_account_number = Column(String(64), nullable=True)           # never exposed in full
    ifsc_code = Column(String(20), nullable=True)
    bank_name = Column(String(255), nullable=True)
    branch_name = Column(String(255), nullable=True)                  # optional

    # ── Timestamps ────────────────────────────────────────────────────────────
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=True,
    )
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    # ── Relationships ─────────────────────────────────────────────────────────
    agent_profile = relationship("AgentProfile", back_populates="payment_account")


# ---------------------------------------------------------------------------
# Agent Withdrawal Request
# ---------------------------------------------------------------------------

class AgentWithdrawal(Base):
    """A withdrawal request submitted by an Agent.

    Lifecycle: PENDING → APPROVED → PAID
               PENDING → REJECTED
               PENDING → CANCELLED
               APPROVED → REJECTED  (before payment only)

    Financial effects:
      - Created: reserve requested_amount from available earnings.
      - Approved: keep reservation.
      - Rejected/Cancelled: release reservation (exactly once, guarded by reservation_released).
      - Paid: consume reservation, record payment details, S3 proof URL.
    """

    __tablename__ = "agent_withdrawals"
    __table_args__ = (
        Index("ix_agent_withdrawals_profile_status", "agent_profile_id", "status"),
        Index("ix_agent_withdrawals_created", "created_at"),
        UniqueConstraint("transaction_id", name="uq_agent_withdrawal_transaction_id"),
    )

    id = Column(Integer, primary_key=True, index=True)

    agent_profile_id = Column(
        Integer,
        ForeignKey("agent_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── Request details ───────────────────────────────────────────────────────
    requested_amount = Column(Numeric(12, 2), nullable=False)
    status = Column(
        String(32),
        nullable=False,
        default=WithdrawalStatus.PENDING.value,
        index=True,
    )
    agent_remarks = Column(Text, nullable=True)

    # ── Payment account snapshot (taken at request time) ─────────────────────
    payment_method_snapshot = Column(String(32), nullable=True)       # PaymentMethod value
    upi_id_snapshot = Column(String(128), nullable=True)
    bank_account_masked_snapshot = Column(String(64), nullable=True)  # already masked e.g. XXXXXX1234
    ifsc_snapshot = Column(String(20), nullable=True)
    bank_name_snapshot = Column(String(255), nullable=True)
    account_holder_name_snapshot = Column(String(255), nullable=True)

    # ── Admin review ──────────────────────────────────────────────────────────
    admin_remarks = Column(Text, nullable=True)
    rejection_reason = Column(Text, nullable=True)
    reviewed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)

    # ── Payment details (set on mark-paid) ───────────────────────────────────
    transaction_id = Column(String(128), nullable=True, unique=True)  # UTR / bank ref — must be unique
    transaction_date = Column(Date, nullable=True)
    actual_paid_amount = Column(Numeric(12, 2), nullable=True)
    payment_proof_url = Column(Text, nullable=True)                   # S3 URL (private)
    payment_proof_s3_key = Column(Text, nullable=True)               # raw S3 key for cleanup
    paid_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    paid_at = Column(DateTime(timezone=True), nullable=True)

    # ── Reservation guard (prevents double-release) ───────────────────────────
    reservation_released = Column(Boolean, nullable=False, default=False)

    # ── Timestamps ────────────────────────────────────────────────────────────
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=True,
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    agent_profile = relationship("AgentProfile", back_populates="withdrawals")
    history = relationship(
        "AgentWithdrawalHistory",
        back_populates="withdrawal",
        cascade="all, delete-orphan",
        order_by="AgentWithdrawalHistory.created_at",
    )


# ---------------------------------------------------------------------------
# Withdrawal Audit History
# ---------------------------------------------------------------------------

class AgentWithdrawalHistory(Base):
    """Immutable audit log. One row per status transition or admin action.

    Agents must not modify these rows.
    Paid requests must never silently revert.
    """

    __tablename__ = "agent_withdrawal_history"
    __table_args__ = (
        Index("ix_withdrawal_history_withdrawal", "withdrawal_id"),
        Index("ix_withdrawal_history_created", "created_at"),
    )

    id = Column(Integer, primary_key=True, index=True)

    withdrawal_id = Column(
        Integer,
        ForeignKey("agent_withdrawals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    agent_profile_id = Column(Integer, nullable=False, index=True)

    from_status = Column(String(32), nullable=True)    # null for initial creation
    to_status = Column(String(32), nullable=False)
    action = Column(String(64), nullable=False)        # e.g. "CREATED", "APPROVED", "REJECTED", "PAID"
    actor_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    remarks = Column(Text, nullable=True)              # admin_remarks / rejection_reason
    transaction_id = Column(String(128), nullable=True)
    transaction_date = Column(Date, nullable=True)
    payment_proof_url = Column(Text, nullable=True)
    actual_paid_amount = Column(Numeric(12, 2), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    withdrawal = relationship("AgentWithdrawal", back_populates="history")
