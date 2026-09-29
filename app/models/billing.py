"""
Billing, Wallet, and Digital Profile Price Configuration models.

Tables:
    digital_profile_price_config  – per education-associate pricing tiers
    wallet_recharge_config         – platform-level recharge limits
    wallet_recharge_bonus          – bonus slabs for recharge amounts
    school_wallet                  – one wallet per school (UNIQUE school_id)
    wallet_transactions            – full ledger / audit trail
    business_inquiry_school        – per-school seen-state + billing junction
"""

from decimal import Decimal
from enum import Enum

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY as PG_ARRAY
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.session import Base


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class EducationAssociate(str, Enum):
    SCHOOL_EDUCATIONS = "SCHOOL_EDUCATIONS"
    HIGHER_EDUCATION = "HIGHER_EDUCATION"
    PROFESSIONAL_EDUCATION = "PROFESSIONAL_EDUCATION"
    MEDICAL_PHARMA = "MEDICAL_PHARMA"
    UNIVERSITY = "UNIVERSITY"
    TRAINING_COACHING = "TRAINING_COACHING"
    CREATIVE_TRAINING = "CREATIVE_TRAINING"


class WalletTransactionType(str, Enum):
    RECHARGE = "RECHARGE"
    INQUIRY_DEDUCTION = "INQUIRY_DEDUCTION"
    BONUS = "BONUS"
    REFUND = "REFUND"
    ADJUSTMENT = "ADJUSTMENT"


class WalletTransactionStatus(str, Enum):
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    REFUNDED = "REFUNDED"


# ---------------------------------------------------------------------------
# Digital Profile Price Configuration
# ---------------------------------------------------------------------------

class DigitalProfilePriceConfig(Base):
    """
    Pricing tiers for Business Inquiry view deductions.
    One row per education_associate (though multiple are allowed for historical tracking).
    Admin/SuperAdmin manage this; Schools can only read it.
    """
    __tablename__ = "digital_profile_price_config"

    id = Column(Integer, primary_key=True, index=True)
    education_associate = Column(String(64), nullable=False, index=True)
    # education_offered stores values like ["CBSE", "ICSE", "JEE"] — TEXT[]
    education_offered = Column(PG_ARRAY(String), nullable=False)

    # Tiered pricing (NUMERIC for precision — never float)
    first_two_viewer_price = Column(Numeric(12, 2), nullable=False, default=Decimal("50.00"))
    next_five_viewer_price = Column(Numeric(12, 2), nullable=False, default=Decimal("20.00"))
    all_other_viewer_price = Column(Numeric(12, 2), nullable=False, default=Decimal("10.00"))

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=True)


# ---------------------------------------------------------------------------
# Wallet Recharge Configuration
# ---------------------------------------------------------------------------

class WalletRechargeConfig(Base):
    """
    Platform-level recharge limits. Only one row should exist at a time
    (first row is the active config; admin updates it in-place).
    """
    __tablename__ = "wallet_recharge_config"

    id = Column(Integer, primary_key=True, index=True)
    min_recharge_amount = Column(Numeric(12, 2), nullable=False, default=Decimal("500.00"))
    max_recharge_amount = Column(Numeric(12, 2), nullable=False, default=Decimal("20000.00"))

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    bonus_configs = relationship(
        "WalletRechargeBonus",
        back_populates="recharge_config",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class WalletRechargeBonus(Base):
    """
    Bonus percentage slabs tied to a recharge config.
    E.g. recharge_amount=5000, bonus_percentage=20 → 20% bonus on ₹5000 recharge.
    """
    __tablename__ = "wallet_recharge_bonus"

    id = Column(Integer, primary_key=True, index=True)
    recharge_config_id = Column(
        Integer,
        ForeignKey("wallet_recharge_config.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    recharge_amount = Column(Numeric(12, 2), nullable=False, index=True)
    bonus_percentage = Column(Numeric(5, 2), nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    recharge_config = relationship("WalletRechargeConfig", back_populates="bonus_configs")


# ---------------------------------------------------------------------------
# School Wallet
# ---------------------------------------------------------------------------

class SchoolWallet(Base):
    """
    One wallet per school. Balance must never go negative.
    Direct balance updates are not allowed from the frontend — only via
    wallet_transactions with confirmed payment.
    """
    __tablename__ = "school_wallet"

    id = Column(Integer, primary_key=True, index=True)
    school_id = Column(
        String,
        ForeignKey("schools.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    balance = Column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    currency = Column(String(8), nullable=False, default="INR")

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    transactions = relationship(
        "WalletTransaction",
        back_populates="wallet",
        foreign_keys="WalletTransaction.school_id",
        primaryjoin="SchoolWallet.school_id == WalletTransaction.school_id",
        lazy="dynamic",
    )


# ---------------------------------------------------------------------------
# Wallet Transactions (Ledger)
# ---------------------------------------------------------------------------

class WalletTransaction(Base):
    """
    Complete audit ledger for all wallet movements.

    Razorpay-ready: payment_provider / payment_order_id / payment_payment_id /
    payment_signature are all nullable now. When Razorpay is integrated:
      1. Create PENDING transaction
      2. Call Razorpay to create an order → save payment_provider + payment_order_id
      3. On webhook confirmation → set SUCCESS, credit wallet.

    State machine: PENDING → SUCCESS | FAILED | CANCELLED
    Once SUCCESS, the row must not be transitioned again (double-credit guard).
    """
    __tablename__ = "wallet_transactions"

    id = Column(Integer, primary_key=True, index=True)
    school_id = Column(
        String,
        ForeignKey("schools.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    transaction_type = Column(String(32), nullable=False, index=True)   # WalletTransactionType
    transaction_status = Column(String(32), nullable=False, index=True)  # WalletTransactionStatus

    # Amounts — all NUMERIC(12,2) for precision
    amount = Column(Numeric(12, 2), nullable=False)           # positive = credit, negative = debit
    bonus_amount = Column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    total_credit = Column(Numeric(12, 2), nullable=False)     # = amount + bonus_amount for RECHARGE

    balance_before = Column(Numeric(12, 2), nullable=True)    # filled on SUCCESS
    balance_after = Column(Numeric(12, 2), nullable=True)     # filled on SUCCESS

    currency = Column(String(8), nullable=False, default="INR")

    # Reference — what triggered this transaction
    reference_type = Column(String(64), nullable=True)        # e.g. "BUSINESS_INQUIRY"
    reference_id = Column(String(128), nullable=True)         # e.g. "245"

    # Payment-provider fields — all nullable; filled by Razorpay integration later
    payment_provider = Column(String(32), nullable=True)      # e.g. "RAZORPAY"
    payment_order_id = Column(String(128), nullable=True)
    payment_payment_id = Column(String(128), nullable=True)
    payment_signature = Column(String(256), nullable=True)

    description = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    wallet = relationship(
        "SchoolWallet",
        foreign_keys=[school_id],
        primaryjoin="WalletTransaction.school_id == SchoolWallet.school_id",
        back_populates="transactions",
    )

    __table_args__ = (
        Index("ix_wallet_txn_school_status", "school_id", "transaction_status"),
        Index("ix_wallet_txn_school_type", "school_id", "transaction_type"),
        Index("ix_wallet_txn_created", "created_at"),
    )


# ---------------------------------------------------------------------------
# Business Inquiry — Per-School Junction Table
# ---------------------------------------------------------------------------

class BusinessInquirySchool(Base):
    """
    Junction table: one row per (business_inquiry_id, school_id) pair.

    Represents the per-school view/billing state for a business inquiry.
    The parent BusinessInquiry.school_ids array still governs which schools
    are targeted — this table is the billing/state layer on top.

    Rules:
    - Created automatically when POST /inquiry creates a BusinessInquiry.
    - is_seen=False initially.
    - On first GET /school/business-inquiry/{id}:
        → wallet deducted atomically
        → is_seen=True, viewer_number, price_per_view, amount_deducted saved.
    - Subsequent views: return stored values, no re-deduction.
    - remark / remark_status are per-school (moved here from global BusinessInquiry).
    """
    __tablename__ = "business_inquiry_school"

    id = Column(Integer, primary_key=True, index=True)
    business_inquiry_id = Column(
        Integer,
        ForeignKey("business_inquiry.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    school_id = Column(
        String,
        ForeignKey("schools.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Seen / billing state
    is_seen = Column(Boolean, nullable=False, default=False)
    seen_at = Column(DateTime(timezone=True), nullable=True)

    # Historical pricing — written once on first view, never updated
    viewer_number = Column(Integer, nullable=True)     # 1-based counter per school
    price_per_view = Column(Numeric(12, 2), nullable=True)  # snapshot of price at view time
    amount_deducted = Column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))

    # FK to the wallet transaction that deducted the fee
    wallet_transaction_id = Column(
        Integer,
        ForeignKey("wallet_transactions.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Per-school remark (moved from global BusinessInquiry)
    remark = Column(Text, nullable=True)
    remark_status = Column(String(50), nullable=True)  # relevant|not_relevant|important|call_to_action

    # Per-school employee assignment — written via PATCH /business-inquiry/{id}/remark
    assigned_to_name = Column(String(255), nullable=True)
    assigned_to_designation = Column(String(100), nullable=True)
    assigned_to_phone = Column(String(20), nullable=True)
    assigned_to_email = Column(String(255), nullable=True)
    assigned_at = Column(DateTime(timezone=True), nullable=True)  # server-set; never accepted from client

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("business_inquiry_id", "school_id", name="uq_biz_inquiry_school"),
        Index("ix_bis_school_seen", "school_id", "is_seen"),
        Index("ix_bis_inquiry_id", "business_inquiry_id"),
        Index("ix_bis_school_id", "school_id"),
    )

    wallet_transaction = relationship("WalletTransaction", foreign_keys=[wallet_transaction_id])
