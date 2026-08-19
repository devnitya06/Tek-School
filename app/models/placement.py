from enum import Enum

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.session import Base


class PlacementStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class PlacementPartner(Base):
    __tablename__ = "placement_partners"

    id = Column(Integer, primary_key=True, index=True)
    school_id = Column(String, ForeignKey("schools.id"), nullable=False, index=True)
    company_logo = Column(String, nullable=True)
    company_name = Column(String(255), nullable=False, index=True)
    website = Column(String(500), nullable=False)
    placement_year = Column(Integer, nullable=False, index=True)
    campus_month = Column(Integer, nullable=True)
    about_company = Column(Text, nullable=True)
    hiring_criteria = Column(Text, nullable=True)
    what_they_give = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default=PlacementStatus.ACTIVE.value)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

    achievers = relationship("PlacementAchiever", back_populates="company", cascade="all, delete-orphan")


class PlacementAchiever(Base):
    __tablename__ = "placement_achievers"

    id = Column(Integer, primary_key=True, index=True)
    school_id = Column(String, ForeignKey("schools.id"), nullable=False, index=True)
    student_logo = Column(String, nullable=True)
    student_name = Column(String(255), nullable=False, index=True)
    gender = Column(String(50), nullable=False)
    class_name = Column(String(100), nullable=False, index=True)
    section_roll_no = Column(String(100), nullable=True)
    company_id = Column(Integer, ForeignKey("placement_partners.id"), nullable=False, index=True)
    designation = Column(String(255), nullable=False)
    salary_package_lpa = Column(String(50), nullable=False)
    placement_year = Column(Integer, nullable=False, index=True)
    about_student = Column(Text, nullable=True)
    file = Column(String, nullable=True)
    status = Column(String(20), nullable=False, default=PlacementStatus.ACTIVE.value)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

    company = relationship("PlacementPartner", back_populates="achievers")