"""
Demo Management System — SQLAlchemy Models

Tables:
  demo_configurations   — admin-managed demo schedule configurations
  demo_requests         — public user demo booking requests
  demo_request_images   — images attached to a demo request (admin-uploaded)
  demo_otps             — anonymous OTP records (no user_id, standalone)
  demo_access_attempts  — brute-force tracking for the public access endpoint
"""
from datetime import datetime, timezone, timedelta
from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    DateTime,
    Date,
    Time,
    Text,
    BigInteger,
    ForeignKey,
    Index,
    ARRAY,
    JSON,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.session import Base


class DemoConfiguration(Base):
    __tablename__ = "demo_configurations"

    id = Column(Integer, primary_key=True, index=True)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    user_limit = Column(Integer, nullable=False)
    # Stored as ARRAY of strings e.g. ["MONDAY","WEDNESDAY","FRIDAY"]
    demo_days = Column(ARRAY(String), nullable=False)
    presented_by = Column(String(255), nullable=False)
    demonstration_link = Column(String(1024), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationship
    demo_requests = relationship(
        "DemoRequest", back_populates="configuration", lazy="dynamic"
    )


class DemoRequest(Base):
    __tablename__ = "demo_requests"

    id = Column(Integer, primary_key=True, index=True)
    request_code = Column(String(20), unique=True, nullable=False, index=True)
    email = Column(String(255), nullable=False, index=True)
    user_category = Column(String(50), nullable=False)
    institution_name = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    designation = Column(String(255), nullable=True)
    phone = Column(String(20), nullable=False, index=True)
    institution_address = Column(Text, nullable=True)
    # Stored as JSON array of strings
    area_of_interest = Column(JSON, nullable=True)
    # Preferred language for the demo presentation
    preferred_language = Column(String(20), nullable=True)

    # Slot fields — derived from configuration at booking/reschedule time
    config_id = Column(
        Integer, ForeignKey("demo_configurations.id"), nullable=False, index=True
    )
    demo_date = Column(Date, nullable=False, index=True)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    presented_by = Column(String(255), nullable=False)
    demonstration_link = Column(String(1024), nullable=False)

    status = Column(String(20), nullable=False, default="PENDING", index=True)
    access_code = Column(String(6), nullable=True)
    feedback_message = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    configuration = relationship("DemoConfiguration", back_populates="demo_requests")
    images = relationship(
        "DemoRequestImage",
        back_populates="demo_request",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        # Composite index for slot capacity queries
        Index(
            "ix_demo_requests_slot",
            "config_id",
            "demo_date",
            "start_time",
            "status",
        ),
    )


class DemoRequestImage(Base):
    __tablename__ = "demo_request_images"

    id = Column(Integer, primary_key=True, index=True)
    demo_request_id = Column(
        Integer,
        ForeignKey("demo_requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    image_url = Column(String(1024), nullable=False)
    file_name = Column(String(255), nullable=True)
    file_size = Column(BigInteger, nullable=True)  # bytes
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    demo_request = relationship("DemoRequest", back_populates="images")


class DemoOtp(Base):
    """
    Standalone OTP records for anonymous demo users.
    Does NOT reference the users table (public, no account needed).
    """

    __tablename__ = "demo_otps"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), nullable=False, index=True)
    otp_code = Column(String(6), nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)
    # Tracks incorrect verify attempts to enforce DEMO_OTP_ATTEMPTS_EXCEEDED
    attempt_count = Column(Integer, default=0, nullable=False)
    # Tracks how many times OTP was re-sent within the window
    resend_count = Column(Integer, default=0, nullable=False)
    # Temporary booking payload waiting for OTP verification.
    request_payload = Column(JSON, nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    @property
    def is_expired(self) -> bool:
        now = datetime.now(timezone.utc)
        exp = self.expires_at
        if exp.tzinfo is None:
            from datetime import timezone as tz
            exp = exp.replace(tzinfo=tz.utc)
        return now > exp


class DemoAccessAttempt(Base):
    """
    Tracks failed access-code attempts per email within a rolling time window.
    Used to enforce DEMO_ACCESS_RATE_LIMITED (brute-force protection).
    """

    __tablename__ = "demo_access_attempts"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), nullable=False, index=True)
    attempt_count = Column(Integer, default=0, nullable=False)
    # Start of the current rate-limit window
    window_start = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
