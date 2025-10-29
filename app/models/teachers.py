from sqlalchemy import Column, DateTime, Integer, String, ForeignKey, Time, Enum as SQLEnum,UniqueConstraint,Boolean
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import relationship
from app.db.session import Base
from enum import Enum
import uuid
from sqlalchemy.sql import func

# Define Python Enum for teacher_type
class TeacherTypeEnum(str, Enum):
    full_time = "full_time"
    part_time = "part_time"


class DayOfWeek(str, Enum):
    mon = "Mon"
    tue = "Tue"
    wed = "Wed"
    thu = "Thu"
    fri = "Fri"
    sat = "Sat"
    sun = "Sun"
class Teacher(Base):
    __tablename__ = "teachers"

    id = Column(String, primary_key=True)
    profile_image=Column(String,nullable=True)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    highest_qualification = Column(String, nullable=False)
    university = Column(String, nullable=False)
    phone = Column(String(10), nullable=False)
    email = Column(String, unique=True, nullable=False)           
    start_duty = Column(Time, nullable=False)
    end_duty = Column(Time, nullable=False)
    teacher_type = Column(SQLEnum(TeacherTypeEnum), nullable=False)
    present_in = Column(ARRAY(String), nullable=False)
    created_at = Column(DateTime, default=func.now())
    # Foreign keys
    school_id = Column(String, ForeignKey("schools.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    is_active = Column(Boolean, default=True)

    # Relationships
    school = relationship("School", back_populates="teachers")
    user = relationship("User", back_populates="teacher_profile")
    assigned_classes = relationship("Class", secondary="class_assigned_teachers", back_populates="assigned_teachers")
    attendances = relationship("Attendance", back_populates="teacher")
    timetable_periods = relationship("TimetablePeriod", back_populates="teacher")
    created_exams = relationship("Exam", back_populates="teacher")
    leave_requests = relationship("LeaveRequest", back_populates="teacher", cascade="all, delete")
    home_assignments = relationship("HomeAssignment", back_populates="teacher", cascade="all, delete")

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
            