from datetime import datetime
from enum import Enum

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, ARRAY
from sqlalchemy.sql import func

from app.db.session import Base


class NewsStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class NewsSubmission(Base):
    __tablename__ = "news_submissions"

    id = Column(Integer, primary_key=True, index=True)
    school_id = Column(String, nullable=False, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    images = Column(ARRAY(String), nullable=True)
    user_type = Column(String(50), nullable=True, default="visitor")
    full_name = Column(String(255), nullable=True)
    phone_no = Column(String(50), nullable=True)
    email_id = Column(String(255), nullable=True)
    location = Column(String(255), nullable=True)
    status = Column(String(50), nullable=False, default=NewsStatus.PENDING.value)
    remark = Column(Text, nullable=True)
    is_verified = Column(Boolean, nullable=False, default=False)
    otp_code = Column(String(10), nullable=True)
    otp_expires_at = Column(DateTime, nullable=True)
    verified_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if self.status is None:
            self.status = NewsStatus.PENDING.value
