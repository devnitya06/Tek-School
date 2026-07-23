from datetime import datetime
from enum import Enum
import secrets
import string

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import relationship
from sqlalchemy import Enum as SQLEnum

from app.db.session import Base


class TuitionBatchStatus(str, Enum):
    DRAFT = "draft"
    PENDING = "pending"
    APPROVED = "approved"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class EnrollmentStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    REMOVED = "removed"


class MeetingProvider(str, Enum):
    GOOGLE_MEET = "google_meet"
    ZOOM = "zoom"


class PaymentStatus(str, Enum):
    PENDING = "pending"
    PAID = "paid"
    PARTIAL = "partial"
    REFUNDED = "refunded"


class SettlementStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    PAID = "paid"


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class LessonPlanStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"


def generate_short_id(prefix: str = "ID", length: int = 8) -> str:
    alphabet = string.ascii_uppercase + string.digits
    suffix = "".join(secrets.choice(alphabet) for _ in range(length))
    return f"{prefix}{suffix}"


class TuitionBatch(Base):
    __tablename__ = "tuition_batches"

    id = Column(String, primary_key=True, default=generate_short_id)
    school_id = Column(String, ForeignKey("schools.id"), nullable=True)
    teacher_id = Column(String, ForeignKey("teachers.id"), nullable=True)
    self_signed_teacher_id = Column(Integer, ForeignKey("self_signed_teachers.id"), nullable=True)
    teacher_type = Column(String(30), nullable=False, default="teacher")
    board_id = Column(String(50), nullable=False)
    class_id = Column(Integer, ForeignKey("classes.id"), nullable=False)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False)
    batch_name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    language = Column(String(100), nullable=True)
    meeting_provider = Column(SQLEnum(MeetingProvider), nullable=False, default=MeetingProvider.GOOGLE_MEET)
    meeting_link = Column(Text, nullable=True)
    batch_capacity = Column(Integer, nullable=False, default=30)
    tuition_fee = Column(Numeric(12, 2), nullable=False, default=0)
    study_material_fee = Column(Numeric(12, 2), nullable=False, default=0)
    discount = Column(Numeric(12, 2), nullable=False, default=0)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    days_of_week = Column(ARRAY(String), nullable=True)
    start_time = Column(Time, nullable=True)
    end_time = Column(Time, nullable=True)
    batch_status = Column(SQLEnum(TuitionBatchStatus), nullable=False, default=TuitionBatchStatus.DRAFT)
    is_deleted = Column(Boolean, nullable=False, default=False)
    deleted_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    updated_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    __table_args__ = (
        UniqueConstraint("batch_name", "school_id", name="uq_tuition_batch_name_school"),
        Index("ix_tuition_batches_status", "batch_status"),
        Index("ix_tuition_batches_teacher", "teacher_id"),
        Index("ix_tuition_batches_self_signed_teacher", "self_signed_teacher_id"),
        Index("ix_tuition_batches_school", "school_id"),
        Index("ix_tuition_batches_class_subject", "class_id", "subject_id"),
    )

    student_mappings = relationship(
        "TuitionBatchStudentMapping",
        back_populates="batch",
        cascade="all, delete-orphan",
    )
    schedules = relationship(
        "TuitionBatchSchedule",
        back_populates="batch",
        cascade="all, delete-orphan",
    )
    lesson_plans = relationship(
        "TuitionLessonPlan",
        back_populates="batch",
        cascade="all, delete-orphan",
    )
    lesson_plan_batches = relationship(
        "TuitionLessonPlanBatch",
        back_populates="batch",
        cascade="all, delete-orphan",
    )
    class_obj = relationship(
        "Class",
        foreign_keys=[class_id],
        primaryjoin="TuitionBatch.class_id == Class.id",
    )
    subject_obj = relationship(
        "Subject",
        foreign_keys=[subject_id],
        primaryjoin="TuitionBatch.subject_id == Subject.id",
    )
    class_done_records = relationship(
        "TuitionClassDoneRecord",
        back_populates="batch",
        cascade="all, delete-orphan",
    )
    teacher_earnings = relationship(
        "TuitionTeacherEarning",
        back_populates="batch",
        cascade="all, delete-orphan",
    )
    approval = relationship(
        "TuitionBatchApproval",
        back_populates="batch",
        uselist=False,
        cascade="all, delete-orphan",
    )


class TuitionBatchStudentMapping(Base):
    __tablename__ = "tuition_batch_student_mappings"

    id = Column(String, primary_key=True, default=lambda: generate_short_id("BSM"))
    batch_id = Column(String, ForeignKey("tuition_batches.id"), nullable=False)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=True)
    self_signed_student_id = Column(Integer, ForeignKey("self_signed_students.id"), nullable=True)
    student_type = Column(String(30), nullable=False, default="student")
    joined_date = Column(Date, nullable=False, default=datetime.utcnow().date)
    enrollment_status = Column(SQLEnum(EnrollmentStatus), nullable=False, default=EnrollmentStatus.PENDING)
    payment_status = Column(SQLEnum(PaymentStatus), nullable=False, default=PaymentStatus.PENDING)
    is_deleted = Column(Boolean, nullable=False, default=False)
    deleted_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("batch_id", "student_id", name="uq_tuition_batch_student"),
        UniqueConstraint("batch_id", "self_signed_student_id", name="uq_tuition_batch_self_signed_student"),
        Index("ix_tuition_batch_student_batch", "batch_id"),
        Index("ix_tuition_batch_student_enrollment", "enrollment_status"),
        Index("ix_tuition_batch_student_payment", "payment_status"),
    )

    batch = relationship("TuitionBatch", back_populates="student_mappings")


class TuitionBatchSchedule(Base):
    __tablename__ = "tuition_batch_schedules"

    id = Column(String, primary_key=True, default=lambda: generate_short_id("SCH"))
    batch_id = Column(String, ForeignKey("tuition_batches.id"), nullable=False)
    class_date = Column(Date, nullable=False)
    topic = Column(String(255), nullable=True)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    meeting_link_override = Column(Text, nullable=True)
    status = Column(String(30), nullable=False, default="scheduled")
    is_deleted = Column(Boolean, nullable=False, default=False)
    deleted_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("ix_tuition_schedule_batch_date", "batch_id", "class_date"),
        Index("ix_tuition_schedule_status", "status"),
    )

    batch = relationship("TuitionBatch", back_populates="schedules")
    class_done_record = relationship(
        "TuitionClassDoneRecord",
        back_populates="schedule",
        uselist=False,
        cascade="all, delete-orphan",
    )


class TuitionClassDoneRecord(Base):
    __tablename__ = "tuition_class_done_records"

    id = Column(String, primary_key=True, default=lambda: generate_short_id("CLS"))
    batch_id = Column(String, ForeignKey("tuition_batches.id"), nullable=False)
    schedule_id = Column(String, ForeignKey("tuition_batch_schedules.id"), nullable=False, unique=True)
    class_date = Column(Date, nullable=False)
    topic = Column(String(255), nullable=True)
    chapter = Column(String(255), nullable=True)
    summary = Column(Text, nullable=True)
    started_time = Column(Time, nullable=True)
    ended_time = Column(Time, nullable=True)
    duration_minutes = Column(Integer, nullable=True)
    created_by_type = Column(String(30), nullable=False, default="teacher")
    created_by_teacher_id = Column(String, ForeignKey("teachers.id"), nullable=True)
    created_by_self_signed_teacher_id = Column(Integer, ForeignKey("self_signed_teachers.id"), nullable=True)
    is_deleted = Column(Boolean, nullable=False, default=False)
    deleted_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_tuition_class_done_batch", "batch_id"),
        Index("ix_tuition_class_done_schedule", "schedule_id"),
    )

    batch = relationship("TuitionBatch", back_populates="class_done_records")
    schedule = relationship("TuitionBatchSchedule", back_populates="class_done_record")


class TuitionLessonPlan(Base):
    __tablename__ = "tuition_lesson_plans"

    id = Column(String, primary_key=True, default=lambda: generate_short_id("LP"))
    batch_id = Column(String, ForeignKey("tuition_batches.id"), nullable=False)
    chapter = Column(String(255), nullable=True)
    lesson_title = Column(String(255), nullable=False)
    objective = Column(Text, nullable=True)
    status = Column(String(30), nullable=False, default="active")
    is_deleted = Column(Boolean, nullable=False, default=False)
    deleted_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("ix_tuition_lesson_plan_batch", "batch_id"),
        Index("ix_tuition_lesson_plan_status", "status"),
    )

    batch = relationship("TuitionBatch", back_populates="lesson_plans")
    batch_mappings = relationship(
        "TuitionLessonPlanBatch",
        back_populates="lesson_plan",
        cascade="all, delete-orphan",
    )
    lessons = relationship(
        "TuitionLesson",
        back_populates="lesson_plan",
        cascade="all, delete-orphan",
    )
    assignments = relationship(
        "TuitionLessonAssignmentMapping",
        back_populates="lesson_plan",
        cascade="all, delete-orphan",
    )

    # Convenience read-only properties to match API schema expectations
    @property
    def title(self):
        return self.lesson_title

    @property
    def board(self):
        first_batch = self.batches[0] if self.batches else None
        return first_batch.board_id if getattr(first_batch, 'board_id', None) else None

    @property
    def class_id(self):
        first_batch = self.batches[0] if self.batches else None
        return first_batch.class_id if getattr(first_batch, 'class_id', None) else None

    @property
    def class_name(self):
        first_batch = self.batches[0] if self.batches else None
        if getattr(first_batch, 'class_obj', None) is not None:
            return first_batch.class_obj.name
        return None

    @property
    def subject_id(self):
        first_batch = self.batches[0] if self.batches else None
        return first_batch.subject_id if getattr(first_batch, 'subject_id', None) else None

    @property
    def subject_name(self):
        first_batch = self.batches[0] if self.batches else None
        if getattr(first_batch, 'subject_obj', None) is not None:
            return first_batch.subject_obj.name
        return None

    @property
    def remarks(self):
        # remarks may be set dynamically; default to None
        return getattr(self, '_remarks', None)

    @remarks.setter
    def remarks(self, value):
        self._remarks = value

    @property
    def batch_ids(self):
        mappings = getattr(self, 'batch_mappings', None) or []
        if mappings:
            return [mapping.batch_id for mapping in mappings if getattr(mapping, 'batch_id', None)]
        return [self.batch_id] if getattr(self, 'batch_id', None) else []

    @property
    def batches(self):
        mappings = getattr(self, 'batch_mappings', None) or []
        if mappings:
            return [mapping.batch for mapping in mappings if getattr(mapping, 'batch', None)]
        return [self.batch] if getattr(self, 'batch', None) else []


class TuitionLessonPlanBatch(Base):
    __tablename__ = "tuition_lesson_plan_batches"

    id = Column(String, primary_key=True, default=lambda: generate_short_id("LPB"))
    lesson_plan_id = Column(String, ForeignKey("tuition_lesson_plans.id"), nullable=False)
    batch_id = Column(String, ForeignKey("tuition_batches.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("lesson_plan_id", "batch_id", name="uq_tuition_lesson_plan_batch"),
        Index("ix_tuition_lesson_plan_batch_plan", "lesson_plan_id"),
        Index("ix_tuition_lesson_plan_batch_batch", "batch_id"),
    )

    lesson_plan = relationship("TuitionLessonPlan", back_populates="batch_mappings")
    batch = relationship("TuitionBatch", back_populates="lesson_plan_batches")


class TuitionLesson(Base):
    __tablename__ = "tuition_lessons"

    id = Column(String, primary_key=True, default=lambda: generate_short_id("LSN"))
    lesson_plan_id = Column(String, ForeignKey("tuition_lesson_plans.id"), nullable=False)
    lesson_title = Column(String(255), nullable=False)
    lesson_objective = Column(Text, nullable=True)
    display_order = Column(Integer, nullable=False, default=1)
    is_deleted = Column(Boolean, nullable=False, default=False)
    deleted_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("lesson_plan_id", "display_order", name="uq_tuition_lesson_order"),
        Index("ix_tuition_lesson_plan", "lesson_plan_id"),
        Index("ix_tuition_lesson_order", "display_order"),
    )

    lesson_plan = relationship("TuitionLessonPlan", back_populates="lessons")
    topics = relationship(
        "TuitionLessonTopic",
        back_populates="lesson",
        cascade="all, delete-orphan",
        order_by="TuitionLessonTopic.display_order",
    )
    mappings = relationship(
        "TuitionLessonAssignmentMapping",
        back_populates="lesson",
        cascade="all, delete-orphan",
    )


class TuitionLessonTopic(Base):
    __tablename__ = "tuition_lesson_topics"

    id = Column(String, primary_key=True, default=lambda: generate_short_id("TOP"))
    lesson_id = Column(String, ForeignKey("tuition_lessons.id"), nullable=False)
    topic_title = Column(String(255), nullable=False)
    topic_content = Column(Text, nullable=True)
    display_order = Column(Integer, nullable=False, default=1)
    reference_video_link = Column(Text, nullable=True)
    is_deleted = Column(Boolean, nullable=False, default=False)
    deleted_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("lesson_id", "display_order", name="uq_tuition_lesson_topic_order"),
        Index("ix_tuition_lesson_topic_lesson", "lesson_id"),
        Index("ix_tuition_lesson_topic_order", "display_order"),
    )

    lesson = relationship("TuitionLesson", back_populates="topics")
    files = relationship(
        "TuitionTopicFile",
        back_populates="topic",
        cascade="all, delete-orphan",
    )


class TuitionTopicFile(Base):
    __tablename__ = "tuition_topic_files"

    id = Column(String, primary_key=True, default=lambda: generate_short_id("FIL"))
    topic_id = Column(String, ForeignKey("tuition_lesson_topics.id"), nullable=False)
    file_name = Column(String(255), nullable=False)
    file_url = Column(Text, nullable=False)
    file_type = Column(String(100), nullable=True)
    uploaded_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    uploaded_by_teacher_id = Column(String, ForeignKey("teachers.id"), nullable=True)
    uploaded_by_self_signed_teacher_id = Column(Integer, ForeignKey("self_signed_teachers.id"), nullable=True)
    is_deleted = Column(Boolean, nullable=False, default=False)
    deleted_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_tuition_topic_file_topic", "topic_id"),
    )

    topic = relationship("TuitionLessonTopic", back_populates="files")


class TuitionLessonAssignmentMapping(Base):
    __tablename__ = "tuition_lesson_assignment_mappings"

    id = Column(String, primary_key=True, default=lambda: generate_short_id("ASM"))
    lesson_plan_id = Column(String, ForeignKey("tuition_lesson_plans.id"), nullable=False)
    lesson_id = Column(String, ForeignKey("tuition_lessons.id"), nullable=True)
    assignment_id = Column(Integer, ForeignKey("assignments.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("lesson_plan_id", "lesson_id", "assignment_id", name="uq_tuition_lesson_assignment_mapping"),
        Index("ix_tuition_lesson_assignment_plan", "lesson_plan_id"),
        Index("ix_tuition_lesson_assignment_assignment", "assignment_id"),
    )

    lesson_plan = relationship("TuitionLessonPlan", back_populates="assignments")
    lesson = relationship("TuitionLesson", back_populates="mappings")


class TuitionTeacherEarning(Base):
    __tablename__ = "tuition_teacher_earnings"

    id = Column(String, primary_key=True, default=lambda: generate_short_id("EARN"))
    teacher_id = Column(String, ForeignKey("teachers.id"), nullable=True)
    self_signed_teacher_id = Column(Integer, ForeignKey("self_signed_teachers.id"), nullable=True)
    teacher_type = Column(String(30), nullable=False, default="teacher")
    batch_id = Column(String, ForeignKey("tuition_batches.id"), nullable=False)
    gross_amount = Column(Numeric(12, 2), nullable=False, default=0)
    commission = Column(Numeric(12, 2), nullable=False, default=0)
    net_amount = Column(Numeric(12, 2), nullable=False, default=0)
    paid_amount = Column(Numeric(12, 2), nullable=False, default=0)
    pending_amount = Column(Numeric(12, 2), nullable=False, default=0)
    settlement_status = Column(SQLEnum(SettlementStatus), nullable=False, default=SettlementStatus.PENDING)
    is_deleted = Column(Boolean, nullable=False, default=False)
    deleted_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("batch_id", "teacher_id", name="uq_tuition_teacher_earning_teacher"),
        UniqueConstraint("batch_id", "self_signed_teacher_id", name="uq_tuition_teacher_earning_self_signed_teacher"),
        Index("ix_tuition_teacher_earnings_batch", "batch_id"),
        Index("ix_tuition_teacher_earnings_status", "settlement_status"),
    )

    batch = relationship("TuitionBatch", back_populates="teacher_earnings")


class TuitionBatchApproval(Base):
    __tablename__ = "tuition_batch_approvals"

    id = Column(String, primary_key=True, default=lambda: generate_short_id("APRV"))
    batch_id = Column(String, ForeignKey("tuition_batches.id"), nullable=False, unique=True)
    approval_status = Column(SQLEnum(ApprovalStatus), nullable=False, default=ApprovalStatus.PENDING)
    requested_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    approved_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    approval_note = Column(Text, nullable=True)
    requested_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    approved_at = Column(DateTime, nullable=True)
    is_deleted = Column(Boolean, nullable=False, default=False)
    deleted_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("ix_tuition_batch_approval_status", "approval_status"),
        Index("ix_tuition_batch_approval_batch", "batch_id"),
    )

    batch = relationship("TuitionBatch", back_populates="approval")
