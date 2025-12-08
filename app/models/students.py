from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Date,DateTime,Enum
from sqlalchemy.orm import relationship
from app.db.session import Base
from sqlalchemy.sql import func
from enum import Enum as PyEnum

class StudentStatus(PyEnum):
    TRIAL = "TRIAL"
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
class Student(Base):
    __tablename__ = "students"

    id = Column(Integer, primary_key=True, index=True)
    profile_image = Column(String, nullable=True)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    gender = Column(String(10), nullable=False) #1
    dob = Column(Date, nullable=False)   #2

    class_id = Column(Integer, ForeignKey("classes.id"))  #3
    section_id = Column(Integer, ForeignKey("sections.id"))  #4
    roll_no = Column(Integer, nullable=False)       #5
    is_transport = Column(Boolean, default=True)

    driver_id = Column(Integer, ForeignKey("transports.id"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    school_id = Column(String, ForeignKey("schools.id"), nullable=True)
    status = Column(Enum(StudentStatus), default=StudentStatus.TRIAL.value, nullable=False)
    status_expiry_date = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=func.now())
    pickup_point = Column(String(150), nullable=True)
    pickup_time = Column(String(50), nullable=True)
    drop_point = Column(String(150), nullable=True)
    drop_time = Column(String(50), nullable=True)

    # Relationships
    classes = relationship("Class", back_populates="students")
    section = relationship("Section",back_populates="students")
    driver = relationship("Transport", back_populates="students")
    user = relationship("User", back_populates="student_profile")
    school= relationship("School", back_populates="students")
    parent = relationship("Parent", back_populates="student", uselist=False)
    present_address = relationship("PresentAddress", back_populates="student", uselist=False)
    permanent_address = relationship("PermanentAddress", back_populates="student", uselist=False)
    attendances = relationship("Attendance", back_populates="student")
    exam_data = relationship("StudentExamData", back_populates="student")
    chapter_progress = relationship("StudentChapterProgress", back_populates="student")
    leave_requests = relationship("LeaveRequest", back_populates="student", cascade="all, delete")
    student_assignments = relationship("AssignmentStudent",back_populates="student",cascade="all, delete-orphan")
    # Each student’s task completion statuses
    student_task_statuses = relationship("StudentTaskStatus",back_populates="student",cascade="all, delete-orphan")



class Parent(Base):
    __tablename__ = "parents"

    id = Column(Integer, primary_key=True, index=True)
    parent_name = Column(String(100), nullable=False)
    relation = Column(String(50), nullable=False)
    phone = Column(String(15), nullable=False)
    email = Column(String(100), nullable=False, unique=True)
    occupation = Column(String(100), nullable=True)
    organization = Column(String(150), nullable=True)

    student_id = Column(Integer, ForeignKey("students.id"), nullable=False, unique=True)

    student = relationship("Student", back_populates="parent")

class AddressMixin:
    enter_pin = Column(String(10), nullable=False)
    division = Column(String(100), nullable=True)
    district = Column(String(100), nullable=False)
    state = Column(String(100), nullable=False)
    country = Column(String(100), nullable=False)
    building = Column(String(150), nullable=True)
    house_no = Column(String(50), nullable=True)
    floor_name = Column(String(50), nullable=True)
    
class PresentAddress(Base, AddressMixin):
    __tablename__ = "present_addresses"

    id = Column(Integer, primary_key=True, index=True)
    is_this_permanent_as_well = Column(Boolean, default=False)

    student_id = Column(Integer, ForeignKey("students.id"), nullable=False, unique=True)
    student = relationship("Student", back_populates="present_address")

class PermanentAddress(Base, AddressMixin):
    __tablename__ = "permanent_addresses"

    id = Column(Integer, primary_key=True, index=True)

    student_id = Column(Integer, ForeignKey("students.id"), nullable=False, unique=True)
    student = relationship("Student", back_populates="permanent_address")



class SelfSignedStudent(Base):
    __tablename__ = "self_signed_students"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    profile_image = Column(String, nullable=True)
    phone = Column(String(20), nullable=True)
    email = Column(String(255), nullable=False, unique=True)

    select_board = Column(String(50), nullable=True)
    select_medium = Column(String(50), nullable=True)
    select_class = Column(String(50), nullable=True)

    school_name = Column(String(255), nullable=True)
    school_location = Column(String(255), nullable=True)

    pin = Column(Integer, nullable=True)
    division = Column(String(100), nullable=True)
    district = Column(String(100), nullable=True)
    state = Column(String(100), nullable=True)

    plot = Column(String(255), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", back_populates="self_signed_student_profile")
    admin_exam_data = relationship("StudentAdminExamData", back_populates="student")