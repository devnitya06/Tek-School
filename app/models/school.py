from sqlalchemy import (
    Column,
    Integer,
    String,
    ForeignKey,
    Table,
    Time,
    UniqueConstraint,
    Date,
    Boolean,
    DateTime,
    Float,
    ARRAY,
    Text,
    JSON,
    TypeDecorator,
)
from sqlalchemy.dialects.postgresql import ARRAY as PG_ARRAY
from sqlalchemy.orm import relationship
from app.db.session import Base
import uuid
from enum import Enum
from sqlalchemy import Enum as SQLEnum
from datetime import datetime
from sqlalchemy.sql import func
from datetime import date


class SchoolType(str, Enum):
    PVT = "private"
    GOVT = "government"
    SEMI_GOVT = "semi-government"
    INTERNATIONAL = "international"


class SchoolMedium(str, Enum):
    ENGLISH = "english"
    HINDI = "hindi"
    BILINGUAL = "bilingual"
    OTHER = "other"


class SchoolBoard(str, Enum):
    CBSE = "cbse"
    ICSE = "icse"
    STATE = "stateboard"
    IB = "ib"
    OTHER = "other"


class ExamTypeEnum(str, Enum):
    MOCK = "mock"
    RANK = "rank"


class ExamStatusEnum(str, Enum):
    ACTIVE = "active"
    PENDING = "pending"
    EXPIRED = "expired"
    DECLINED = "declined"


class SchoolAccountType(str, Enum):
    LISTING = "listing"  # Only listing account (can login immediately)
    BUSINESS = "business"  # Business account (has both listing + business permissions, requires admin approval)


class EvaluationScopeEnum(str, Enum):
    INTERNAL = "internal"
    EXTERNAL = "external"
    BOTH = "both"


class QuestionTypeEnum(str, Enum):
    MCQ = "mcq"
    SHORT = "short"
    LONG = "long"


class ExamStatus(str, Enum):
    pass_ = "pass"
    fail = "fail"


class AchievementLevel(str, Enum):
    STATE = "state"
    NATIONAL = "national"
    INTERNATIONAL = "international"


class SchoolAccountTypeDecorator(TypeDecorator):
    """Custom type decorator to handle case-insensitive enum mapping"""

    impl = String
    cache_ok = True

    def __init__(self, enum_class, length=50):
        self.enum_class = enum_class
        self.length = length
        super().__init__(length=length)

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, self.enum_class):
            return value.value
        # Handle case-insensitive string matching
        if isinstance(value, str):
            value_lower = value.lower()
            for enum_member in self.enum_class:
                if enum_member.value.lower() == value_lower:
                    return enum_member.value
        return value

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, self.enum_class):
            return value
        # Handle case-insensitive string matching when reading from DB
        if isinstance(value, str):
            value_lower = value.lower()
            for enum_member in self.enum_class:
                if enum_member.value.lower() == value_lower:
                    return enum_member
            # If no match found, try direct value match
            try:
                return self.enum_class(value)
            except ValueError:
                # Try case-insensitive member name match as fallback
                for enum_member in self.enum_class:
                    if enum_member.name.lower() == value_lower:
                        return enum_member
        return value


class School(Base):
    __tablename__ = "schools"

    id = Column(String, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True)
    # School Information
    school_name = Column(String, nullable=False)
    school_type = Column(SQLEnum(SchoolType), nullable=True)
    school_medium = Column(SQLEnum(SchoolMedium), nullable=True)
    school_board = Column(SQLEnum(SchoolBoard), nullable=True)
    establishment_year = Column(Integer, nullable=True)
    establishment_month = Column(Integer, nullable=True)
    register_no = Column(String, nullable=True)

    # Address Information
    profile_pic_url = Column(String, nullable=True)
    banner_pic_url = Column(String, nullable=True)
    pin_code = Column(String(10), nullable=True)
    block_division = Column(String)
    district = Column(String, nullable=True)
    state = Column(String, nullable=True)
    country = Column(String, nullable=False, default="India")

    # Contact Information
    school_email = Column(String, nullable=False)
    school_phone = Column(String(15), nullable=False)
    school_alt_phone = Column(String(15))
    school_website = Column(String)
    school_location = Column(String(100), nullable=True)

    # Principal Information
    principal_name = Column(String, nullable=True)
    principal_designation = Column(String)
    principal_email = Column(String)
    principal_phone = Column(String(15))
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    account_type = Column(
        SchoolAccountTypeDecorator(SchoolAccountType, length=50),
        default=SchoolAccountType.LISTING,
    )
    is_business_approved = Column(Boolean, default=False)
    is_promotion_pending = Column(Boolean, default=False)
    # When no bank account exists, fees/payments default to cash (offline) ledger.
    default_settlement_channel = Column(
        String(32),
        nullable=False,
        default="cash_offline",
    )
    created_at = Column(DateTime, default=func.now())

    school_other_email = Column(String, nullable=True)
    institution_categories = Column(ARRAY(String), nullable=True)
    have_digital_board = Column(Boolean, nullable=True, default=False)
    have_cctv_in_campus = Column(Boolean, nullable=True, default=False)
    have_scholarship_opportunities = Column(Boolean, nullable=True, default=False)
    have_extra_curricular_activities = Column(Boolean, nullable=True, default=False)
    school_location = Column(String, nullable=True)
    total_teachers = Column(Integer, nullable=True)
    total_students = Column(Integer, nullable=True)
    class_from = Column(String, nullable=True)
    class_to = Column(String, nullable=True)
    due_installment_type = Column(JSON, nullable=True)
    transportation_facility = Column(Boolean, nullable=True, default=False)
    playground_facility = Column(Boolean, nullable=True, default=False)
    teaching_method = Column(JSON, nullable=True)
    catalogue = Column(ARRAY(String), nullable=True)
    photo_gallery = Column(ARRAY(String), nullable=True)
    # Teacher/staff attendance QR: latest token per mode only; regenerating overwrites and invalidates the old one.
    attendance_qr_mark_in_token = Column(String(64), nullable=True)
    attendance_qr_mark_out_token = Column(String(64), nullable=True)

    user = relationship("User", backref="school")
    teachers = relationship(
        "Teacher", back_populates="school", cascade="all, delete-orphan"
    )
    classes = relationship("Class", back_populates="school")
    subjects = relationship("Subject", back_populates="school")
    extra_activities = relationship("ExtraCurricularActivity", back_populates="school")
    sections = relationship("Section", back_populates="school")
    transports = relationship("Transport", back_populates="school")
    students = relationship("Student", back_populates="school")
    staff_members = relationship(
        "Staff", back_populates="school", cascade="all, delete-orphan"
    )
    designation_compensation_templates = relationship(
        "DesignationCompensationTemplate",
        back_populates="school",
        cascade="all, delete-orphan",
    )
    timetables = relationship(
        "Timetable", back_populates="school", cascade="all, delete"
    )
    # timetable_periods = relationship("TimetablePeriod", back_populates="school")
    # school = relationship("School", back_populates="timetable_periods")
    school_margins = relationship(
        "SchoolMarginConfiguration",
        back_populates="school",
        cascade="all, delete-orphan",
    )
    transaction_history = relationship(
        "TransactionHistory", back_populates="school", cascade="all, delete-orphan"
    )
    exams = relationship("Exam", back_populates="school")
    exam_data = relationship("StudentExamData", back_populates="school")
    leave_requests = relationship(
        "LeaveRequest", back_populates="school", cascade="all, delete"
    )
    bank_accounts = relationship(
        "BankAccount", back_populates="school", cascade="all, delete-orphan"
    )
    settlement_transactions = relationship(
        "SchoolSettlementTransaction",
        back_populates="school",
        cascade="all, delete-orphan",
    )
    cash_deposit_transactions = relationship(
        "CashDepositTransaction",
        back_populates="school",
        cascade="all, delete-orphan",
    )
    faqs = relationship("FAQ", secondary="school_faqs", back_populates="schools")
    listed_school_students = relationship(
        "ListedSchoolStudent", back_populates="school", cascade="all, delete-orphan"
    )
    school_info = relationship(
        "SchoolInfo",
        back_populates="school",
        uselist=False,
        cascade="all, delete-orphan",
    )
    class_fees = relationship(
        "SchoolClassFee", back_populates="school", cascade="all, delete-orphan"
    )
    team_members = relationship(
        "SchoolTeamMember", back_populates="school", cascade="all, delete-orphan"
    )
    excellent_students = relationship(
        "ExcellentStudent", back_populates="school", cascade="all, delete-orphan"
    )
    school_ratings = relationship(
        "SchoolRating", back_populates="school", cascade="all, delete-orphan"
    )
    support_plus = relationship(
        "SupportPlus", back_populates="school", cascade="all, delete-orphan"
    )
    communication_sections = relationship(
        "CommunicationSection", back_populates="school", cascade="all, delete-orphan"
    )
    achievements = relationship(
        "Achievement", back_populates="school", cascade="all, delete-orphan"
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.id:
            self.id = f"SCH-{str(uuid.uuid4().int)[:6]}"


class_subjects = Table(
    "class_subjects",
    Base.metadata,
    Column("class_id", Integer, ForeignKey("classes.id")),
    Column("subject_id", Integer, ForeignKey("subjects.id")),
    Column("school_id", String, ForeignKey("schools.id")),
    Column(
        "school_class_subject_id",
        Integer,
        ForeignKey("school_classes_subjects.id", ondelete="SET NULL"),
        nullable=True,
    ),
)


class_extra_curricular = Table(
    "class_extra_curricular",
    Base.metadata,
    Column("class_id", Integer, ForeignKey("classes.id")),
    Column("activity_id", Integer, ForeignKey("extra_curricular_activities.id")),
    Column("school_id", String, ForeignKey("schools.id")),
)

class_assigned_teachers = Table(
    "class_assigned_teachers",
    Base.metadata,
    Column("class_id", Integer, ForeignKey("classes.id")),
    Column("teacher_id", String, ForeignKey("teachers.id")),
    Column("school_id", String, ForeignKey("schools.id")),
)
class_section = Table(
    "class_section",
    Base.metadata,
    Column("class_id", Integer, ForeignKey("classes.id")),
    Column("section_id", Integer, ForeignKey("sections.id")),
    Column("school_id", String, ForeignKey("schools.id")),
)


# Subject Models
class Subject(Base):
    __tablename__ = "subjects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100))
    school_id = Column(String, ForeignKey("schools.id"))

    school = relationship("School", back_populates="subjects")
    classes = relationship("Class", secondary=class_subjects, back_populates="subjects")


class class_optional_subjects(Base):
    __tablename__ = "class_optional_subjects"

    class_id = Column(
        Integer, ForeignKey("classes.id", ondelete="CASCADE"), primary_key=True
    )
    subject_id = Column(
        Integer, ForeignKey("subjects.id", ondelete="CASCADE"), primary_key=True
    )


class ExtraCurricularActivity(Base):
    __tablename__ = "extra_curricular_activities"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100))
    school_id = Column(String, ForeignKey("schools.id"))

    school = relationship("School", back_populates="extra_activities")
    classes = relationship(
        "Class",
        secondary=class_extra_curricular,
        back_populates="extra_curricular_activities",
    )


# Class Model (main table)
class Class(Base):
    __tablename__ = "classes"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100))
    start_time = Column(Time)
    end_time = Column(Time)
    school_id = Column(String, ForeignKey("schools.id"))
    annual_course_fee = Column(Float, default=10000.0)
    annual_transport_fee = Column(Float, default=3000.0)
    tek_school_payment_annually = Column(Float, default=1000.0)
    admission_fee = Column(Float, default=0.0)
    class_start_date = Column(Date, nullable=False)
    class_end_date = Column(Date, nullable=False)

    # Relationships
    school = relationship("School", back_populates="classes")
    students = relationship("Student", back_populates="classes")

    # Many-to-many relationships
    subjects = relationship(
        "Subject", secondary=class_subjects, back_populates="classes"
    )
    optional_subjects = relationship(
        "Subject", secondary="class_optional_subjects", back_populates="classes"
    )
    assigned_teachers = relationship(
        "Teacher", secondary=class_assigned_teachers, back_populates="assigned_classes"
    )
    extra_curricular_activities = relationship(
        "ExtraCurricularActivity",
        secondary=class_extra_curricular,
        back_populates="classes",
    )
    sections = relationship(
        "Section", secondary=class_section, back_populates="classes"
    )
    school_margins = relationship("SchoolMarginConfiguration", back_populates="class_")
    exams = relationship("Exam", back_populates="class_obj")
    timetables = relationship("Timetable", back_populates="class_")
    student_payments = relationship("StudentPayment", back_populates="classes")

    # Unique constraint to prevent duplicate class names within a school
    __table_args__ = (
        UniqueConstraint("name", "school_id", name="uq_class_name_school"),
    )


class Transport(Base):
    __tablename__ = "transports"

    id = Column(Integer, primary_key=True, index=True)
    vechicle_name = Column(String(50), nullable=False)
    vechicle_number = Column(String(50), nullable=False)
    driver_name = Column(String(100), nullable=False)
    phone_no = Column(String(20), nullable=False)
    duty_start_time = Column(Time, nullable=False)
    duty_end_time = Column(Time, nullable=False)
    school_id = Column(String, ForeignKey("schools.id"), nullable=False)
    pickup_stops = relationship(
        "PickupStop", back_populates="transport", cascade="all, delete-orphan"
    )
    drop_stops = relationship(
        "DropStop", back_populates="transport", cascade="all, delete-orphan"
    )

    # Relationship to students
    students = relationship("Student", back_populates="driver")
    school = relationship("School", back_populates="transports")


class PickupStop(Base):
    __tablename__ = "pickup_stops"

    id = Column(Integer, primary_key=True, index=True)
    transport_id = Column(Integer, ForeignKey("transports.id"), nullable=False)
    stop_name = Column(String(100), nullable=False)
    stop_time = Column(Time, nullable=False)

    transport = relationship("Transport", back_populates="pickup_stops")


class DropStop(Base):
    __tablename__ = "drop_stops"

    id = Column(Integer, primary_key=True, index=True)
    transport_id = Column(Integer, ForeignKey("transports.id"), nullable=False)
    stop_name = Column(String(100), nullable=False)
    stop_time = Column(Time, nullable=False)

    transport = relationship("Transport", back_populates="drop_stops")


class Attendance(Base):
    __tablename__ = "attendances"
    id = Column(Integer, primary_key=True, index=True)

    student_id = Column(Integer, ForeignKey("students.id"), nullable=True)
    teachers_id = Column(String, ForeignKey("teachers.id"), nullable=True)
    staff_id = Column(String, ForeignKey("staff.id"), nullable=True)
    date = Column(Date, nullable=False)
    status = Column(String(1), nullable=False)
    is_verified = Column(Boolean, nullable=True)
    student = relationship("Student", back_populates="attendances")
    teacher = relationship("Teacher", back_populates="attendances")
    staff = relationship("Staff", back_populates="attendances")
    is_today_present = Column(Boolean, default=True, nullable=False)
    mark_in_at = Column(DateTime, nullable=True)
    mark_out_at = Column(DateTime, nullable=True)
    # True = recorded via QR scan; False = manual / other API; None = unknown or not applicable yet.
    mark_in_via_qr = Column(Boolean, nullable=True)
    mark_out_via_qr = Column(Boolean, nullable=True)
    verified_at = Column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint("student_id", "date", name="uq_student_attendance"),
        UniqueConstraint("teachers_id", "date", name="uq_teacher_attendance"),
        UniqueConstraint("staff_id", "date", name="uq_staff_attendance"),
    )

    def update_today_status(self):
        """Automatically set is_today_present based on whether date == today."""
        self.is_today_present = self.date == date.today()


class WeekDay(Enum):
    MONDAY = "Monday"
    TUESDAY = "Tuesday"
    WEDNESDAY = "Wednesday"
    THURSDAY = "Thursday"
    FRIDAY = "Friday"
    SATURDAY = "Saturday"


class Timetable(Base):
    __tablename__ = "timetables"

    id = Column(Integer, primary_key=True, index=True)
    school_id = Column(String, ForeignKey("schools.id"), nullable=False)
    class_id = Column(Integer, ForeignKey("classes.id"), nullable=False)
    section_id = Column(Integer, ForeignKey("sections.id"), nullable=False)
    is_published = Column(Boolean, default=False)
    published_at = Column(DateTime, nullable=True)
    # A timetable belongs to a school/class/section
    school = relationship("School", back_populates="timetables")
    days = relationship(
        "TimetableDay", back_populates="timetable", cascade="all, delete-orphan"
    )
    class_ = relationship("Class", back_populates="timetables")
    section = relationship("Section", back_populates="timetables")

    __table_args__ = (
        UniqueConstraint(
            "school_id", "class_id", "section_id", name="uq_timetable_class_section"
        ),
    )


class TimetableDay(Base):
    __tablename__ = "timetable_days"

    id = Column(Integer, primary_key=True)
    timetable_id = Column(Integer, ForeignKey("timetables.id"), nullable=False)
    day = Column(SQLEnum(WeekDay, name="weekday"), nullable=False)

    timetable = relationship("Timetable", back_populates="days")
    periods = relationship(
        "TimetablePeriod", back_populates="day", cascade="all, delete-orphan"
    )

    __table_args__ = (UniqueConstraint("timetable_id", "day", name="uq_timetable_day"),)


class TimetablePeriod(Base):
    __tablename__ = "timetable_periods"

    id = Column(Integer, primary_key=True)
    day_id = Column(Integer, ForeignKey("timetable_days.id"), nullable=False)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False)
    teacher_id = Column(String, ForeignKey("teachers.id"), nullable=False)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)

    day = relationship("TimetableDay", back_populates="periods")
    # school = relationship("School", back_populates="timetable_periods")
    teacher = relationship("Teacher", back_populates="timetable_periods")
    subject = relationship("Subject")


class SchoolMarginConfiguration(Base):
    __tablename__ = "school_margin_configuration"
    id = Column(Integer, primary_key=True, index=True)
    school_id = Column(String, ForeignKey("schools.id"), nullable=False)
    class_id = Column(Integer, ForeignKey("classes.id"), nullable=False)
    credit_configuration_id = Column(Integer, ForeignKey("credit_configuration.id"))
    margin_value = Column(Integer, nullable=False)

    school = relationship("School", back_populates="school_margins")
    class_ = relationship("Class", back_populates="school_margins")
    credit_configuration = relationship(
        "CreditConfiguration", back_populates="school_margins"
    )


class TransactionHistory(Base):
    __tablename__ = "transaction_history"

    id = Column(Integer, primary_key=True, index=True)
    school_id = Column(String, ForeignKey("schools.id"), nullable=False)
    amount = Column(Float, nullable=False)
    transaction_id = Column(String, nullable=False, unique=True)
    order_id = Column(String, nullable=False)
    status = Column(String, nullable=False, default="SUCCESS")
    created_at = Column(DateTime(timezone=True), default=func.now())

    school = relationship("School", back_populates="transaction_history")


exam_sections = Table(
    "exam_sections",
    Base.metadata,
    Column("exam_id", String, ForeignKey("exams.id"), primary_key=True),
    Column("section_id", Integer, ForeignKey("sections.id"), primary_key=True),
)


class Section(Base):
    __tablename__ = "sections"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50))
    school_id = Column(String, ForeignKey("schools.id"))

    school = relationship("School", back_populates="sections")
    classes = relationship("Class", secondary=class_section, back_populates="sections")
    students = relationship("Student", back_populates="section")
    exams = relationship("Exam", secondary=exam_sections, back_populates="sections")
    timetables = relationship("Timetable", back_populates="section")


class Exam(Base):
    __tablename__ = "exams"

    id = Column(String, primary_key=True)
    school_id = Column(String, ForeignKey("schools.id"), nullable=True)
    class_id = Column(Integer, ForeignKey("classes.id"), nullable=True)
    selected_class_id = Column(
        Integer, ForeignKey("school_classes_subjects.id"), nullable=True
    )
    subject_id = Column(
        Integer, ForeignKey("school_classes_subjects.id"), nullable=True
    )

    chapters = Column(ARRAY(Integer), nullable=False)

    exam_type = Column(SQLEnum(ExamTypeEnum), nullable=False)
    evaluation_scope = Column(SQLEnum(EvaluationScopeEnum), nullable=True)
    no_of_questions = Column(Integer, default=0)
    total_marks = Column(Integer, default=0)
    pass_percentage = Column(Integer, nullable=False)

    question_time = Column(Integer, nullable=True)
    exam_activation_date = Column(DateTime, nullable=False)
    inactive_date = Column(DateTime, nullable=True)

    max_repeat = Column(Integer, nullable=False, default=1)

    status = Column(SQLEnum(ExamStatusEnum), default=ExamStatusEnum.PENDING)
    no_students_appeared = Column(Integer, default=0)

    created_by = Column(String, ForeignKey("teachers.id"), nullable=True)
    created_by_admin = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    is_published = Column(Boolean, default=False)
    exam_description = Column(Text, nullable=True)

    # Relationships
    school = relationship("School", back_populates="exams")
    teacher = relationship("Teacher", back_populates="created_exams")
    class_obj = relationship("Class", back_populates="exams", foreign_keys=[class_id])
    selected_class = relationship(
        "SchoolClassSubject",
        back_populates="exams_as_selected_class",
        foreign_keys=[selected_class_id],
    )
    subject = relationship(
        "SchoolClassSubject",
        back_populates="exams_as_subject",
        foreign_keys=[subject_id],
    )
    sections = relationship("Section", secondary=exam_sections, back_populates="exams")
    questions = relationship(
        "ExamQuestion", back_populates="exam", cascade="all, delete-orphan"
    )
    student_exam_data = relationship("StudentExamData", back_populates="exam")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.id:
            self.id = f"EXM-{str(uuid.uuid4().int)[:6]}"


class ExamQuestion(Base):
    __tablename__ = "exam_questions"

    id = Column(Integer, primary_key=True)
    exam_id = Column(String, ForeignKey("exams.id", ondelete="CASCADE"))

    question_type = Column(SQLEnum(QuestionTypeEnum), nullable=False)
    question_text = Column(Text, nullable=False)
    marks = Column(Integer, nullable=False)
    image = Column(String, nullable=True)
    # SHORT type
    correct_text_answer = Column(Text, nullable=True)

    # LONG type
    answer_keywords = Column(ARRAY(String), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    exam = relationship("Exam", back_populates="questions")
    options = relationship(
        "ExamQuestionOption", back_populates="question", cascade="all, delete"
    )
    student_answers = relationship("StudentAnswer", back_populates="question")


class ExamQuestionOption(Base):
    __tablename__ = "exam_question_options"

    id = Column(Integer, primary_key=True)
    question_id = Column(Integer, ForeignKey("exam_questions.id", ondelete="CASCADE"))

    option_text = Column(String(255), nullable=False)
    is_correct = Column(Boolean, default=False)

    question = relationship("ExamQuestion", back_populates="options")


class StudentExamData(Base):
    __tablename__ = "student_exam_data"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(
        Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=True
    )
    school_id = Column(
        String, ForeignKey("schools.id", ondelete="CASCADE"), nullable=True
    )
    self_signed_student_id = Column(
        Integer,
        ForeignKey("self_signed_students.id", ondelete="CASCADE"),
        nullable=True,
    )
    exam_id = Column(String, ForeignKey("exams.id", ondelete="CASCADE"), nullable=False)

    attempt_no = Column(Integer, default=1)

    total_marks_obtained = Column(Integer, default=0)
    percentage_scored = Column(Float, default=0.0)

    status = Column(SQLEnum(ExamStatus), nullable=True)  # pass / fail

    is_submitted = Column(Boolean, default=False)

    class_rank = Column(Integer, nullable=True)

    submitted_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    student = relationship("Student", back_populates="exam_data")
    self_signed_student = relationship("SelfSignedStudent", back_populates="exam_data")
    school = relationship("School", back_populates="exam_data")
    exam = relationship("Exam", back_populates="student_exam_data")

    student_answers = relationship(
        "StudentAnswer", back_populates="attempt", cascade="all, delete"
    )

    __table_args__ = (
        UniqueConstraint(
            "exam_id", "student_id", "attempt_no", name="unique_exam_student_attempt"
        ),
    )


class StudentAnswer(Base):
    __tablename__ = "student_answers"

    id = Column(Integer, primary_key=True)

    attempt_id = Column(Integer, ForeignKey("student_exam_data.id", ondelete="CASCADE"))
    question_id = Column(Integer, ForeignKey("exam_questions.id", ondelete="CASCADE"))

    # For MCQ
    # selected_option_id = Column(Integer, ForeignKey("question_options.id"), nullable=True)
    selected_option_id = Column(
        Integer, ForeignKey("exam_question_options.id"), nullable=True
    )

    # For SHORT / LONG
    descriptive_answer = Column(Text, nullable=True)

    marks_awarded = Column(Integer, default=0)

    attempt = relationship("StudentExamData", back_populates="student_answers")
    question = relationship("ExamQuestion", back_populates="student_answers")


class LeaveStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    DECLINED = "declined"


class LeaveType(str, Enum):
    CASUAL = "casual"
    EMERGENCY = "emergency"


class LeaveRequest(Base):
    __tablename__ = "leave_requests"

    id = Column(Integer, primary_key=True, index=True)
    subject = Column(String(255), nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    description = Column(Text, nullable=True)
    attach_file = Column(String, nullable=True)
    # status can only be pending, approved, or declined
    status = Column(SQLEnum(LeaveStatus), default=LeaveStatus.PENDING, nullable=False)
    leave_type = Column(SQLEnum(LeaveType), nullable=False)
    # foreign keys
    school_id = Column(
        String, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False
    )
    teacher_id = Column(
        String, ForeignKey("teachers.id", ondelete="CASCADE"), nullable=True
    )
    student_id = Column(
        Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=True
    )
    staff_id = Column(String, ForeignKey("staff.id", ondelete="CASCADE"), nullable=True)

    # metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # relationships
    school = relationship("School", back_populates="leave_requests")
    teacher = relationship("Teacher", back_populates="leave_requests")
    student = relationship("Student", back_populates="leave_requests")
    staff = relationship("Staff", back_populates="leave_requests")

    def __repr__(self):
        return f"<LeaveRequest(subject={self.subject}, status={self.status})>"


# ---------------- Home Task ----------------
class AssignmentStatus(str, Enum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class TaskStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"


# ---------------- MAIN HOME ASSIGNMENT ----------------
class HomeAssignment(Base):
    __tablename__ = "home_assignments"

    id = Column(Integer, primary_key=True, index=True)
    task_title = Column(String(255), nullable=False)
    task_type = Column(String(100), nullable=False)

    class_id = Column(Integer, ForeignKey("classes.id", ondelete="SET NULL"))
    section_id = Column(Integer, ForeignKey("sections.id", ondelete="SET NULL"))
    subject_id = Column(Integer, ForeignKey("subjects.id", ondelete="SET NULL"))
    chapter_id = Column(Integer, ForeignKey("chapters.id", ondelete="SET NULL"))

    assigned_to_count = Column(Integer, default=0)
    responded_count = Column(Integer, default=0)
    status = Column(SQLEnum(AssignmentStatus), default=AssignmentStatus.IN_PROGRESS)

    date_assigned = Column(DateTime, default=datetime.utcnow)

    teacher_id = Column(String, ForeignKey("teachers.id", ondelete="CASCADE"))
    teacher = relationship("Teacher", back_populates="home_assignments")

    # Relationship to individual tasks
    tasks = relationship(
        "AssignmentTask", back_populates="assignment", cascade="all, delete-orphan"
    )

    # Relationship to assigned students
    assigned_students = relationship(
        "AssignmentStudent", back_populates="assignment", cascade="all, delete-orphan"
    )


# ---------------- ASSIGNMENT TASKS ----------------
class AssignmentTask(Base):
    __tablename__ = "assignment_tasks"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    file = Column(String(255), nullable=True)

    assignment_id = Column(
        Integer, ForeignKey("home_assignments.id", ondelete="CASCADE")
    )
    assignment = relationship("HomeAssignment", back_populates="tasks")

    # Each student's completion status for this task
    student_task_statuses = relationship(
        "StudentTaskStatus", back_populates="task", cascade="all, delete-orphan"
    )


# ---------------- ASSIGNED STUDENTS ----------------
class AssignmentStudent(Base):
    __tablename__ = "assignment_students"

    id = Column(Integer, primary_key=True, index=True)
    assignment_id = Column(
        Integer, ForeignKey("home_assignments.id", ondelete="CASCADE")
    )
    student_id = Column(Integer, ForeignKey("students.id", ondelete="CASCADE"))

    assigned_date = Column(DateTime, default=datetime.utcnow)
    status = Column(SQLEnum(AssignmentStatus), default=AssignmentStatus.IN_PROGRESS)

    # Relationships
    assignment = relationship("HomeAssignment", back_populates="assigned_students")
    student = relationship("Student", back_populates="student_assignments")

    # Student task statuses under this assignment
    student_tasks = relationship(
        "StudentTaskStatus",
        back_populates="assignment_student",
        cascade="all, delete-orphan",
    )


# ---------------- STUDENT TASK STATUS ----------------
class StudentTaskStatus(Base):
    __tablename__ = "student_task_statuses"

    id = Column(Integer, primary_key=True, index=True)
    assignment_student_id = Column(
        Integer, ForeignKey("assignment_students.id", ondelete="CASCADE")
    )
    task_id = Column(Integer, ForeignKey("assignment_tasks.id", ondelete="CASCADE"))
    student_id = Column(Integer, ForeignKey("students.id", ondelete="CASCADE"))

    status = Column(SQLEnum(TaskStatus), default=TaskStatus.PENDING)
    completed_at = Column(DateTime, nullable=True)

    # Relationships
    assignment_student = relationship(
        "AssignmentStudent", back_populates="student_tasks"
    )
    task = relationship("AssignmentTask", back_populates="student_task_statuses")
    student = relationship("Student", back_populates="student_task_statuses")


# Bank Account Model
class BankAccount(Base):
    __tablename__ = "bank_accounts"

    id = Column(Integer, primary_key=True, index=True)
    school_id = Column(String, ForeignKey("schools.id"), nullable=False)
    account_holder_name = Column(String, nullable=False)
    account_number = Column(
        String, nullable=False, unique=True
    )  # Account number must be unique
    ifsc_code = Column(String(11), nullable=False)  # IFSC code is 11 characters
    bank_name = Column(String, nullable=False)
    branch_name = Column(String, nullable=True)
    account_type = Column(String, nullable=False)  # 'savings' or 'current'
    is_primary = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    school = relationship("School", back_populates="bank_accounts")
    settlement_transactions = relationship(
        "SchoolSettlementTransaction",
        back_populates="bank_account",
    )
    cash_deposit_transactions = relationship(
        "CashDepositTransaction",
        back_populates="bank_account",
    )

    # Note: Only one primary account per school is enforced at application level
    # A partial unique index can be added at database level for PostgreSQL:
    # CREATE UNIQUE INDEX uq_school_primary_account ON bank_accounts (school_id) WHERE is_primary = true;


class SchoolSettlementTransaction(Base):
    """
    Ledger of school-side settlements: either a specific bank account or cash (offline).
    `settlement_channel` is `cash_offline` (bank_account_id NULL) or `bank_account` (bank_account_id set).
    """

    __tablename__ = "school_settlement_transactions"

    id = Column(Integer, primary_key=True, index=True)
    school_id = Column(
        String,
        ForeignKey("schools.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    settlement_channel = Column(String(32), nullable=False, index=True)
    bank_account_id = Column(
        Integer,
        ForeignKey("bank_accounts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    amount = Column(Float, nullable=False)
    direction = Column(String(8), nullable=False, default="in")
    category = Column(String(100), nullable=True)
    source_reference = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)
    recorded_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    school = relationship("School", back_populates="settlement_transactions")
    bank_account = relationship(
        "BankAccount", back_populates="settlement_transactions"
    )


class CashDepositTransaction(Base):
    """
    Cash to bank transfer record:
    deduct from cash ledger and add to selected bank ledger.
    """

    __tablename__ = "cash_deposit_transactions"

    id = Column(Integer, primary_key=True, index=True)
    school_id = Column(String, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True)
    bank_account_id = Column(Integer, ForeignKey("bank_accounts.id", ondelete="CASCADE"), nullable=False, index=True)

    payment_title = Column(String(255), nullable=False)
    deposite_amount = Column(Float, nullable=False)
    associate_in_payment = Column(String(255), nullable=True)
    payment_description = Column(Text, nullable=True)
    depositor_name = Column(String(255), nullable=False)
    deposite_date = Column(DateTime, nullable=False, default=func.now())
    attached_file = Column(String(1000), nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    school = relationship("School", back_populates="cash_deposit_transactions")
    bank_account = relationship("BankAccount", back_populates="cash_deposit_transactions")


class Worker(Base):
    __tablename__ = "workers"

    id = Column(String, primary_key=True, index=True)
    school_id = Column(String, ForeignKey("schools.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    role = Column(
        String, nullable=False
    )  # plumber, labor, electrician, technician, etc.
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    # Relationships
    school = relationship("School", backref="workers")
    user = relationship("User", backref="worker_profile")
    payment_records = relationship(
        "PaymentRecord", back_populates="worker", cascade="all, delete-orphan"
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.id:
            role_prefix_map = {
                "technician": "TEC",
                "plumber": "PLU",
                "labor": "LAB",
                "electrician": "ELE",
                "carpenter": "CAR",
                "painter": "PAI",
                "mason": "MAS",
                "welder": "WEL",
                "mechanic": "MEC",
            }
            role_lower = self.role.lower() if self.role else "WRK"
            prefix = role_prefix_map.get(role_lower, "WRK")
            self.id = f"{prefix}-{str(uuid.uuid4().int)[:6]}"


class CommunicationSection(Base):
    """Model for storing school communication/contact information."""
    __tablename__ = "communication_sections"

    id = Column(String, primary_key=True, index=True)
    school_id = Column(String, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True)
    
    contact_person_name = Column(String(255), nullable=False)
    contact_numbers = Column(ARRAY(String), nullable=False)  # Multiple phone numbers
    contact_time = Column(String(255), nullable=True)  # Example: "10 AM – 6 PM"
    working_days = Column(String(255), nullable=True)  # Example: "Monday – Saturday"
    website_url = Column(String(500), nullable=True)
    facebook_page_link = Column(String(500), nullable=True)
    instagram_page = Column(String(500), nullable=True)
    twitter_x_page = Column(String(500), nullable=True)
    
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    school = relationship("School", back_populates="communication_sections")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.id:
            self.id = f"COMM-{str(uuid.uuid4().int)[:6]}"


class Achievement(Base):
    """Model for storing school achievements."""
    __tablename__ = "achievements"

    id = Column(String, primary_key=True, index=True)
    school_id = Column(String, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True)
    
    achievement_name = Column(String(255), nullable=False)
    achievement_level = Column(SQLEnum(AchievementLevel), nullable=False)
    date_of_achievement = Column(Date, nullable=False)
    description = Column(Text, nullable=True)  # Max 150 words
    achievement_images = Column(ARRAY(String), nullable=True)  # URLs to images stored in S3
    
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    school = relationship("School", back_populates="achievements")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.id:
            self.id = f"ACHV-{str(uuid.uuid4().int)[:6]}"


class PaymentRecord(Base):
    __tablename__ = "payment_records"

    id = Column(Integer, primary_key=True, index=True)
    worker_id = Column(String, ForeignKey("workers.id"), nullable=False, index=True)
    description = Column(String(1000), nullable=True)
    files = Column(JSON, nullable=True)  # Array of file URLs
    status = Column(String(50), nullable=False)  # Input field for status
    amount = Column(Float, nullable=True)  # Payment amount
    settlement_channel = Column(String(32), nullable=False, default="cash_offline")
    bank_account_id = Column(Integer, ForeignKey("bank_accounts.id"), nullable=True)
    payment_date = Column(DateTime, nullable=False, default=func.now())
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    # Relationships
    worker = relationship("Worker", back_populates="payment_records")
    bank_account = relationship("BankAccount")


class SchoolInfo(Base):
    """One-to-one: school profile info (admission path, vision, mission, about us)."""

    __tablename__ = "school_info"

    id = Column(Integer, primary_key=True, index=True)
    school_id = Column(
        String,
        ForeignKey("schools.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    admission_path = Column(Text, nullable=True)
    vision = Column(Text, nullable=True)
    mission = Column(Text, nullable=True)
    about_us = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    school = relationship("School", back_populates="school_info")


class SchoolClassFee(Base):
    """Per-school class fee: class name, admission fee, course fee, transport fee. Super admin and school can CRUD."""

    __tablename__ = "school_class_fees"

    id = Column(Integer, primary_key=True, index=True)
    school_id = Column(
        String, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True
    )
    class_name = Column(String(100), nullable=False)
    admission_fee = Column(Float, nullable=True, default=0)
    course_fee = Column(Float, nullable=True, default=0)
    transport_fee = Column(Float, nullable=True, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    school = relationship("School", back_populates="class_fees")

    __table_args__ = (
        UniqueConstraint(
            "school_id", "class_name", name="uq_school_class_fee_class_name"
        ),
    )


class SchoolTeamMember(Base):
    """Team members under a school. Fields: name, designation, member_story, profile_picture. Super admin and school can CRUD."""

    __tablename__ = "school_team_members"

    id = Column(Integer, primary_key=True, index=True)
    school_id = Column(
        String, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name = Column(String(200), nullable=False)
    designation = Column(String(200), nullable=True)
    phone_number = Column(String(20), nullable=True)
    email_id = Column(String(255), nullable=True)
    years_of_experience = Column(Integer, nullable=True)
    highest_qualification = Column(String(255), nullable=True)
    member_story = Column(Text, nullable=True)
    profile_picture = Column(String(500), nullable=True)  # URL
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    school = relationship("School", back_populates="team_members")


class ExcellentStudent(Base):
    """Excellent student list under school. Fields: school_id, school_name, gender, student_photo, phone_no, email, class_name, batch_of_student, secure_mark. School and admin can CRUD."""

    __tablename__ = "excellent_students"

    id = Column(Integer, primary_key=True, index=True)
    school_id = Column(
        String, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True
    )
    school_name = Column(String(200), nullable=True)
    gender = Column(String(20), nullable=True)
    student_photo = Column(String(500), nullable=True)  # URL (file upload)
    phone_no = Column(String(20), nullable=True)
    email = Column(String(255), nullable=True)
    class_name = Column(String(100), nullable=True)
    batch_of_student = Column(String(100), nullable=True)
    secure_mark = Column(Float, nullable=True)
    total_mark = Column(Float, nullable=True)
    secured_percentage = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    school = relationship("School", back_populates="excellent_students")


class ListedSchoolStudent(Base):
    """Listed school students - students displayed under a school (listing)."""

    __tablename__ = "listed_school_students"

    id = Column(Integer, primary_key=True, index=True)
    school_id = Column(String, ForeignKey("schools.id"), nullable=False, index=True)
    student_name = Column(String(200), nullable=False)
    gender = Column(String(20), nullable=True)
    phone_no = Column(String(20), nullable=True)
    email_id = Column(String(255), nullable=True)
    class_name = Column(String(100), nullable=True)
    batch_of_student = Column(String(100), nullable=True)
    secured_mark_in_percentage = Column(Float, nullable=True)
    profile_picture = Column(String(500), nullable=True)  # URL
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    # Relationships
    school = relationship("School", back_populates="listed_school_students")


class SchoolRating(Base):
    """User rating and feedback for a listed school. Any user can submit."""

    __tablename__ = "school_ratings"
    __table_args__ = (
        UniqueConstraint(
            "school_id",
            "mobile",
            "email_id",
            name="uq_school_rating_school_mobile_email",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    school_id = Column(
        String, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_name = Column(String(200), nullable=False)
    user_role = Column(String(50), nullable=False)  # visitor, student, parent
    mobile = Column(String(20), nullable=False)
    email_id = Column(String(255), nullable=False)
    feedback = Column(Text, nullable=True)
    rating = Column(Integer, nullable=False)  # 1 to 5
    created_at = Column(DateTime, server_default=func.now())

    school = relationship("School", back_populates="school_ratings")


class SupportPlusStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CANCELLED = "cancelled"


class SupportPlus(Base):
    """Support Plus: schools create records; admin updates status."""

    __tablename__ = "supportplus"

    id = Column(Integer, primary_key=True, index=True)
    school_id = Column(
        String, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True
    )
    looking_for = Column(String(255), nullable=False)
    whatsapp_number = Column(String(20), nullable=False)
    discussion_datetime = Column(DateTime(timezone=True), nullable=False)
    files = Column(ARRAY(String), nullable=True)  # list of file URLs (multiple files)
    message = Column(Text, nullable=True)
    status = Column(
        SQLEnum(SupportPlusStatus), default=SupportPlusStatus.PENDING, nullable=False
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    school = relationship("School", back_populates="support_plus")


class BusinessInquiry(Base):
    """Business inquiry from visitors (non-authenticated). Multiple schools, files, lists."""

    __tablename__ = "business_inquiry"

    id = Column(Integer, primary_key=True, index=True)
    school_ids = Column(
        PG_ARRAY(String), nullable=False
    )  # multiple school IDs (PG_ARRAY for .contains() in queries)
    guardian_name = Column(String(255), nullable=False)
    phone = Column(String(20), nullable=False)
    email = Column(String(255), nullable=False)
    location = Column(String(255), nullable=True)
    student_name = Column(String(255), nullable=True)
    standard_in_academic = Column(String(100), nullable=True)  # e.g. Class 10
    inquiry_for_class = Column(PG_ARRAY(String), nullable=True)  # multiple classes
    desire_to_know = Column(PG_ARRAY(String), nullable=True)  # list of strings
    files = Column(PG_ARRAY(String), nullable=True)  # uploaded file URLs
    message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class SchoolHoliday(Base):
    __tablename__ = "school_holidays"

    id = Column(Integer, primary_key=True, index=True)

    school_id = Column(String, ForeignKey("schools.id", ondelete="CASCADE"))
    holiday_master_id = Column(Integer, ForeignKey("holiday_master.id"))

    created_at = Column(DateTime, default=func.now())

    holiday = relationship("HolidayMaster")
