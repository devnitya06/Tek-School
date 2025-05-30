from sqlalchemy import Column, DateTime, Integer, String, ForeignKey, Time, Enum as SQLEnum,UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import relationship
from app.db.session import Base
from enum import Enum
import uuid
from datetime import timedelta,datetime,timezone

# Define Python Enum for teacher_type
class TeacherTypeEnum(str, Enum):
    full_time = "full_time"
    part_time = "part_time"

class Teacher(Base):
    __tablename__ = "teachers"

    id = Column(String, primary_key=True)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    highest_qualification = Column(String, nullable=False)
    university = Column(String, nullable=False)
    phone = Column(String(10), nullable=False)
    email = Column(String, unique=True, nullable=False)
    teacher_in_classes = Column(ARRAY(String), nullable=False)  # ["5th", "7th"]
    subjects = Column(ARRAY(String), nullable=False)            # ["Math", "Sci"]
    start_duty = Column(Time, nullable=False)                   # 10:30 AM
    end_duty = Column(Time, nullable=False)                    # 5:00 PM
    teacher_type = Column(SQLEnum(TeacherTypeEnum), nullable=False)
    present_in = Column(ARRAY(String), nullable=False)          # ["Mon", "Wed", "Fri"]
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    # Foreign keys
    school_id = Column(String, ForeignKey("schools.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # Nullable until account is created

    # Relationships
    school = relationship("School", back_populates="teachers")
    user = relationship("User", back_populates="teacher_profile")
    assigned_classes = relationship("Class", secondary="class_assigned_teachers", back_populates="assigned_teachers")
    attendances = relationship("Attendance", back_populates="teacher")
    timetable_periods = relationship("TimetablePeriod", back_populates="teacher")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.id:
            self.id = f"TCH-{str(uuid.uuid4().int)[:6]}"
            
            
class TeacherClassSectionSubject(Base):
    __tablename__ = "teacher_class_section_subjects"

    id = Column(Integer, primary_key=True, index=True)
    teacher_id = Column(String, ForeignKey("teachers.id"), nullable=False)
    class_id = Column(Integer, ForeignKey("classes.id"), nullable=False)
    section_id = Column(Integer, ForeignKey("sections.id"), nullable=False)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False)
    school_id = Column(String, ForeignKey("schools.id"), nullable=False)

    __table_args__ = (
        UniqueConstraint("teacher_id", "class_id", "section_id", "subject_id", name="unique_teacher_assignment"),
    )

    teacher = relationship("Teacher", backref="assignments")
    school = relationship("School", backref="teacher_assignments")
    section = relationship("Section")
    subject = relationship("Subject")
    class_ = relationship("Class")
            