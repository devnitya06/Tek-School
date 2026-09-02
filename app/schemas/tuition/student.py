from datetime import date, datetime, time
from typing import List, Optional
from pydantic import BaseModel


# ============================================================================
# ENROLLMENT & DISCOVERY SCHEMAS
# ============================================================================

class TuitionBatchTeacherInfo(BaseModel):
    """Basic teacher info in batch summary"""
    teacher_id: str
    teacher_name: str
    teacher_type: str  # "teacher" or "self_signed_teacher"
    
    class Config:
        from_attributes = True


class TuitionBatchScheduleInfo(BaseModel):
    """Schedule info in batch summary"""
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    days: Optional[List[str]] = None
    time_slot: Optional[str] = None


class StudentEnrollmentResponse(BaseModel):
    """Response for enrolling in a batch"""
    enrollment_id: str
    batch_id: str
    enrollment_status: str
    payment_status: str
    joined_date: date


class StudentTuitionListItem(BaseModel):
    """Item in student's tuition list"""
    enrollment_id: str
    batch_id: str
    batch_name: str
    teacher_name: str
    teacher_id: str
    teacher_type: str
    board: str
    class_name: str
    subject_name: str
    enrollment_status: str
    payment_status: str
    batch_status: str
    joined_date: date
    schedule: TuitionBatchScheduleInfo
    progress: Optional[dict] = None

    class Config:
        from_attributes = True


class StudentTuitionListResponse(BaseModel):
    """Response for listing student's tuitions"""
    total: int
    page: int
    page_size: int
    enrollments: List[StudentTuitionListItem]


class AvailableBatchSummary(BaseModel):
    """Summary of available batch for discovery"""
    batch_id: str
    batch_name: str
    teacher: TuitionBatchTeacherInfo
    board: str
    class_name: str
    subject_name: str
    batch_status: str
    description: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    batch_capacity: int
    tuition_fee: str
    study_material_fee: str
    enrolled_count: int
    language: Optional[str] = None

    class Config:
        from_attributes = True


class AvailableBatchesResponse(BaseModel):
    """Response for available batches"""
    total: int
    page: int
    page_size: int
    batches: List[AvailableBatchSummary]


# ============================================================================
# STUDY PLAN & CURRICULUM SCHEMAS
# ============================================================================

class StudentTopicProgress(BaseModel):
    """Student's progress on a topic"""
    topic_id: str
    status: str  # not_started, in_progress, completed
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class TopicSummary(BaseModel):
    """Topic in lesson"""
    topic_id: str
    topic_title: str
    display_order: int
    status: Optional[str] = None  # from StudentTuitionTopicProgress
    has_files: bool = False

    class Config:
        from_attributes = True


class LessonSummary(BaseModel):
    """Lesson in study plan"""
    lesson_id: str
    lesson_number: int
    lesson_title: str
    lesson_objective: Optional[str] = None
    topics_count: int
    topics_completed: int
    completion_percentage: int

    class Config:
        from_attributes = True


class StudyPlanResponse(BaseModel):
    """Response for batch study plan"""
    batch_id: str
    batch_name: str
    lesson_plan_id: str
    subject: str
    board: str
    class_name: str
    total_lessons: int
    total_topics: int
    lessons_completed: int
    topics_completed: int
    overall_completion_percentage: int
    lessons: List[LessonSummary]

    class Config:
        from_attributes = True


class LessonDetailResponse(BaseModel):
    """Response for lesson details"""
    lesson_id: str
    lesson_number: int
    lesson_title: str
    lesson_objective: Optional[str] = None
    topics: List[TopicSummary]
    topics_completed: int

    class Config:
        from_attributes = True


class TopicFileResponse(BaseModel):
    """File attached to topic"""
    file_id: str
    file_name: str
    file_url: str
    file_type: str
    file_size: Optional[int] = None
    uploaded_at: datetime

    class Config:
        from_attributes = True


class TopicDetailResponse(BaseModel):
    """Response for topic details"""
    topic_id: str
    topic_title: str
    topic_content: Optional[str] = None
    display_order: int
    reference_video_link: Optional[str] = None
    files: List[TopicFileResponse] = []
    student_progress: Optional[StudentTopicProgress] = None

    class Config:
        from_attributes = True


class TopicCompleteResponse(BaseModel):
    """Response for marking topic complete"""
    topic_id: str
    status: str
    completed_at: datetime


# ============================================================================
# SCHEDULE & CLASS SCHEMAS
# ============================================================================

class ScheduleItemResponse(BaseModel):
    """Class schedule item"""
    schedule_id: str
    class_date: date
    start_time: time
    end_time: time
    topic: Optional[str] = None
    meeting_link: Optional[str] = None
    meeting_link_override: Optional[str] = None
    status: str  # scheduled, completed, cancelled
    class_summary: Optional[str] = None

    class Config:
        from_attributes = True


class BatchScheduleResponse(BaseModel):
    """Response for batch schedule"""
    total: int
    page: int
    page_size: int
    schedules: List[ScheduleItemResponse]


class JoinClassResponse(BaseModel):
    """Response for joining live class"""
    schedule_id: str
    class_date: date
    start_time: time
    end_time: time
    topic: Optional[str] = None
    meeting_provider: str
    meeting_link: str


# ============================================================================
# ASSIGNMENT SCHEMAS
# ============================================================================

class AssignmentSummary(BaseModel):
    """Assignment in batch"""
    assignment_id: int
    title: str
    chapter: Optional[str] = None
    topic_ids: Optional[List[str]] = []
    question_count: int
    due_date: Optional[date] = None
    status: str
    student_attempt_status: str  # not_attempted, in_progress, submitted, graded

    class Config:
        from_attributes = True


class BatchAssignmentsResponse(BaseModel):
    """Response for batch assignments"""
    total: int
    page: int
    page_size: int
    assignments: List[AssignmentSummary]


# ============================================================================
# DASHBOARD SCHEMAS
# ============================================================================

class DashboardTuitionItem(BaseModel):
    """Tuition item in dashboard"""
    batch_id: str
    batch_name: str
    teacher_name: str
    subject_name: str
    progress_percentage: int
    enrollment_status: str


class DashboardUpcomingClass(BaseModel):
    """Upcoming class in dashboard"""
    schedule_id: str
    class_date: date
    start_time: time
    subject_name: str
    batch_name: str


class DashboardRecentAssignment(BaseModel):
    """Recent assignment in dashboard"""
    assignment_id: int
    title: str
    batch_name: str
    due_date: Optional[date] = None
    status: str


class DashboardStudyProgress(BaseModel):
    """Overall study progress"""
    total_topics: int
    topics_completed: int
    total_lessons: int
    lessons_completed: int
    overall_percentage: int


class StudentDashboardResponse(BaseModel):
    """Student dashboard response"""
    active_tuitions_count: int
    tuitions: List[DashboardTuitionItem]
    upcoming_classes: List[DashboardUpcomingClass]
    recent_assignments: List[DashboardRecentAssignment]
    study_progress: DashboardStudyProgress
