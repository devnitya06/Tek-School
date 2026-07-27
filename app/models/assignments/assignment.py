from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime, Float, Enum, Text, Date, JSON
from sqlalchemy.orm import relationship
from app.db.session import Base
from datetime import datetime
import enum

class AssignmentStatus(str, enum.Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    UNPUBLISHED = "unpublished"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"

class AssignmentType(str, enum.Enum):
    ACADEMIC = "Academic"
    GENERAL_KNOWLEDGE = "General Knowledge"

class StudentImprovementCategory(str, enum.Enum):
    MORAL_DEVELOPMENT = "Moral Development"
    ENHANCE_THINKING = "Enhance Thinking"
    KNOWLEDGE_ENHANCEMENT = "Knowledge Enhancement"

class Assignment(Base):
    __tablename__ = "assignments"

    id = Column(Integer, primary_key=True, index=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_by_teacher_id = Column(String, ForeignKey("teachers.id"), nullable=True)
    created_by_self_signed_teacher_id = Column(Integer, ForeignKey("self_signed_teachers.id"), nullable=True)
    status = Column(
        Enum(AssignmentStatus, values_callable=lambda enum_cls: [e.value for e in enum_cls]),
        default=AssignmentStatus.DRAFT,
        nullable=False,
    )

    # Core assignment details
    board = Column(String, nullable=False)
    class_name = Column(String, nullable=False) # Renamed to avoid conflict with 'class' keyword
    subject = Column(String, nullable=False)
    title = Column(String, nullable=True)
    chapter_number = Column(Integer, nullable=False)
    chapter_name = Column(String, nullable=True)
    chapter_description = Column(Text, nullable=True)
    sub_chapters = Column(JSON, nullable=True)
    chapter_tagline = Column(String, nullable=True)
    sub_chapter = Column(String, nullable=True)
    topic_title = Column(String, nullable=True)
    tuition_setup_id = Column(String, nullable=True)
    tuition_date = Column(Date, nullable=True)
    total_file_size_bytes = Column(Integer, nullable=False, default=0)
    total_file_count = Column(Integer, nullable=False, default=0)

    # Denormalized teacher and school info for display
    teacher_name = Column(String, nullable=True)
    school_name = Column(String, nullable=True)
    school_address = Column(String, nullable=True)

    # Computed/aggregated fields (optional, can be done via relationships or queries)
    # total_views = Column(Integer, default=0)
    # doubts_count = Column(Integer, default=0)
    # made_ideal_count = Column(Integer, default=0)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    published_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    created_by_user = relationship("User")
    created_by_teacher = relationship(
        "Teacher",
        foreign_keys=[created_by_teacher_id],
        primaryjoin="Assignment.created_by_teacher_id == Teacher.id",
        back_populates="assignments",
    )
    created_by_self_signed_teacher = relationship(
        "SelfSignedTeacher",
        foreign_keys=[created_by_self_signed_teacher_id],
        primaryjoin="Assignment.created_by_self_signed_teacher_id == SelfSignedTeacher.id",
        back_populates="assignments",
    )
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
    doubts = relationship("AssignmentDoubt", back_populates="assignment", cascade="all, delete-orphan")
    reports = relationship("AssignmentReport", back_populates="assignment", cascade="all, delete-orphan")


class AssignmentKeyPoint(Base):
    __tablename__ = "assignment_key_points"

    id = Column(Integer, primary_key=True, index=True)
    assignment_id = Column(Integer, ForeignKey("assignments.id"), nullable=False)
    step_number = Column(Integer, nullable=False)
    text = Column(String, nullable=False)

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
    file_name = Column(String, nullable=True)
    file_type = Column(String, nullable=True)
    usage = Column(String, nullable=True)
    sub_chapter_name = Column(String, nullable=True)
    step_number = Column(Integer, nullable=True)
    file_size_bytes = Column(Integer, nullable=True)
    s3_key = Column(String, nullable=True)

    assignment = relationship("Assignment", back_populates="images")

class AssignmentPDF(Base):
    __tablename__ = "assignment_pdfs"

    id = Column(Integer, primary_key=True, index=True)
    assignment_id = Column(Integer, ForeignKey("assignments.id"), nullable=False)
    url = Column(String, nullable=False)
    file_name = Column(String, nullable=True)
    file_type = Column(String, nullable=True)
    usage = Column(String, nullable=True)
    sub_chapter_name = Column(String, nullable=True)
    step_number = Column(Integer, nullable=True)
    file_size_bytes = Column(Integer, nullable=True)
    s3_key = Column(String, nullable=True)

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


class StudentAssignmentProgress(Base):
    __tablename__ = "student_assignment_progress"

    id = Column(Integer, primary_key=True, index=True)
    student_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    assignment_id = Column(Integer, ForeignKey("assignments.id"), nullable=False)
    status = Column(
        Enum(AssignmentStatus, values_callable=lambda enum_cls: [e.value for e in enum_cls]),
        default=AssignmentStatus.DRAFT,
        nullable=False,
    )
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    student_user = relationship("User", foreign_keys=[student_user_id])


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
    teacher = relationship(
        "Teacher",
        primaryjoin="Teacher.user_id == TeacherRating.teacher_user_id",
        foreign_keys=[teacher_user_id],
        viewonly=True,
    )


class AssignmentView(Base):
    __tablename__ = "assignment_views"

    id = Column(Integer, primary_key=True, index=True)
    assignment_id = Column(Integer, ForeignKey("assignments.id"), nullable=False)
    viewer_user_id = Column(Integer, ForeignKey("users.id"), nullable=False) # Could be student or teacher
    viewed_at = Column(DateTime, default=datetime.utcnow)

    assignment = relationship("Assignment", back_populates="views")
    viewer = relationship("User", foreign_keys=[viewer_user_id])


class DoubtStatus(str, enum.Enum):
    OPEN = "Open"
    RESOLVED = "Resolved"

class AssignmentDoubt(Base):
    __tablename__ = "assignment_doubts"

    id = Column(Integer, primary_key=True, index=True)
    assignment_id = Column(Integer, ForeignKey("assignments.id"), nullable=False)
    student_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    self_signed_student_id = Column(Integer, ForeignKey("self_signed_students.id", ondelete="CASCADE"), nullable=True)
    question_id = Column(Integer, ForeignKey("assignment_questions.id"), nullable=True) # Optional, for question-specific doubts
    doubt_text = Column(Text, nullable=False)
    status = Column(Enum(DoubtStatus), default=DoubtStatus.OPEN, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)

    assignment = relationship("Assignment", back_populates="doubts")
    student_user = relationship("User", foreign_keys=[student_user_id])
    self_signed_student = relationship("SelfSignedStudent", foreign_keys=[self_signed_student_id])
    question = relationship("AssignmentQuestion", back_populates="doubts")
    replies = relationship("DoubtReply", back_populates="doubt", cascade="all, delete-orphan")


class DoubtReply(Base):
    __tablename__ = "doubt_replies"

    id = Column(Integer, primary_key=True, index=True)
    doubt_id = Column(Integer, ForeignKey("assignment_doubts.id"), nullable=False)
    teacher_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    self_signed_teacher_id = Column(Integer, ForeignKey("self_signed_teachers.id", ondelete="SET NULL"), nullable=True)
    reply_text = Column(Text, nullable=False)
    file_url = Column(String(255), nullable=True) # From AssignmentActivityDoubtReply
    step_solutions = Column(Text, nullable=True) # JSON string of step-by-step solutions
    created_at = Column(DateTime, default=datetime.utcnow)

    doubt = relationship("AssignmentDoubt", back_populates="replies")
    teacher_user = relationship("User", foreign_keys=[teacher_user_id])
    self_signed_teacher = relationship("SelfSignedTeacher", foreign_keys=[self_signed_teacher_id])

    @property
    def sender_type(self):
        if self.teacher_user_id is not None:
            return "teacher"
        if self.self_signed_teacher_id is not None:
            return "self_signed_teacher"
        if self.doubt is not None and self.doubt.student_user_id is not None:
            return "student"
        if self.doubt is not None and self.doubt.self_signed_student_id is not None:
            return "self_signed_student"
        return "student"


class ReportCategory(str, enum.Enum):
    INAPPROPRIATE_CONTENT = "Inappropriate Content"
    PLAGIARISM = "Plagiarism"
    OTHER = "Other"

class ReportStatus(str, enum.Enum):
    PENDING = "pending"
    REVIEWED = "reviewed"
    RESOLVED = "resolved"

class TaskStatus(str, enum.Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"

class FavoriteTeacher(Base):
    __tablename__ = "favorite_teachers"

    id = Column(Integer, primary_key=True, index=True)
    student_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    teacher_id = Column(String, nullable=False)
    teacher_type = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class AssignmentReport(Base):
    __tablename__ = "assignment_reports"

    id = Column(Integer, primary_key=True, index=True)
    assignment_id = Column(Integer, ForeignKey("assignments.id"), nullable=False)
    student_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    category = Column(Enum(ReportCategory), nullable=False)
    reason = Column(Text, nullable=False)
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    assignment = relationship("Assignment", back_populates="reports")
    student_user = relationship("User", foreign_keys=[student_user_id])
