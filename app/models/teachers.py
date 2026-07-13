from sqlalchemy import Column, DateTime, Date, Integer, String, ForeignKey, Time, Enum as SQLEnum, UniqueConstraint, Boolean, Float
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import relationship, synonym, foreign, remote
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
    # Keep DB column as legacy-spelled `immidiate_boss`; expose
    # `immediate_boss` alias for compatibility in newer code.
    immidiate_boss = Column("immidiate_boss", String, ForeignKey("staff.id"), nullable=True)
    immediate_boss = synonym("immidiate_boss")
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
    assigned_doubts = relationship("DoubtTeacher", back_populates="teacher")
    responses = relationship("DoubtResponse", back_populates="teacher")
    assignments = relationship(
        "Assignment",
        back_populates="created_by_teacher",
        primaryjoin="Teacher.id == Assignment.created_by_teacher_id",
        foreign_keys="[Assignment.created_by_teacher_id]",
    )
    ratings = relationship(
        "TeacherRating",
        back_populates="teacher",
        cascade="all, delete-orphan",
        primaryjoin="Teacher.user_id == foreign(TeacherRating.teacher_user_id)",
        remote_side="Teacher.user_id",
    )
    avg_rating = Column(Float, default=0.0)
    rating_count = Column(Integer, default=0)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.id:
            self.id = f"TCH-{str(uuid.uuid4().int)[:6]}"


class VerificationStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    BLOCKED = "blocked"
    REJECTED = "rejected"


class ProfileStatus(str, Enum):
    DRAFT = "draft"
    PROFILE_SUBMITTED = "profile_submitted"


class SelfSignedTeacher(Base):
    __tablename__ = "self_signed_teachers"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    gender = Column(String(20), nullable=True)
    dob = Column(Date, nullable=True)
    profile_image = Column(String, nullable=True)
    phone = Column(String(20), nullable=False)
    email = Column(String(255), nullable=False, unique=True)
    bio = Column(String(500), nullable=True)
    qualification = Column(String(255), nullable=True)
    university = Column(String(255), nullable=True)
    institution_name = Column(String(255), nullable=True)
    designation = Column(String(255), nullable=True)
    institution_pin_code = Column(String(20), nullable=True)
    division = Column(String(100), nullable=True)
    district = Column(String(100), nullable=True)
    state = Column(String(100), nullable=True)
    landmark = Column(String(255), nullable=True)
    joining_date = Column(Date, nullable=True)
    official_id_card = Column(String, nullable=True)
    invite_code = Column(String(32), nullable=False, unique=True)
    profile_status = Column(SQLEnum(ProfileStatus), default=ProfileStatus.DRAFT, nullable=False)
    rejection_reason = Column(String(500), nullable=True)
    blocked_reason = Column(String(500), nullable=True)
    verified_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    verified_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship(
        "User",
        back_populates="self_signed_teacher_profile",
        foreign_keys=[user_id],
    )
    students = relationship("SelfSignedStudent", back_populates="self_signed_teacher", cascade="all, delete-orphan")
    assignments = relationship(
        "Assignment",
        back_populates="created_by_self_signed_teacher",
        primaryjoin="SelfSignedTeacher.id == Assignment.created_by_self_signed_teacher_id",
        foreign_keys="[Assignment.created_by_self_signed_teacher_id]",
    )
    teaching_configurations = relationship(
        "SelfSignedTeacherTeachingConfiguration",
        back_populates="teacher",
        cascade="all, delete-orphan"
    )

    @property
    def verification_status(self):
        return self.user.verification_status if self.user else None

    @property
    def profile_completed(self):
        return self.user.profile_completed if self.user else False

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.invite_code:
            self.invite_code = f"TCH-{uuid.uuid4().hex[:10]}"


class SelfSignedTeacherTeachingConfiguration(Base):
    __tablename__ = "self_signed_teacher_teaching_configurations"

    id = Column(Integer, primary_key=True, index=True)
    self_signed_teacher_id = Column(Integer, ForeignKey("self_signed_teachers.id"), nullable=False)
    board_id = Column(String(50), nullable=False)
    class_id = Column(Integer, ForeignKey("school_classes_subjects.id"), nullable=False)
    subject_ids = Column(ARRAY(Integer), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    teacher = relationship("SelfSignedTeacher", back_populates="teaching_configurations")


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

    teacher = relationship("Teacher", backref="class_section_subjects")
    school = relationship("School", backref="teacher_assignments")
    section = relationship("Section")
    subject = relationship("Subject")
    class_ = relationship("Class")
    # assigned_doubts = relationship("DoubtTeacher", back_populates="teacher")
    # responses = relationship("DoubtResponse", back_populates="teacher")


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
            

class TeacherWallet(Base):
    __tablename__ = "teacher_wallets"

    id = Column(Integer, primary_key=True)
    teacher_id = Column(String, ForeignKey("teachers.id"), unique=True)

    total_earned = Column(Integer, default=0)
    balance = Column(Integer, default=0)

    level = Column(Integer, default=1)

    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

class RewardTransaction(Base):
    __tablename__ = "reward_transactions"

    id = Column(Integer, primary_key=True)
    teacher_id = Column(String, ForeignKey("teachers.id"))

    points = Column(Integer)
    type = Column(String)  # EARN / REDEEM / WITHDRAW

    exam_id = Column(String, nullable=True)

    created_at = Column(DateTime, server_default=func.now())

class TeacherBankAccount(Base):
    __tablename__ = "teacher_bank_accounts"

    id = Column(Integer, primary_key=True)
    teacher_id = Column(String, ForeignKey("teachers.id"))

    account_holder_name = Column(String)
    account_number = Column(String)
    ifsc_code = Column(String)
    bank_name = Column(String)

    is_default = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())

class WithdrawalRequest(Base):
    __tablename__ = "withdrawal_requests"

    id = Column(Integer, primary_key=True)
    teacher_id = Column(String, ForeignKey("teachers.id"))

    amount = Column(Integer)
    status = Column(String, default="PENDING")  # PENDING / SUCCESS / HOLD

    bank_account_id = Column(Integer, ForeignKey("teacher_bank_accounts.id"))

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())
    bank_account = relationship(
        "TeacherBankAccount",
        backref="withdrawal_requests"
    )

class AdminWallet(Base):
    __tablename__ = "admin_wallets"

    id = Column(Integer, primary_key=True)
    total_added = Column(Integer, default=0)
    available_balance = Column(Integer, default=0)

    updated_at = Column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now()
    )


# =====================================================
# ADMIN BANK ACCOUNT
# =====================================================
class AdminBankAccount(Base):
    __tablename__ = "admin_bank_accounts"

    id = Column(Integer, primary_key=True)
    account_holder_name = Column(String)
    account_number = Column(String)
    ifsc_code = Column(String)
    bank_name = Column(String)
    is_default = Column(Boolean, default=False)

    created_at = Column(
        DateTime,
        server_default=func.now()
    )