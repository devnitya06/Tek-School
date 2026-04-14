from sqlalchemy import Column, DateTime, Integer, String, ForeignKey, Time, Enum as SQLEnum,UniqueConstraint,Boolean,Float, JSON
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


class PaymentMode(str, Enum):
    ONLINE = "Online"
    CASH_IN_HAND = "Cash in hand"
    ACCOUNT_TRANSFER = "Account transfer"
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
    designation = Column(String, nullable=True)
    immidiate_boss = Column(String, ForeignKey("staff.id"), nullable=True)
    super_boss = Column(String, ForeignKey("staff.id"), nullable=True)
    mark_in_time = Column(Time, nullable=True)
    mark_out_time = Column(Time, nullable=True)
    employee_grade = Column(String(100), nullable=True)
    is_active_hr_service = Column(Boolean, nullable=True, default=False)
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
    payment = relationship("TeacherStaffPayment", back_populates="teacher", uselist=False, cascade="all, delete-orphan")

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


class TeacherStaffPayment(Base):
    __tablename__ = "teacher_staff_payments"
    __table_args__ = (
        UniqueConstraint('teacher_id', name='unique_teacher_payment'),
        UniqueConstraint('staff_id', name='unique_staff_payment'),
    )

    id = Column(Integer, primary_key=True, index=True)
    teacher_id = Column(String, ForeignKey("teachers.id"), nullable=True, unique=True)
    staff_id = Column(String, ForeignKey("staff.id"), nullable=True, unique=True)
    
    # Monthly In-Hand Salary
    monthly_in_hand_salary = Column(Float, nullable=False, default=0.0)
    
    # Allowances
    allowance = Column(Float, nullable=False, default=0.0)
    bonus = Column(Float, nullable=False, default=0.0)
    other_allowances = Column(Float, nullable=False, default=0.0)
    
    # Additional Benefits
    incentive_plan = Column(Float, nullable=False, default=0.0)
    health_care_insurance = Column(Float, nullable=False, default=0.0)
    skill_development = Column(Float, nullable=False, default=0.0)
    
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    # Relationships
    teacher = relationship("Teacher", back_populates="payment")
    staff = relationship("Staff", back_populates="payment")
    transactions = relationship("TeacherStaffPaymentTransaction", back_populates="payment_structure", cascade="all, delete-orphan")


class TeacherStaffPaymentTransaction(Base):
    __tablename__ = "teacher_staff_payment_transactions"
    __table_args__ = (
        UniqueConstraint('teacher_id', 'payment_month', name='unique_teacher_payment_month'),
        UniqueConstraint('staff_id', 'payment_month', name='unique_staff_payment_month'),
    )

    id = Column(Integer, primary_key=True, index=True)
    payment_structure_id = Column(Integer, ForeignKey("teacher_staff_payments.id"), nullable=False)
    teacher_id = Column(String, ForeignKey("teachers.id"), nullable=True)
    staff_id = Column(String, ForeignKey("staff.id"), nullable=True)
    
    # Payment month in YYYY-MM format (e.g., "2025-01")
    payment_month = Column(String(7), nullable=False)
    
    # Total amount released
    total_amount = Column(Float, nullable=False)
    
    # Payment mode
    payment_mode = Column(SQLEnum(PaymentMode), nullable=False)
    
    # Amount release date
    release_date = Column(DateTime, nullable=False)
    
    # Created by (school user who made the payment)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    created_at = Column(DateTime, default=func.now())
    
    # Relationships
    payment_structure = relationship("TeacherStaffPayment", back_populates="transactions")
    teacher = relationship("Teacher")
    staff = relationship("Staff")
    created_by_user = relationship("User")
            