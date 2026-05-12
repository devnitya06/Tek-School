from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Date,DateTime,Enum,Float,UniqueConstraint,JSON,Text
from sqlalchemy.orm import relationship
from app.db.session import Base
from sqlalchemy.sql import func
from enum import Enum as PyEnum
from sqlalchemy import Enum as SQLEnum

class StudentStatus(PyEnum):
    TRIAL = "TRIAL"
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"

class InstallmentType(str, PyEnum):
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    HALF_YEARLY = "half_yearly"
    YEARLY = "yearly"
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
    registration_no = Column(String(50), nullable=True)
    blood_group = Column(String(20), nullable=True)
    date_of_admission = Column(Date, nullable=True)
    previous_class_marks_obtained = Column(Integer, nullable=True)
    previous_class_overall_percentage = Column(Float, nullable=True)
    previous_class_final_grade = Column(String(20), nullable=True)
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
    select_class_id = Column(Integer, ForeignKey("school_classes_subjects.id"), nullable=True)

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
    # Each student's task completion statuses
    student_task_statuses = relationship("StudentTaskStatus",back_populates="student",cascade="all, delete-orphan")
    payments = relationship("StudentPayment", back_populates="student", cascade="all, delete-orphan")
    selected_class = relationship("SchoolClassSubject", backref="students")
    subscriptions = relationship(
    "StudentSubscription",
    back_populates="student",
    foreign_keys="StudentSubscription.student_id"
)
    doubts = relationship("Doubt", back_populates="student", cascade="all, delete-orphan")



class Parent(Base):
    __tablename__ = "parents"

    id = Column(Integer, primary_key=True, index=True)
    parent_name = Column(String(100), nullable=False)
    relation = Column(String(50), nullable=False)
    phone = Column(String(15), nullable=False)
    email = Column(String(100), nullable=False, unique=True)
    occupation = Column(String(100), nullable=True)
    education = Column(String(150), nullable=True)
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
    select_class_id = Column(Integer, ForeignKey("school_classes_subjects.id"), nullable=True)
    school_name = Column(String(255), nullable=True)
    school_location = Column(String(255), nullable=True)

    pin = Column(Integer, nullable=True)
    division = Column(String(100), nullable=True)
    district = Column(String(100), nullable=True)
    state = Column(String(100), nullable=True)

    plot = Column(String(255), nullable=True)
    status = Column(Enum(StudentStatus), default=StudentStatus.TRIAL.value, nullable=False)
    status_expiry_date = Column(DateTime, nullable=True)

    #parent details
    parent_name = Column(String(100), nullable=True)
    relation = Column(String(50), nullable=True)
    parent_phone = Column(String(15), nullable=True)
    parent_email = Column(String(100), nullable=True)
    occupation = Column(String(100), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", back_populates="self_signed_student_profile")
    exam_data = relationship("StudentExamData", back_populates="self_signed_student")
    admin_exam_data = relationship("StudentAdminExamData", back_populates="student")
    subscriptions = relationship(
    "StudentSubscription",
    back_populates="self_signed_student",
    foreign_keys="StudentSubscription.self_signed_student_id"
)
    selected_class = relationship("SchoolClassSubject", backref="self_signed_student")
class StudentPayment(Base):
    __tablename__ = "student_payments"
    __table_args__ = (
        UniqueConstraint('student_id', 'class_id', name='unique_student_class_payment'),
    )

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False)
    class_id = Column(Integer, ForeignKey("classes.id"), nullable=False)
    
    # Course Fee
    course_fee = Column(Float, nullable=False, default=0.0)
    
    # Transport Fee
    transport_fee = Column(Float, nullable=False, default=0.0)
    
    # Tek School Fee
    tek_school_fee = Column(Float, nullable=False, default=0.0)
    
    # Installment Type (applies to all fees) - Using String to match database values
    installment_type = Column(String(50), nullable=False, default=InstallmentType.YEARLY.value)
    
    # Payment Clear Amounts (how much has been paid/cleared)
    course_fee_paid = Column(Float, nullable=False, default=0.0)  # Amount paid for course fee
    transport_fee_paid = Column(Float, nullable=False, default=0.0)  # Amount paid for transport fee
    tek_school_fee_paid = Column(Float, nullable=False, default=0.0)  # Amount paid for tek school fee
    
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    # Relationships
    student = relationship("Student", back_populates="payments")
    classes = relationship("Class", back_populates="student_payments")
    transactions = relationship("StudentPaymentTransaction", back_populates="payment", cascade="all, delete-orphan")


class PaymentTransactionStatus(str, PyEnum):
    SCHOOL_REQUEST = "school_request"  # School sent payment reminder/request
    PAYMENT_UPDATE_BY_STUDENT = "payment_update_by_student"  # Student filled/updated the payment form
    DONE = "done"  # School verified and amounts calculated
    CANCEL = "cancel"  # School cancelled the request
    # Legacy statuses for backward compatibility
    PENDING = "pending"  # Old: Waiting for school verification
    VERIFIED = "verified"  # Old: Verified by school, amounts updated
    REJECTED = "rejected"  # Old: Rejected by school

class StudentPaymentTransaction(Base):
    __tablename__ = "student_payment_transactions"

    id = Column(Integer, primary_key=True, index=True)
    student_payment_id = Column(Integer, ForeignKey("student_payments.id"), nullable=False)
    
    # Transaction details
    amount = Column(Float, nullable=False)  # Total amount paid in this transaction
    payment_type = Column(String(50), nullable=False)  # "course_fee", "transport_fee", or "tek_school_fee" (primary type)
    payment_breakdown = Column(JSON, nullable=True)  # Dynamic breakdown: {"course_fee": 5.0, "transport_fee": 2.0, "tek_school_fee": 1.0}
    transaction_date = Column(DateTime, nullable=False, default=func.now())
    description = Column(String(500), nullable=True)  # Description/notes
    files = Column(JSON, nullable=True)  # Array of file URLs (payslips, receipts, etc.)
    
    # Payment method (optional)
    payment_method = Column(String(50), nullable=True)  # "cash", "bank_transfer", "cheque", etc.
    transaction_reference = Column(String(100), nullable=True)  # Transaction ID, cheque number, etc.
    
    # Bank account (optional) - which bank account was used for this payment
    bank_account_id = Column(Integer, ForeignKey("bank_accounts.id"), nullable=True)  # Bank account selected for payment
    
    # Verification status - Using String instead of SQLEnum to match database values
    status = Column(String(50), default=PaymentTransactionStatus.VERIFIED.value, nullable=False)  # Default to "verified" for backward compatibility
    verified_at = Column(DateTime, nullable=True)  # When school verified the payment
    verified_by = Column(Integer, ForeignKey("users.id"), nullable=True)  # Who verified the payment
    rejection_reason = Column(String(500), nullable=True)  # Reason if rejected
    
    created_at = Column(DateTime, default=func.now())
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)  # Who recorded this payment
    
    # Relationships
    payment = relationship("StudentPayment", back_populates="transactions")
    created_by_user = relationship("User", foreign_keys=[created_by])
    verified_by_user = relationship("User", foreign_keys=[verified_by])
    bank_account = relationship("BankAccount", foreign_keys=[bank_account_id])

class DoubtStatus(str, PyEnum):
    PENDING = "PENDING"
    SOLVED = "SOLVED"
    UNSOLVED = "UNSOLVED"


class TeacherDoubtStatus(str, PyEnum):
    PENDING = "PENDING"
    RESPONDED = "RESPONDED"


class ResponseAction(str, PyEnum):
    SOLVE = "SOLVE"
    DISCUSS = "DISCUSS"
class Doubt(Base):
    __tablename__ = "doubts"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False)
    school_id = Column(String, ForeignKey("schools.id"), nullable=False)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False)
    class_id = Column(Integer, ForeignKey("classes.id"), nullable=False)
    section_id = Column(Integer, ForeignKey("sections.id"), nullable=False)
    chapter_name = Column(String(255), nullable=False)
    question = Column(Text, nullable=False)
    key_points = Column(Text, nullable=True)
    attachment = Column(String, nullable=True)
    status = Column(SQLEnum(DoubtStatus, name="doubt_status"),default=DoubtStatus.PENDING,nullable=False)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    # ✅ relationships
    student = relationship("Student", back_populates="doubts")
    subject = relationship("Subject")
    teachers = relationship("DoubtTeacher", back_populates="doubt", cascade="all, delete-orphan")
    responses = relationship("DoubtResponse", back_populates="doubt", cascade="all, delete-orphan")

class DoubtTeacher(Base):
    __tablename__ = "doubt_teachers"
    id = Column(Integer, primary_key=True)
    doubt_id = Column(Integer, ForeignKey("doubts.id", ondelete="CASCADE"))
    teacher_id = Column(String, ForeignKey("teachers.id"))
    status = Column(SQLEnum(TeacherDoubtStatus, name="teacher_doubt_status"),default=TeacherDoubtStatus.PENDING,nullable=False)

    # ✅ relationships
    doubt = relationship("Doubt", back_populates="teachers")
    teacher = relationship("Teacher", back_populates="assigned_doubts")

    __table_args__ = (
        UniqueConstraint("doubt_id", "teacher_id", name="unique_doubt_teacher"),
    )

class DoubtResponse(Base):
    __tablename__ = "doubt_responses"

    id = Column(Integer, primary_key=True)
    doubt_id = Column(Integer, ForeignKey("doubts.id", ondelete="CASCADE"))
    teacher_id = Column(String, ForeignKey("teachers.id"))
    answer = Column(Text, nullable=False)
    attachment = Column(String, nullable=True)
    action = Column(SQLEnum(ResponseAction, name="response_action"),nullable=False)
    created_at = Column(DateTime, default=func.now())
    # ✅ relationships
    doubt = relationship("Doubt", back_populates="responses")
    teacher = relationship("Teacher", back_populates="responses")
    __table_args__ = (
        UniqueConstraint("doubt_id", "teacher_id", name="unique_doubt_response"),
    )