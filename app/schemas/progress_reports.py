from pydantic import BaseModel, Field, validator
from typing import List, Optional
from datetime import date, datetime
from app.models.progress_reports import ProgressReportStatus

class SubjectPerformance(BaseModel):
    subject_name: str = Field(..., description="Name of the subject")
    status: str = Field(..., description="Performance status: good, better, best, average, excellent, poor")

class AssessmentAreaPerformance(BaseModel):
    area: str = Field(..., description="Assessment area, e.g., Discipline, Teamwork")
    status: str = Field(..., description="Performance status: good, better, best, average, excellent, poor")

class ProgressReportCreate(BaseModel):
    student_id: int
    report_title: str
    duration_from: date
    duration_to: date
    status: ProgressReportStatus = ProgressReportStatus.DRAFT
    subjects: List[SubjectPerformance] = []
    assessment_areas: List[AssessmentAreaPerformance] = []
    key_needs_improvement: List[str] = []

    @validator("duration_to")
    def validate_duration_to(cls, v):
        if v > date.today():
            raise ValueError("duration_to cannot be a future date")
        return v

class ProgressReportUpdate(BaseModel):
    report_title: Optional[str] = None
    duration_from: Optional[date] = None
    duration_to: Optional[date] = None
    status: Optional[ProgressReportStatus] = None
    subjects: Optional[List[SubjectPerformance]] = None
    assessment_areas: Optional[List[AssessmentAreaPerformance]] = None
    key_needs_improvement: Optional[List[str]] = None

    @validator("duration_to")
    def validate_duration_to(cls, v):
        if v and v > date.today():
            raise ValueError("duration_to cannot be a future date")
        return v

class ProgressReportResponse(BaseModel):
    id: int
    student_id: int
    school_id: str
    teacher_id: Optional[str]
    report_title: str
    duration_from: date
    duration_to: date
    status: ProgressReportStatus
    subjects: Optional[List[dict]]
    assessment_areas: Optional[List[dict]]
    key_needs_improvement: Optional[List[str]]
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True

class StudentProgressListResponse(BaseModel):
    student_id: int
    student_name: str
    class_name: str
    section_name: str
    roll_no: int
    no_of_reports: int
    last_report_date: Optional[date]
    student_status: str

    class Config:
        from_attributes = True
