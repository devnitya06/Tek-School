from datetime import date, datetime, time, timezone
from enum import Enum
import secrets
import string

from sqlalchemy import JSON, Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, Time

from app.db.session import Base


class TeachingMode(str, Enum):
    ONLINE_CLASS_AND_STUDY_MATERIALS = "ONLINE_CLASS_AND_STUDY_MATERIALS"
    STUDY_MATERIALS_ONLY = "STUDY_MATERIALS_ONLY"


class TeachingSetupStatus(str, Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class MeetingProvider(str, Enum):
    GOOGLE_MEET = "GOOGLE_MEET"
    ZOOM = "ZOOM"


def generate_teaching_setup_id(prefix: str = "TS", length: int = 8) -> str:
    alphabet = string.ascii_uppercase + string.digits
    suffix = "".join(secrets.choice(alphabet) for _ in range(length))
    return f"{prefix}{suffix}"


class TuitionTeachingSetup(Base):
    __tablename__ = "tuition_teaching_setups"

    id = Column(String, primary_key=True, default=generate_teaching_setup_id)
    lesson_plan_id = Column(String, ForeignKey("tuition_lesson_plans.id"), nullable=False)
    batch_id = Column(String, ForeignKey("tuition_batches.id"), nullable=True)
    teaching_mode = Column(String(100), nullable=False, default=TeachingMode.ONLINE_CLASS_AND_STUDY_MATERIALS.value)
    batch_title = Column(String(255), nullable=True)
    batch_start_date = Column(Date, nullable=True)
    batch_end_date = Column(Date, nullable=True)
    tuition_from_time = Column(Time, nullable=True)
    tuition_to_time = Column(Time, nullable=True)
    tuition_days = Column(JSON, nullable=True)
    languages = Column(JSON, nullable=True)
    subjects = Column(JSON, nullable=True)
    material_update_days = Column(JSON, nullable=True)
    upload_from_time = Column(Time, nullable=True)
    upload_to_time = Column(Time, nullable=True)
    monthly_tuition_fee = Column(Numeric(12, 2), nullable=False, default=0)
    monthly_tuition_discount = Column(Numeric(12, 2), nullable=False, default=0)
    premium_study_material_fee = Column(Numeric(12, 2), nullable=False, default=0)
    premium_study_material_discount = Column(Numeric(12, 2), nullable=False, default=0)
    maximum_students = Column(Integer, nullable=False, default=200)
    teacher_type = Column(String(30), nullable=False, default="teacher")
    is_active = Column(Boolean, nullable=False, default=True)
    meeting_provider = Column(String(50), nullable=True)
    meeting_link = Column(Text, nullable=True)
    online_teaching_ability = Column(Boolean, nullable=True)
    stable_internet_connection = Column(Boolean, nullable=True)
    camera_available = Column(Boolean, nullable=True)
    silent_place_without_background_noise = Column(Boolean, nullable=True)
    laptop_desktop_pc = Column(Boolean, nullable=True)
    headphone_whiteboard = Column(Boolean, nullable=True)
    status = Column(String(20), nullable=False, default=TeachingSetupStatus.ACTIVE.value)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_by_teacher_id = Column(String, ForeignKey("teachers.id"), nullable=True)
    created_by_self_signed_teacher_id = Column(Integer, ForeignKey("self_signed_teachers.id"), nullable=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    is_deleted = Column(Boolean, nullable=False, default=False)
    deleted_at = Column(DateTime, nullable=True)

    @property
    def final_tuition_fee(self):
        return (self.monthly_tuition_fee or 0) - (self.monthly_tuition_discount or 0)

    @property
    def final_premium_fee(self):
        return (self.premium_study_material_fee or 0) - (self.premium_study_material_discount or 0)

    @property
    def available_seats(self):
        return max(0, (self.maximum_students or 0) - self.joined_students_count)

    @property
    def joined_students_count(self):
        return 0

    @property
    def average_rating(self):
        return 0.0

    @property
    def total_reviews(self):
        return 0
