from pydantic import BaseModel, Field, validator, root_validator, ConfigDict
from typing import List, Optional, Union
from datetime import datetime
from app.models.assignments.assignment import AssignmentStatus, AssignmentType, StudentImprovementCategory, DoubtStatus, ReportCategory, ReportStatus, TaskStatus # Import new enums and TaskStatus
import json

# Helper for JSON fields
pass
# Minimal JSON-encoded helpers used by schemas
JsonEncodedDict = dict
JsonEncodedList = list

# Basic Schemas for Assignment Module
class AssignmentKeyPointBase(BaseModel):
    step_number: int
    text: str
    image_url: Optional[str] = None

class AssignmentKeyPointCreate(AssignmentKeyPointBase):
    pass

class AssignmentKeyPointResponse(AssignmentKeyPointBase):
    id: int
    
    model_config = ConfigDict(from_attributes=True)

class AssignmentQuestionBase(BaseModel):
    question_number: int
    question_text: str
    option_a: str
    option_b: str
    option_c: str
    option_d: str
    correct_option: str
    solution_explanation: Optional[str] = None

class AssignmentQuestionCreate(AssignmentQuestionBase):
    pass

class AssignmentQuestionResponse(AssignmentQuestionBase):
    id: int
    
    model_config = ConfigDict(from_attributes=True)

class AssignmentImageBase(BaseModel):
    url: str

class AssignmentImageCreate(AssignmentImageBase):
    pass

class AssignmentImageResponse(AssignmentImageBase):
    id: int
    
    model_config = ConfigDict(from_attributes=True)

class AssignmentPDFBase(BaseModel):
    url: str

class AssignmentPDFCreate(AssignmentPDFBase):
    pass

class AssignmentPDFResponse(AssignmentPDFBase):
    id: int
    
    model_config = ConfigDict(from_attributes=True)

class AssignmentVideoLinkBase(BaseModel):
    url: str

class AssignmentVideoLinkCreate(AssignmentVideoLinkBase):
    pass

class AssignmentVideoLinkResponse(AssignmentVideoLinkBase):
    id: int
    
    model_config = ConfigDict(from_attributes=True)

class AssignmentMediaBannerBase(BaseModel):
    url: str

class AssignmentMediaBannerCreate(AssignmentMediaBannerBase):
    pass

class AssignmentMediaBannerResponse(AssignmentMediaBannerBase):
    id: int
    
    model_config = ConfigDict(from_attributes=True)

class PublishConfigurationBase(BaseModel):
    assignment_type: AssignmentType
    improvement_categories: List[StudentImprovementCategory]
    reward_amount_override: Optional[float] = None

    class Config:
        json_encoders = {
            List[StudentImprovementCategory]: lambda v: [e.value for e in v]
        }


class PublishConfigurationCreate(PublishConfigurationBase):
    pass

class PublishConfigurationResponse(BaseModel):
    id: int
    assignment_id: int
    assignment_type: AssignmentType
    improvement_categories: List[StudentImprovementCategory]
    reward_amount_override: Optional[float] = None

    @validator("improvement_categories", pre=True)
    def parse_improvement_categories(cls, value):
        # Accept JSON string or list of enum values; normalize to list
        if value is None:
            return []
        try:
            if isinstance(value, str):
                parsed = json.loads(value)
                return [StudentImprovementCategory(v) if not isinstance(v, StudentImprovementCategory) else v for v in parsed]
            if isinstance(value, list):
                return [StudentImprovementCategory(v) if not isinstance(v, StudentImprovementCategory) else v for v in value]
        except Exception:
            return []
        return value

    model_config = ConfigDict(from_attributes=True)


# --- New Schemas for merged AssignmentActivity models ---

class AssignmentTaskBase(BaseModel):
    title: str
    description: Optional[str] = None
    file: Optional[str] = None

class AssignmentTaskCreate(AssignmentTaskBase):
    pass

class AssignmentTaskResponse(AssignmentTaskBase):
    id: int
    assignment_id: int

    model_config = ConfigDict(from_attributes=True)


class StudentTaskStatusBase(BaseModel):
    task_id: int
    status: TaskStatus
    completed_at: Optional[datetime] = None

class StudentTaskStatusCreate(StudentTaskStatusBase):
    student_id: Optional[int] = None # For clarity in creation, though linked via progress

class StudentTaskStatusResponse(StudentTaskStatusBase):
    id: int
    student_assignment_progress_id: int
    student_id: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class StudentAssignmentProgressBase(BaseModel):
    student_id: Optional[int] = None
    self_signed_student_id: Optional[int] = None
    status: AssignmentStatus = AssignmentStatus.IN_PROGRESS # Overall progress status

class StudentAssignmentProgressCreate(StudentAssignmentProgressBase):
    pass

class StudentAssignmentProgressResponse(StudentAssignmentProgressBase):
    id: int
    assignment_id: int
    assigned_date: datetime
    task_statuses: List[StudentTaskStatusResponse] = []

    model_config = ConfigDict(from_attributes=True)


# --- Unified Doubt Schemas ---

class AssignmentDoubtBase(BaseModel):
    doubt_text: str
    doubt_summary: Optional[str] = None # From AssignmentActivityDoubt
    question_id: Optional[int] = None

class AssignmentDoubtCreate(AssignmentDoubtBase):
    # For creation, link to student and assignment will be handled in route
    pass

class DoubtReplyBase(BaseModel):
    reply_text: str
    file_url: Optional[str] = None # From AssignmentActivityDoubtReply
    step_solutions: Optional[str] = None

class DoubtReplyCreate(DoubtReplyBase):
    # For creation, link to teacher and doubt will be handled in route
    pass

class DoubtReplyResponse(DoubtReplyBase):
    id: int
    doubt_id: int
    teacher_user_id: Optional[int] = None
    self_signed_teacher_id: Optional[int] = None
    student_user_id: Optional[int] = None
    self_signed_student_id: Optional[int] = None
    sender_type: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DoubtConversationMessageResponse(BaseModel):
    sender_type: Optional[str] = None
    message: str
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class AssignmentDoubtResponse(BaseModel):
    id: int
    assignment_id: int
    student_user_id: Optional[int] = None
    self_signed_student_id: Optional[int] = None
    student_name: Optional[str] = None
    status: DoubtStatus
    created_at: datetime
    resolved_at: Optional[datetime] = None
    number_of_attempts: int = 0
    last_attempt_date: Optional[datetime] = None
    result: Optional[float] = None
    replies: List[DoubtConversationMessageResponse] = []

    model_config = ConfigDict(from_attributes=True)


# --- Unified Report Schemas ---

class AssignmentReportBase(BaseModel):
    category: ReportCategory
    reason: str
    comment: Optional[str] = None

class AssignmentReportCreate(AssignmentReportBase):
    # For creation, link to student and assignment will be handled in route
    pass

class AssignmentReportStatusUpdate(BaseModel):
    status: ReportStatus
    admin_notes: Optional[str] = None

class AssignmentReportResponse(AssignmentReportBase):
    id: int
    assignment_id: int
    student_user_id: Optional[int] = None
    self_signed_student_id: Optional[int] = None
    created_at: datetime
    
    # From AssignmentActivityReport
    additional_comments: Optional[str] = None
    status: ReportStatus
    viewed_by_teacher: Optional[datetime] = None
    viewed_by_admin: Optional[datetime] = None
    admin_notes: Optional[str] = None
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# --- Main Assignment Schemas (Updated) ---

class AssignmentBase(BaseModel):
    board: str
    class_name: str
    subject: str
    chapter_number: int
    sub_chapter: Optional[str] = None
    topic_title: str
    chapter_tagline: Optional[str] = None
    original_content: Optional[str] = None
    summarized_content: Optional[str] = None
    
    # From AssignmentActivity
    activity_type: AssignmentType = AssignmentType.ACADEMIC # New field
    class_id: Optional[int] = None # New field
    subject_id: Optional[int] = None # New field
    chapter_id: Optional[int] = None # New field
    chapter_ids: Optional[List[int]] = None # New field

class AssignmentCreate(AssignmentBase):
    key_points: Optional[List[AssignmentKeyPointCreate]] = None
    questions: Optional[List[AssignmentQuestionCreate]] = None
    tasks: Optional[List[AssignmentTaskCreate]] = None # New field
    student_ids: Optional[List[int]] = None # New field
    self_signed_student_ids: Optional[List[int]] = None # New field

class AssignmentUpdate(AssignmentBase):
    status: Optional[AssignmentStatus] = None
    key_points: Optional[List[AssignmentKeyPointCreate]] = None
    questions: Optional[List[AssignmentQuestionCreate]] = None
    tasks: Optional[List[AssignmentTaskCreate]] = None # New field

class FavoriteTeacherCreate(BaseModel):
    teacher_id: str


class FavoriteTeacherResponse(BaseModel):
    teacher_id: str
    is_favorite: bool

    model_config = ConfigDict(from_attributes=True)


class FavoriteTeacherListResponse(BaseModel):
    teacher_id: str
    teacher_name: Optional[str] = None
    teacher_type: str
    is_favorite: bool = True

    model_config = ConfigDict(from_attributes=True)


class AssignmentResponse(AssignmentBase):
    id: int
    created_by_user_id: Optional[int] = None # Can be null now for self-signed
    created_by_teacher_id: Optional[Union[str, int]] = None # New field
    teacher_id: Optional[Union[str, int]] = None # Alias for created_by_teacher_id / self-signed teacher id
    created_by_self_signed_teacher_id: Optional[int] = None # New field
    status: AssignmentStatus
    created_at: datetime
    published_at: Optional[datetime] = None
    updated_at: datetime
    teacher_name: Optional[str] = None
    school_name: Optional[str] = None
    school_address: Optional[str] = None
    creator_favorite_count: int = 0

    @root_validator(pre=True)
    def populate_teacher_id(cls, values):
        if isinstance(values, dict):
            teacher_id = values.get("teacher_id")
            if teacher_id is not None:
                return values
            if values.get("created_by_teacher_id") is not None:
                values["teacher_id"] = values.get("created_by_teacher_id")
            elif values.get("created_by_self_signed_teacher_id") is not None:
                values["teacher_id"] = values.get("created_by_self_signed_teacher_id")
            return values

        teacher_id = getattr(values, "teacher_id", None)
        if teacher_id is not None:
            return values
        if getattr(values, "created_by_teacher_id", None) is not None:
            setattr(values, "teacher_id", getattr(values, "created_by_teacher_id"))
        elif getattr(values, "created_by_self_signed_teacher_id", None) is not None:
            setattr(values, "teacher_id", getattr(values, "created_by_self_signed_teacher_id"))
        return values

    # Computed counts
    participants_count: int = 0
    doubts_count: int = 0
    made_ideal_count: int = 0

    key_points: List[AssignmentKeyPointResponse] = []
    questions: List[AssignmentQuestionResponse] = []
    images: List[AssignmentImageResponse] = []
    pdfs: List[AssignmentPDFResponse] = []
    video_links: List[AssignmentVideoLinkResponse] = []
    media_banners: List[AssignmentMediaBannerResponse] = []
    publish_config: Optional[PublishConfigurationResponse] = None
    tasks: List[AssignmentTaskResponse] = [] # New field
    assigned_students_progress: List[StudentAssignmentProgressResponse] = [] # New field

    model_config = ConfigDict(from_attributes=True)


class StudentAssignmentAttemptBase(BaseModel):
    submitted_answers: JsonEncodedDict # JSON string
    score: float
    time_taken_seconds: Optional[int] = None

class StudentAssignmentAttemptCreate(StudentAssignmentAttemptBase):
    pass

class StudentAssignmentAttemptResponse(StudentAssignmentAttemptBase):
    id: int
    student_user_id: int
    assignment_id: int
    student_name: Optional[str] = None
    attempt_number: int
    submission_date: datetime

    model_config = ConfigDict(from_attributes=True)


class ChapterFeedbackBase(BaseModel):
    is_helpful: bool

class ChapterFeedbackCreate(ChapterFeedbackBase):
    pass

class ChapterFeedbackResponse(ChapterFeedbackBase):
    id: int
    student_id: int
    assignment_id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TeacherRatingBase(BaseModel):
    rating: int = Field(..., ge=1, le=5) # 1-5 stars

class TeacherRatingCreate(TeacherRatingBase):
    pass

class TeacherRatingResponse(TeacherRatingBase):
    id: int
    teacher_id: int
    student_id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class AssignmentViewResponse(BaseModel):
    id: int
    assignment_id: int
    viewer_user_id: int
    viewed_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DoubtReplyBase(BaseModel):
    reply_text: str
    file_url: Optional[str] = None # From AssignmentActivityDoubtReply
    step_solutions: Optional[str] = None

class DoubtReplyCreate(DoubtReplyBase):
    # For creation, link to teacher and doubt will be handled in route
    pass

class AssignmentReportBase(BaseModel):
    category: ReportCategory
    reason: str
    comment: Optional[str] = None

class AssignmentReportCreate(AssignmentReportBase):
    pass

class AssignmentReportResponse(AssignmentReportBase):
    id: int
    assignment_id: int
    student_id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

# Schemas for API responses/requests
class TeacherProfileResponse(BaseModel):
    teacher_id: int
    teacher_name: str
    school_name: Optional[str] = None
    school_address: Optional[str] = None
    average_rating: float = 0.0
    rating_count: int = 0
    total_exams_count: int = 0
    total_assignments_count: int = 0
    total_participants_count: int = 0

    model_config = ConfigDict(from_attributes=True)

class SubjectSummaryResponse(BaseModel):
    board: str
    class_name: str
    subject: str
    total_study_materials: int
    your_study_materials: Optional[int] = None # For teachers
    completed_count: Optional[int] = None # For students

    model_config = ConfigDict(from_attributes=True)
