"""Agent Phase 2 — Payment Configuration and Earnings Models

Tables:
    agent_payment_configs  – one current configuration per Agent (UNIQUE on agent_profile_id)
    agent_earnings         – immutable earning ledger; applied_rate is a snapshot

Design rules:
  - POST creates the initial config; PUT updates it in-place (no versioning).
  - agent_earnings rows are append-only; approved amounts are never recalculated.
  - is_bonus_withdrawn is only flipped by the withdrawal workflow, never by config endpoints.
  - NUMERIC(12,2) for all monetary amounts — never float.
"""

from decimal import Decimal
from enum import Enum as PyEnum

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
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

class AgentEarningType(str, PyEnum):
    INSTITUTION_DIGITAL_PROFILE = "INSTITUTION_DIGITAL_PROFILE"
    DAILY_STIPEND = "DAILY_STIPEND"
    MONTHLY_STIPEND = "MONTHLY_STIPEND"
    PHYSICAL_VERIFICATION = "PHYSICAL_VERIFICATION"
    ONLINE_DEMONSTRATION = "ONLINE_DEMONSTRATION"
    OFFLINE_DEMONSTRATION = "OFFLINE_DEMONSTRATION"
    OTHER_ACTIVITY = "OTHER_ACTIVITY"
    INITIAL_BONUS = "INITIAL_BONUS"


class AgentEarningStatus(str, PyEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    PAID = "PAID"


# ---------------------------------------------------------------------------
# Agent Payment Configuration
# ---------------------------------------------------------------------------

class AgentPaymentConfig(Base):
    """One current payment configuration per Agent.

    Enforced at DB level by UNIQUE constraint on agent_profile_id.
    POST creates; PUT updates in-place. No history table, no version numbers.
    """

    __tablename__ = "agent_payment_configs"
    __table_args__ = (
        UniqueConstraint("agent_profile_id", name="uq_agent_payment_config_profile"),
    )

    id = Column(Integer, primary_key=True, index=True)

    # FK to agent_profiles (one-to-one)
    agent_profile_id = Column(
        Integer,
        ForeignKey("agent_profiles.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # ── Institution Digital Profile ──────────────────────────────────────────
    idp_is_enabled = Column(Boolean, nullable=False, default=False)
    idp_rate = Column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))

    # Legacy daily settings remain stored but are not used for monthly stipends.
    stipend_monthly_is_enabled = Column(Boolean, nullable=False, default=False)
    stipend_is_enabled = Column(Boolean, nullable=False, default=False)
    stipend_daily_rate = Column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    stipend_monthly_rate = Column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    stipend_effective_from = Column(Date, nullable=True)

    # ── Physical Verification ────────────────────────────────────────────────
    pv_is_enabled = Column(Boolean, nullable=False, default=False)
    pv_rate = Column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))

    # ── Online Demonstration ─────────────────────────────────────────────────
    od_is_enabled = Column(Boolean, nullable=False, default=False)
    od_rate = Column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))

    # ── Offline Demonstration ────────────────────────────────────────────────
    offd_is_enabled = Column(Boolean, nullable=False, default=False)
    offd_rate = Column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))

    # ── Other Activities ─────────────────────────────────────────────────────
    oa_is_enabled = Column(Boolean, nullable=False, default=False)
    oa_rate = Column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))

    # ── Initial Bonus ────────────────────────────────────────────────────────
    initial_bonus = Column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    # Only flipped by withdrawal workflow — never by config POST/PUT
    is_bonus_withdrawn = Column(Boolean, nullable=False, default=False)

    # ── Timestamps (server-generated) ───────────────────────────────────────
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=True,
    )
    effective_from = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Audit
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Relationships
    agent_profile = relationship("AgentProfile", back_populates="payment_config")


class AgentStipendRate(Base):
    """Monthly stipend rate snapshots effective from a calendar month."""

    __tablename__ = "agent_stipend_rates"
    __table_args__ = (
        UniqueConstraint(
            "agent_profile_id",
            "effective_from",
            name="uq_agent_stipend_rate_effective_from",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    agent_profile_id = Column(
        Integer,
        ForeignKey("agent_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    effective_from = Column(Date, nullable=False, index=True)
    is_enabled = Column(Boolean, nullable=False)
    monthly_rate = Column(Numeric(12, 2), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# ---------------------------------------------------------------------------
# Agent Earnings Ledger
# ---------------------------------------------------------------------------

class AgentEarning(Base):
    """Immutable earning records for Agents.

    Rules:
    - One row per payable event.
    - applied_rate is a snapshot of the config rate at the time of earning.
    - Approved amounts are NEVER recalculated after a config change.
    - Prevent duplicate earnings via UNIQUE on (agent_profile_id, earning_type, reference_id).
    """

    __tablename__ = "agent_earnings"
    __table_args__ = (
        UniqueConstraint(
            "agent_profile_id",
            "earning_type",
            "reference_id",
            name="uq_agent_earning_type_ref",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)

    agent_profile_id = Column(
        Integer,
        ForeignKey("agent_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    earning_type = Column(String(64), nullable=False, index=True)
    status = Column(
        String(32),
        nullable=False,
        default=AgentEarningStatus.PENDING.value,
        index=True,
    )

    # Reference to the triggering record
    reference_type = Column(String(64), nullable=True)
    reference_id = Column(String(128), nullable=True, index=True)

    # Financial snapshot — immutable once APPROVED
    applied_rate = Column(Numeric(12, 2), nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)

    earning_date = Column(Date, nullable=True)
    description = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=True,
    )
    approved_at = Column(DateTime(timezone=True), nullable=True)

    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    approved_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Relationships
    agent_profile = relationship("AgentProfile", back_populates="earnings")
