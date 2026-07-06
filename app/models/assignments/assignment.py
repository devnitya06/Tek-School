from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime, Float, Enum, Text, UniqueConstraint
from sqlalchemy.types import TypeDecorator
from sqlalchemy.orm import relationship, synonym
from sqlalchemy.dialects.postgresql import ARRAY
from app.db.session import Base
from datetime import datetime
import enum

# --- Enums from assignment_activities and assignments modules ---

class AssignmentStatus(str, enum.Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    UNPUBLISHED = "unpublished"
    # Merged from ActivityStatus
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"

class AssignmentType(str, enum.Enum):
    ACADEMIC = "Academic"
    GENERAL_KNOWLEDGE = "General Knowledge"
    HOMEWORK = "homework" # From AssignmentActivity
    CLASSWORK = "classwork" # From AssignmentActivity
    TEST = "test" # From AssignmentActivity
    PROJECT = "project" # From AssignmentActivity

class TaskStatus(str, enum.Enum): # From AssignmentActivityTaskStatus
    PENDING = "pending"
    COMPLETED = "completed"


class StringEnum(TypeDecorator):
    impl = String
    cache_ok = True

    def __init__(self, enum_cls, *args, **kwargs):
        self.enum_cls = enum_cls
        super().__init__(*args, **kwargs)

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, enum.Enum):
            return value.value
        return value

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        try:
            return self.enum_cls(value)
        except ValueError:
            return value

class StudentImprovementCategory(str, enum.Enum):
    MORAL_DEVELOPMENT = "Moral Development"
    ENHANCE_THINKING = "Enhance Thinking"
    KNOWLEDGE_ENHANCEMENT = "Knowledge Enhancement"

class DoubtStatus(str, enum.Enum): # Unified DoubtStatus
    OPEN = "Open"
    RESOLVED = "Resolved"

class ReportCategory(str, enum.Enum): # Unified ReportCategory
    INAPPROPRIATE_CONTENT = "Inappropriate Content"
    PLAGIARISM = "Plagiarism"
    OTHER = "Other"
    # Merged from AssignmentActivityReport
    INAPPROPRIATE = "inappropriate"
    INCORRECT = "incorrect"
    MISLEADING = "misleading"
    DUPLICATE = "duplicate"

class ReportStatus(str, enum.Enum): # From AssignmentActivityReport
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"

# --- Core Assignment Model ---

class Assignment(Base):
    __tablename__ = "assignments"

    id = Column(Integer, primary_key=True, index=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True) # Can be null for self-signed teachers for now
    created_by_teacher_id = Column(String, ForeignKey("teachers.id", ondelete="SET NULL"), nullable=True) # From AssignmentActivity
    created_by_self_signed_teacher_id = Column(Integer, ForeignKey("self_signed_teachers.id", ondelete="SET NULL"), nullable=True) # From AssignmentActivity
    teacher_id = synonym("created_by_teacher_id")
    
    status = Column(StringEnum(AssignmentStatus), default=AssignmentStatus.DRAFT, nullable=False)

    # Core assignment details (from existing Assignment)
    board = Column(String, nullable=False)
    class_name = Column(String, nullable=False)
    subject = Column(String, nullable=False)
    chapter_number = Column(Integer, nullable=False)
    sub_chapter = Column(String, nullable=True)
    topic_title = Column(String, nullable=False)
    chapter_tagline = Column(String, nullable=True)
    original_content = Column(Text, nullable=True)
    summarized_content = Column(Text, nullable=True)

    # From AssignmentActivity
    activity_type = Column(StringEnum(AssignmentType), nullable=False, default=AssignmentType.ACADEMIC)
    class_id = Column(Integer, ForeignKey("classes.id", ondelete="SET NULL"), nullable=True)
    subject_id = Column(Integer, ForeignKey("subjects.id", ondelete="SET NULL"), nullable=True)
    chapter_id = Column(Integer, ForeignKey("chapters.id", ondelete="SET NULL"), nullable=True)
    chapter_ids = Column(ARRAY(Integer), nullable=True)

    # Denormalized teacher and school info for display
    teacher_name = Column(String, nullable=True)
    school_name = Column(String, nullable=True)
    school_address = Column(String, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    published_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    created_by_user = relationship("User", foreign_keys=[created_by_user_id])
    created_by_teacher = relationship("Teacher", foreign_keys=[created_by_teacher_id], back_populates="assignments")
    created_by_self_signed_teacher = relationship("SelfSignedTeacher", foreign_keys=[created_by_self_signed_teacher_id])

    key_points = relationship("AssignmentKeyPoint", back_populates="assignment", cascade="all, delete-orphan")
    questions = relationship("AssignmentQuestion", back_populates="assignment", cascade="all, delete-orphan")
    images = relationship("AssignmentImage", back_populates="assignment", cascade="all, delete-orphan")
    pdfs = relationship("AssignmentPDF", back_populates="assignment", cascade="all, delete-orphan")
    video_links = relationship("AssignmentVideoLink", back_populates="assignment", cascade="all, delete-orphan")
    media_banners = relationship("AssignmentMediaBanner", back_populates="assignment", cascade="all, delete-orphan")
    publish_config = relationship("PublishConfiguration", back_populates="assignment", uselist=False, cascade="all, delete-orphan")
    attempts = relationship("StudentAssignmentAttempt", back_populates="assignment", cascade="all, delete-orphan")
    feedback = relationship("ChapterFeedback", back_populates="assignment", cascade="all, delete-orphan")
    views = relationship("AssignmentView", back_populates="assignment", cascade="all, delete-orphan")

    # Relationships from AssignmentActivity
    tasks = relationship("AssignmentActivityTask", back_populates="assignment", cascade="all, delete-orphan")
    assigned_students_progress = relationship("StudentAssignmentProgress", back_populates="assignment", cascade="all, delete-orphan")
    
    # Unified doubts and reports
    doubts = relationship("AssignmentDoubt", back_populates="assignment", cascade="all, delete-orphan")
    reports = relationship("AssignmentReport", back_populates="assignment", cascade="all, delete-orphan")

class FavoriteTeacher(Base):
    __tablename__ = "favorite_teachers"

    id = Column(Integer, primary_key=True, index=True)
    student_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    teacher_id = Column(String, nullable=False)
    teacher_type = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("student_user_id", "teacher_id", name="uq_student_teacher_favorite"),
    )

# --- New Models merged from AssignmentActivity ---

class AssignmentActivityTask(Base):
    __tablename__ = "assignments_tasks" # Avoid collision with other app tables

    id = Column(Integer, primary_key=True, index=True)
    assignment_id = Column(Integer, ForeignKey("assignments.id", ondelete="CASCADE"), nullable=False) # Link to Assignment
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    file = Column(String(255), nullable=True)

    assignment = relationship("Assignment", back_populates="tasks")
    student_task_statuses = relationship("AssignmentActivityTaskStatus", back_populates="task", cascade="all, delete-orphan")


class StudentAssignmentProgress(Base):
    __tablename__ = "assignments_student_assignment_progress" # Avoid collision with other app tables

    id = Column(Integer, primary_key=True, index=True)
    assignment_id = Column(Integer, ForeignKey("assignments.id", ondelete="CASCADE"), nullable=False) # Link to Assignment
    student_id = Column(Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=True)
    self_signed_student_id = Column(Integer, ForeignKey("self_signed_students.id", ondelete="CASCADE"), nullable=True)
    assigned_date = Column(DateTime, default=datetime.utcnow)
    status = Column(StringEnum(AssignmentStatus), default=AssignmentStatus.IN_PROGRESS, nullable=False) # Overall progress

    assignment = relationship("Assignment", back_populates="assigned_students_progress")
    student_obj = relationship("Student") # Renamed to avoid conflict
    self_signed_student_obj = relationship("SelfSignedStudent") # Renamed to avoid conflict
    task_statuses = relationship("AssignmentActivityTaskStatus", back_populates="student_progress", cascade="all, delete-orphan")


class AssignmentActivityTaskStatus(Base):
    __tablename__ = "assignments_student_task_statuses" # Avoid collision with other app tables

    id = Column(Integer, primary_key=True, index=True)
    student_assignment_progress_id = Column(
        Integer,
        ForeignKey("assignments_student_assignment_progress.id", ondelete="CASCADE"),
        nullable=False,
    )
    task_id = Column(Integer, ForeignKey("assignments_tasks.id", ondelete="CASCADE"), nullable=False)
    student_id = Column(Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=True) # Redundant but kept for now
    status = Column(Enum(TaskStatus), default=TaskStatus.PENDING, nullable=False)
    completed_at = Column(DateTime, nullable=True)

    student_progress = relationship("StudentAssignmentProgress", back_populates="task_statuses")
    task = relationship("AssignmentActivityTask", back_populates="student_task_statuses")
    student_obj = relationship("Student") # Redundant but kept for now

# --- Updated Doubt and Report Models (unified) ---

class AssignmentKeyPoint(Base):
    __tablename__ = "assignment_key_points"

    id = Column(Integer, primary_key=True, index=True)
    assignment_id = Column(Integer, ForeignKey("assignments.id"), nullable=False)
    step_number = Column(Integer, nullable=False)
    text = Column(String, nullable=False)
    image_url = Column(String, nullable=True)  # Optional S3 URL for key point image

    assignment = relationship("Assignment", back_populates="key_points")


class AssignmentQuestion(Base):
    __tablename__ = "assignment_questions"

    id = Column(Integer, primary_key=True, index=True)
    assignment_id = Column(Integer, ForeignKey("assignments.id"), nullable=False)
    question_number = Column(Integer, nullable=False)
    question_text = Column(Text, nullable=False)
    option_a = Column(Text, nullable=False)
    option_b = Column(Text, nullable=False)
    option_c = Column(Text, nullable=False)
    option_d = Column(Text, nullable=False)
    correct_option = Column(String(1), nullable=False) # 'A', 'B', 'C', 'D'
    solution_explanation = Column(Text, nullable=True)

    assignment = relationship("Assignment", back_populates="questions")
    doubts = relationship("AssignmentDoubt", back_populates="question", cascade="all, delete-orphan")


class AssignmentImage(Base):
    __tablename__ = "assignment_images"

    id = Column(Integer, primary_key=True, index=True)
    assignment_id = Column(Integer, ForeignKey("assignments.id"), nullable=False)
    url = Column(String, nullable=False)

    assignment = relationship("Assignment", back_populates="images")

class AssignmentPDF(Base):
    __tablename__ = "assignment_pdfs"

    id = Column(Integer, primary_key=True, index=True)
    assignment_id = Column(Integer, ForeignKey("assignments.id"), nullable=False)
    url = Column(String, nullable=False)

    assignment = relationship("Assignment", back_populates="pdfs")

class AssignmentVideoLink(Base):
    __tablename__ = "assignment_video_links"

    id = Column(Integer, primary_key=True, index=True)
    assignment_id = Column(Integer, ForeignKey("assignments.id"), nullable=False)
    url = Column(String, nullable=False) # Only URLs allowed

    assignment = relationship("Assignment", back_populates="video_links")

class AssignmentMediaBanner(Base):
    __tablename__ = "assignment_media_banners"

    id = Column(Integer, primary_key=True, index=True)
    assignment_id = Column(Integer, ForeignKey("assignments.id"), nullable=False)
    image_url = Column(String, nullable=False)
    label = Column(String, nullable=False)
    link = Column(String, nullable=True)
    display_order = Column(Integer, nullable=False, default=0)

    assignment = relationship("Assignment", back_populates="media_banners")


class PublishConfiguration(Base):
    __tablename__ = "publish_configurations"

    id = Column(Integer, primary_key=True, index=True)
    assignment_id = Column(Integer, ForeignKey("assignments.id"), unique=True, nullable=False)
    assignment_type = Column(Enum(AssignmentType), nullable=False)
    improvement_categories = Column(Text, nullable=False) # Store as comma-separated string or JSON string
    reward_amount_override = Column(Float, nullable=True) # Optional override

    assignment = relationship("Assignment", back_populates="publish_config")


class StudentAssignmentAttempt(Base):
    __tablename__ = "student_assignment_attempts"

    id = Column(Integer, primary_key=True, index=True)
    student_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    assignment_id = Column(Integer, ForeignKey("assignments.id"), nullable=False)
    attempt_number = Column(Integer, nullable=False)
    submitted_answers = Column(Text, nullable=True) # JSON string of submitted answers
    score = Column(Float, nullable=False, default=0.0)
    time_taken_seconds = Column(Integer, nullable=True)
    submission_date = Column(DateTime, default=datetime.utcnow)

    student_user = relationship("User", foreign_keys=[student_user_id])
    assignment = relationship("Assignment", back_populates="attempts")


class ChapterFeedback(Base):
    __tablename__ = "chapter_feedback"

    id = Column(Integer, primary_key=True, index=True)
    student_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    assignment_id = Column(Integer, ForeignKey("assignments.id"), nullable=False)
    is_helpful = Column(Boolean, nullable=False) # True for "Yes", False for "No"
    created_at = Column(DateTime, default=datetime.utcnow)

    student_user = relationship("User", foreign_keys=[student_user_id])
    assignment = relationship("Assignment", back_populates="feedback")


class TeacherRating(Base):
    __tablename__ = "teacher_ratings"

    id = Column(Integer, primary_key=True, index=True)
    teacher_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    student_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    rating = Column(Integer, nullable=False) # 1-5 stars
    created_at = Column(DateTime, default=datetime.utcnow)

    teacher_user = relationship("User", foreign_keys=[teacher_user_id])
    student_user = relationship("User", foreign_keys=[student_user_id])
    teacher = relationship("Teacher", back_populates="ratings", primaryjoin="Teacher.user_id == foreign(TeacherRating.teacher_user_id)")


class AssignmentView(Base):
    __tablename__ = "assignment_views"

    id = Column(Integer, primary_key=True, index=True)
    assignment_id = Column(Integer, ForeignKey("assignments.id"), nullable=False)
    viewer_user_id = Column(Integer, ForeignKey("users.id"), nullable=False) # Could be student or teacher
    viewed_at = Column(DateTime, default=datetime.utcnow)

    assignment = relationship("Assignment", back_populates="views")
    viewer = relationship("User", foreign_keys=[viewer_user_id])


class AssignmentDoubt(Base): # Unified Doubt model
    __tablename__ = "assignment_doubts"

    id = Column(Integer, primary_key=True, index=True)
    assignment_id = Column(Integer, ForeignKey("assignments.id"), nullable=False)
    student_user_id = Column(Integer, ForeignKey("users.id"), nullable=True) # Can be null for self-signed students
    self_signed_student_id = Column(Integer, ForeignKey("self_signed_students.id", ondelete="CASCADE"), nullable=True) # From AssignmentActivityDoubt
    question_id = Column(Integer, ForeignKey("assignment_questions.id"), nullable=True)
    doubt_text = Column(Text, nullable=False)
    doubt_summary = Column(String(500), nullable=True) # From AssignmentActivityDoubt
    status = Column(Enum(DoubtStatus), default=DoubtStatus.OPEN, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)
    
    number_of_attempts = Column(Integer, default=0) # From AssignmentActivityDoubt
    last_attempt_date = Column(DateTime, nullable=True) # From AssignmentActivityDoubt

    assignment = relationship("Assignment", back_populates="doubts")
    student_user = relationship("User", foreign_keys=[student_user_id])
    self_signed_student = relationship("SelfSignedStudent", foreign_keys=[self_signed_student_id])
    question = relationship("AssignmentQuestion", back_populates="doubts")
    replies = relationship("DoubtReply", back_populates="doubt", cascade="all, delete-orphan")


class DoubtReply(Base): # Unified DoubtReply model
    __tablename__ = "doubt_replies"

    id = Column(Integer, primary_key=True, index=True)
    doubt_id = Column(Integer, ForeignKey("assignment_doubts.id"), nullable=False)
    teacher_user_id = Column(Integer, ForeignKey("users.id"), nullable=True) # Can be null for self-signed teachers
    self_signed_teacher_id = Column(Integer, ForeignKey("self_signed_teachers.id", ondelete="SET NULL"), nullable=True) # From AssignmentActivityDoubtReply
    reply_text = Column(Text, nullable=False)
    file_url = Column(String(255), nullable=True) # From AssignmentActivityDoubtReply
    step_solutions = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    doubt = relationship("AssignmentDoubt", back_populates="replies")
    teacher_user = relationship("User", foreign_keys=[teacher_user_id])
    self_signed_teacher = relationship("SelfSignedTeacher", foreign_keys=[self_signed_teacher_id])


class AssignmentReport(Base): # Unified Report model
    __tablename__ = "assignment_reports"

    id = Column(Integer, primary_key=True, index=True)
    assignment_id = Column(Integer, ForeignKey("assignments.id"), nullable=False)
    student_user_id = Column(Integer, ForeignKey("users.id"), nullable=True) # Can be null for self-signed students
    self_signed_student_id = Column(Integer, ForeignKey("self_signed_students.id", ondelete="CASCADE"), nullable=True) # From AssignmentActivityReport
    category = Column(Enum(ReportCategory), nullable=False)
    reason = Column(Text, nullable=False)
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # From AssignmentActivityReport
    additional_comments = Column(Text, nullable=True)
    status = Column(Enum(ReportStatus), default=ReportStatus.OPEN, nullable=False)
    viewed_by_teacher = Column(DateTime, nullable=True)
    viewed_by_admin = Column(DateTime, nullable=True)
    admin_notes = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


    assignment = relationship("Assignment", back_populates="reports")
    student_user = relationship("User", foreign_keys=[student_user_id])
    self_signed_student = relationship("SelfSignedStudent", foreign_keys=[self_signed_student_id])
