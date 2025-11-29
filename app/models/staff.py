from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.session import Base

import uuid


class Staff(Base):
    __tablename__ = "staff"

    id = Column(String, primary_key=True)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)
    phone = Column(String(15), nullable=True)
    designation = Column(String, nullable=True)
    school_id = Column(String, ForeignKey("schools.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    school = relationship("School", back_populates="staff_members")
    user = relationship("User", back_populates="staff_profile")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.id:
            self.id = f"STF-{str(uuid.uuid4().int)[:6]}"

