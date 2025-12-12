from sqlalchemy import Column, Integer, String, ForeignKey,Table,Time,UniqueConstraint,Date,Boolean,DateTime,Float,ARRAY,Text,JSON
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
    
    # Principal Information
    principal_name = Column(String, nullable=True)
    principal_designation = Column(String)
    principal_email = Column(String)
    principal_phone = Column(String(15))
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now())

    user = relationship("User", backref="school")
    teachers = relationship("Teacher", back_populates="school", cascade="all, delete-orphan")
    classes = relationship("Class", back_populates="school")
    subjects = relationship("Subject", back_populates="school")
    extra_activities = relationship("ExtraCurricularActivity", back_populates="school")
    sections = relationship("Section", back_populates="school")
    transports = relationship("Transport", back_populates="school")
    students = relationship("Student", back_populates="school")
    staff_members = relationship("Staff", back_populates="school", cascade="all, delete-orphan")
    timetables = relationship("Timetable", back_populates="school", cascade="all, delete")
    # timetable_periods = relationship("TimetablePeriod", back_populates="school")
    # school = relationship("School", back_populates="timetable_periods")
    school_margins = relationship("SchoolMarginConfiguration", back_populates="school", cascade="all, delete-orphan")
    transaction_history = relationship("TransactionHistory", back_populates="school", cascade="all, delete-orphan")
    exams = relationship("Exam", back_populates="school")
    exam_data = relationship("StudentExamData", back_populates="school")
    leave_requests = relationship("LeaveRequest", back_populates="school", cascade="all, delete")


    
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
    Column("school_class_subject_id", Integer, ForeignKey("school_classes_subjects.id", ondelete="SET NULL"), nullable=True)
)



class_extra_curricular = Table(
    "class_extra_curricular",
    Base.metadata,
    Column("class_id", Integer, ForeignKey("classes.id")),
    Column("activity_id", Integer, ForeignKey("extra_curricular_activities.id")),
    Column("school_id", String, ForeignKey("schools.id"))
)

class_assigned_teachers = Table(
    "class_assigned_teachers",
    Base.metadata,
    Column("class_id", Integer, ForeignKey("classes.id")),
    Column("teacher_id", String, ForeignKey("teachers.id")),
    Column("school_id", String, ForeignKey("schools.id"))
)
class_section = Table(
    "class_section",
    Base.metadata,
    Column("class_id", Integer, ForeignKey("classes.id")),
    Column("section_id", Integer, ForeignKey("sections.id")),
    Column("school_id", String, ForeignKey("schools.id"))
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
    __tablename__ = 'class_optional_subjects'
    
    class_id = Column(Integer, ForeignKey('classes.id', ondelete="CASCADE"), primary_key=True)
    subject_id = Column(Integer, ForeignKey('subjects.id', ondelete="CASCADE"), primary_key=True)
class ExtraCurricularActivity(Base):
    __tablename__ = "extra_curricular_activities"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100))
    school_id = Column(String, ForeignKey("schools.id"))
    
    school = relationship("School", back_populates="extra_activities")
    classes = relationship("Class", secondary=class_extra_curricular, back_populates="extra_curricular_activities")

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
    
    # Relationships
    school = relationship("School", back_populates="classes")
    students = relationship("Student", back_populates="classes")
    
    # Many-to-many relationships
    subjects = relationship("Subject", secondary=class_subjects,back_populates="classes")
    optional_subjects = relationship("Subject",secondary="class_optional_subjects",back_populates="classes")
    assigned_teachers = relationship("Teacher", secondary=class_assigned_teachers,back_populates="assigned_classes")
    extra_curricular_activities = relationship("ExtraCurricularActivity", secondary=class_extra_curricular,back_populates="classes")
    sections = relationship("Section", secondary=class_section,back_populates="classes")
    school_margins = relationship("SchoolMarginConfiguration", back_populates="class_")
    exams = relationship("Exam", back_populates="class_obj")
    timetables = relationship("Timetable", back_populates="class_")
    
    # Unique constraint to prevent duplicate class names within a school
    __table_args__ = (
        UniqueConstraint('name', 'school_id', name='uq_class_name_school'),
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
    pickup_stops = relationship("PickupStop", back_populates="transport", cascade="all, delete-orphan")
    drop_stops = relationship("DropStop", back_populates="transport", cascade="all, delete-orphan")

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
    is_today_present = Column(Boolean, default=False, nullable=False)

    __table_args__ = (
        UniqueConstraint('student_id','date', name='uq_student_attendance'),
        UniqueConstraint('teachers_id','date', name='uq_teacher_attendance'),
        UniqueConstraint('staff_id','date', name='uq_staff_attendance'),
    )
    def update_today_status(self):
        """Automatically set is_today_present based on whether date == today."""
        self.is_today_present = (self.date == date.today())

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
    days = relationship("TimetableDay", back_populates="timetable", cascade="all, delete-orphan")
    class_ = relationship("Class", back_populates="timetables")
    section = relationship("Section", back_populates="timetables")

    __table_args__ = (
        UniqueConstraint("school_id", "class_id", "section_id", name="uq_timetable_class_section"),
    )

class TimetableDay(Base):
    __tablename__ = "timetable_days"

    id = Column(Integer, primary_key=True)
    timetable_id = Column(Integer, ForeignKey("timetables.id"), nullable=False)
    day = Column(SQLEnum(WeekDay, name="weekday"), nullable=False)

    timetable = relationship("Timetable", back_populates="days")
    periods = relationship("TimetablePeriod", back_populates="day", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("timetable_id", "day", name="uq_timetable_day"),
    )
      
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
    school_id = Column(String,ForeignKey("schools.id"), nullable=False)
    class_id = Column(Integer,ForeignKey("classes.id"), nullable=False)
    credit_configuration_id = Column(Integer, ForeignKey("credit_configuration.id"))
    margin_value = Column(Integer, nullable=False)
    
    school= relationship("School", back_populates="school_margins")
    class_ = relationship("Class", back_populates="school_margins")
    credit_configuration = relationship("CreditConfiguration", back_populates="school_margins")

class TransactionHistory(Base):
    __tablename__ = "transaction_history"

    id = Column(Integer, primary_key=True, index=True)
    school_id = Column(String, ForeignKey("schools.id"), nullable=False)
    amount = Column(Float, nullable=False)
    transaction_id = Column(String, nullable=False, unique=True)
    order_id = Column(String, nullable=False)
    status = Column(String, nullable=False, default="SUCCESS")
    created_at = Column(DateTime(timezone=True), default=func.now())
    
    school= relationship("School", back_populates="transaction_history")

exam_sections = Table(
    "exam_sections",
    Base.metadata,
    Column("exam_id", String, ForeignKey("exams.id"), primary_key=True),
    Column("section_id", Integer, ForeignKey("sections.id"), primary_key=True),
)

class Exam(Base):
    __tablename__ = "exams"

    id = Column(String, primary_key=True)
    school_id = Column(String, ForeignKey("schools.id"), nullable=False)
    class_id = Column(Integer, ForeignKey("classes.id"), nullable=False)
    chapters = Column(ARRAY(Integer), nullable=False)
    exam_type = Column(SQLEnum(ExamTypeEnum), nullable=False)
    no_of_questions = Column(Integer, nullable=False)
    question_time = Column(Integer, nullable=True)
    pass_percentage = Column(Integer, nullable=False)
    exam_activation_date = Column(DateTime, nullable=False)
    inactive_date = Column(DateTime, nullable=True)
    max_repeat = Column(Integer, nullable=False, default=1)
    status = Column(SQLEnum(ExamStatusEnum), nullable=False, default=ExamStatusEnum.PENDING)
    no_students_appeared = Column(Integer, default=0)
    created_by = Column(String, ForeignKey("teachers.id"), nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    is_published = Column(Boolean, default=False)

    # Relationships
    school = relationship("School", back_populates="exams")
    teacher = relationship("Teacher", back_populates="created_exams")
    class_obj = relationship("Class", back_populates="exams")
    sections = relationship("Section", secondary=exam_sections, back_populates="exams")
    mcqs = relationship("McqBank", back_populates="exam")
    student_exam_data = relationship("StudentExamData", back_populates="exam")


    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.id:
            self.id = f"EXM-{str(uuid.uuid4().int)[:6]}"


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

class McqBank(Base):
    __tablename__ = "mcq_bank"

    id = Column(Integer, primary_key=True, index=True)
    exam_id = Column(String, ForeignKey("exams.id", ondelete="CASCADE"))
    question = Column(Text, nullable=False)
    mcq_type = Column(String(1), nullable=False, default="1")  # '1' = Single, '2' = Multiple
    image = Column(String, nullable=True)

    option_a = Column(String(100), nullable=False)
    option_b = Column(String(100), nullable=False)
    option_c = Column(String(100), nullable=False)
    option_d = Column(String(100), nullable=False)

    # For storing multiple correct answers → ARRAY of strings
    correct_option = Column(ARRAY(String), nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationship with Exam
    exam = relationship("Exam", back_populates="mcqs")

class ExamStatus(str,Enum):
    pass_ = "pass"
    fail = "fail"


class StudentExamData(Base):
    __tablename__ = "student_exam_data"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    school_id = Column(String, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False)
    exam_id = Column(String, ForeignKey("exams.id", ondelete="CASCADE"), nullable=False)
    attempt_no = Column(Integer, default=1)
    answers = Column(JSON, nullable=False)
    result = Column(Float, nullable=True)
    status = Column(SQLEnum(ExamStatus), nullable=True)
    appeared_count = Column(Integer, default=0)
    class_rank = Column(Integer, nullable=True)
    submitted_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships (optional, if you want ORM navigation)
    student = relationship("Student", back_populates="exam_data")
    school = relationship("School", back_populates="exam_data")
    exam = relationship("Exam", back_populates="student_exam_data")

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
    school_id = Column(String, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False)
    teacher_id = Column(String, ForeignKey("teachers.id", ondelete="CASCADE"), nullable=True)
    student_id = Column(Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=True)
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
        "AssignmentTask",
        back_populates="assignment",
        cascade="all, delete-orphan"
    )

    # Relationship to assigned students
    assigned_students = relationship(
        "AssignmentStudent",
        back_populates="assignment",
        cascade="all, delete-orphan"
    )


# ---------------- ASSIGNMENT TASKS ----------------
class AssignmentTask(Base):
    __tablename__ = "assignment_tasks"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    file = Column(String(255), nullable=True)

    assignment_id = Column(Integer, ForeignKey("home_assignments.id", ondelete="CASCADE"))
    assignment = relationship("HomeAssignment", back_populates="tasks")

    # Each student's completion status for this task
    student_task_statuses = relationship(
        "StudentTaskStatus",
        back_populates="task",
        cascade="all, delete-orphan"
    )


# ---------------- ASSIGNED STUDENTS ----------------
class AssignmentStudent(Base):
    __tablename__ = "assignment_students"

    id = Column(Integer, primary_key=True, index=True)
    assignment_id = Column(Integer, ForeignKey("home_assignments.id", ondelete="CASCADE"))
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
        cascade="all, delete-orphan"
    )


# ---------------- STUDENT TASK STATUS ----------------
class StudentTaskStatus(Base):
    __tablename__ = "student_task_statuses"

    id = Column(Integer, primary_key=True, index=True)
    assignment_student_id = Column(Integer, ForeignKey("assignment_students.id", ondelete="CASCADE"))
    task_id = Column(Integer, ForeignKey("assignment_tasks.id", ondelete="CASCADE"))
    student_id = Column(Integer, ForeignKey("students.id", ondelete="CASCADE"))

    status = Column(SQLEnum(TaskStatus), default=TaskStatus.PENDING)
    completed_at = Column(DateTime, nullable=True)

    # Relationships
    assignment_student = relationship("AssignmentStudent", back_populates="student_tasks")
    task = relationship("AssignmentTask", back_populates="student_task_statuses")
    student = relationship("Student", back_populates="student_task_statuses")