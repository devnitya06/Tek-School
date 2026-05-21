from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Date, DateTime, Float, JSON, Table, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.session import Base
from enum import Enum as PyEnum
from sqlalchemy import Enum as SQLEnum

class AcademicResultType(str, PyEnum):
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    HALF_YEARLY = "half_yearly"
    ANNUAL = "annual"

academic_result_sections = Table(
    "academic_result_sections",
    Base.metadata,
    Column("definition_id", Integer, ForeignKey("academic_result_definitions.id", ondelete="CASCADE"), primary_key=True),
    Column("section_id", Integer, ForeignKey("sections.id", ondelete="CASCADE"), primary_key=True)
)

class AcademicResultDefinition(Base):
    __tablename__ = "academic_result_definitions"

    id = Column(Integer, primary_key=True, index=True)
    school_id = Column(String, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False)
    class_id = Column(Integer, ForeignKey("classes.id", ondelete="CASCADE"), nullable=False)
    
    result_type = Column(SQLEnum(AcademicResultType), nullable=False)
    exam_date = Column(Date, nullable=False)
    
    # JSON structure: [{"subject_id": 1, "full_marks": 100}, ...]
    subject_marks = Column(JSON, nullable=False)
    
    # JSON structure: {"excellent": 90, "very_good": 80, "good": 70, "average": 50, "poor": 33, "failed": 0}
    grade_percentages = Column(JSON, nullable=False)
    
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    school = relationship("School")
    class_obj = relationship("Class")
    sections = relationship("Section", secondary=academic_result_sections)
    student_results = relationship("AcademicStudentResult", back_populates="definition", cascade="all, delete-orphan")


class AcademicStudentResult(Base):
    __tablename__ = "academic_student_results"

    id = Column(Integer, primary_key=True, index=True)
    definition_id = Column(Integer, ForeignKey("academic_result_definitions.id", ondelete="CASCADE"), nullable=False)
    student_id = Column(Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    
    # JSON structure: [{"subject_id": 1, "secure_mark": 85}, ...]
    secure_marks = Column(JSON, nullable=False)
    
    total_secure_mark = Column(Float, nullable=False)
    grade = Column(String(50), nullable=False)
    last_result_day = Column(Date, nullable=True)
    
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    definition = relationship("AcademicResultDefinition", back_populates="student_results")
    student = relationship("Student")

    __table_args__ = (
        UniqueConstraint('definition_id', 'student_id', name='uq_academic_result_student_definition'),
    )
