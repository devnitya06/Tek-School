"""Agent Profile Model - Phase 1

Two-step creation flow:
  Step 1 (Admin creates): first_name, last_name, phone, email, stipend_type
  Step 2 (Admin fills full profile): all remaining profile fields

Agent accounts live in the existing `users` table with role = 'agent'.
Six activity permissions (ADMIN/SUPERADMIN only):
  can_onboard_school, can_enroll_student, can_collect_fees,
  can_do_followup, can_verify_documents, can_coordinate_events
"""

from enum import Enum as PyEnum
import uuid

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Enum as SQLEnum,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.session import Base


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class StipendType(str, PyEnum):
    WITH_STIPEND = "WITH_STIPEND"
    WITHOUT_STIPEND = "WITHOUT_STIPEND"


class AgentGender(str, PyEnum):
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

class AgentProfile(Base):
    """One-to-one extension of `users` for Agent accounts."""

    __tablename__ = "agent_profiles"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_agent_profiles_user_id"),
        UniqueConstraint("agent_id", name="uq_agent_profiles_agent_id"),
    )

    # Primary key
    id = Column(Integer, primary_key=True, index=True)

    # FK to users table (one-to-one)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # System-generated unique agent identifier e.g. "AGT-827364"
    agent_id = Column(String(20), nullable=False, unique=True, index=True)

    # ── Step-1 fields (set at creation, editable by admin) ──────────────────
    first_name = Column(String(100), nullable=False)
    last_name  = Column(String(100), nullable=False)
    # phone / email mirrored from users table for profile display
    phone      = Column(String(20), nullable=True)
    email      = Column(String(255), nullable=True)

    stipend_type = Column(
        SQLEnum(StipendType, name="stipend_type_enum"),
        nullable=False,
        default=StipendType.WITHOUT_STIPEND,
    )

    # ── Step-2 profile fields (filled via profile-update endpoint) ───────────
    gender      = Column(
        SQLEnum(
            AgentGender,
            name="agent_gender_enum",
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=True,
    )
    dob         = Column(Date, nullable=True)
    qualification  = Column(String(255), nullable=True)
    university     = Column(String(255), nullable=True)   # University / Institution
    designation    = Column(String(255), nullable=True)   # Agent Designation
    experience     = Column(Text, nullable=True)

    # Address / Location (PIN-code based; frontend auto-fills division/district/state)
    pin_code  = Column(String(10),  nullable=True)
    division  = Column(String(100), nullable=True)
    district  = Column(String(100), nullable=True)
    state     = Column(String(100), nullable=True)
    landmark  = Column(String(255), nullable=True)

    # ── Six activity permission flags (ADMIN/SUPERADMIN only) ─────────────────
    can_onboard_school    = Column(Boolean, nullable=False, default=False)
    can_enroll_student    = Column(Boolean, nullable=False, default=False)
    can_collect_fees      = Column(Boolean, nullable=False, default=False)
    can_do_followup       = Column(Boolean, nullable=False, default=False)
    can_verify_documents  = Column(Boolean, nullable=False, default=False)
    can_coordinate_events = Column(Boolean, nullable=False, default=False)

    # Profile completion flag (True once step-2 is filled)
    profile_completed_step2 = Column(Boolean, nullable=False, default=False)

    # ── Phase 2: Bonus preference (set by agent at consent time) ─────────────
    wants_initial_bonus = Column(Boolean, nullable=False, default=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    # Relationships
    user = relationship("User", back_populates="agent_profile")
    payment_config = relationship(
        "AgentPaymentConfig",
        back_populates="agent_profile",
        uselist=False,
        cascade="all, delete-orphan",
    )
    earnings = relationship(
        "AgentEarning",
        back_populates="agent_profile",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )
    payment_account = relationship(
        "AgentPaymentAccount",
        back_populates="agent_profile",
        uselist=False,
        cascade="all, delete-orphan",
    )
    withdrawals = relationship(
        "AgentWithdrawal",
        back_populates="agent_profile",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )

    # Auto-generate agent_id on first insert
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.agent_id:
            import uuid as _uuid
            self.agent_id = f"AGT-{str(_uuid.uuid4().int)[:6]}"
