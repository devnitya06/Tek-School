from sqlalchemy import Column, Integer, String, ForeignKey, Date, DateTime, JSON, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from enum import Enum as PyEnum
from sqlalchemy import Enum as SQLEnum

from app.db.session import Base

class ProgressReportStatus(str, PyEnum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"

class ProgressReport(Base):
    __tablename__ = "progress_reports"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    school_id = Column(String, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False)
    teacher_id = Column(String, ForeignKey("teachers.id", ondelete="SET NULL"), nullable=True)
    
    report_title = Column(String(255), nullable=False)
    duration_from = Column(Date, nullable=False)
    duration_to = Column(Date, nullable=False)
    
    status = Column(SQLEnum(ProgressReportStatus, name="progress_report_status"), default=ProgressReportStatus.DRAFT, nullable=False)

    # JSON structure: [{"subject_name": "Math", "status": "good"}]
    subjects = Column(JSON, nullable=True)
    
    # JSON structure: [{"area": "Discipline", "status": "better"}]
    assessment_areas = Column(JSON, nullable=True)
    
    # JSON structure: ["Focus more in class", "Complete homework on time"]
    key_needs_improvement = Column(JSON, nullable=True)

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    # Relationships
    student = relationship("Student", backref="progress_reports")
    school = relationship("School")
    teacher = relationship("Teacher")
