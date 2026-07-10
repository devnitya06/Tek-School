from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    DateTime,
    Boolean,
    ForeignKey,
    UniqueConstraint,
)
from app.db.session import Base
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship


class UserSession(Base):
    __tablename__ = "user_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True)

    ip_address = Column(String, nullable=True)

    country = Column(String, nullable=True)
    region = Column(String, nullable=True)
    city = Column(String, nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    timezone = Column(String, nullable=True)

    isp = Column(String, nullable=True)
    organization = Column(String, nullable=True)

    browser = Column(String, nullable=True)
    browser_version = Column(String, nullable=True)

    os = Column(String, nullable=True)
    os_version = Column(String, nullable=True)

    device_type = Column(String, nullable=True)

    user_agent = Column(String, nullable=True)
    language = Column(String, nullable=True)

    login_at = Column(DateTime, nullable=True)
    last_active_at = Column(DateTime, nullable=True)

    is_active = Column(Boolean, default=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="session", uselist=False)

    __table_args__ = (
        UniqueConstraint("user_id", name="uq_user_sessions_user_id"),
    )
