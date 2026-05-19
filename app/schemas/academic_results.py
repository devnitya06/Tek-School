from pydantic import BaseModel, Field, field_validator
from typing import List, Dict, Optional, Any
from datetime import date, datetime
from app.models.academic_results import AcademicResultType

class SubjectMarkDefinition(BaseModel):
    subject_id: int
    full_marks: float

class GradePercentages(BaseModel):
    excellent: float
    very_good: float
    good: float
    average: float
    poor: float
    failed: float

class AcademicResultDefinitionBase(BaseModel):
    result_type: AcademicResultType
    exam_date: date
    class_id: int
    sections: List[int]
    subject_marks: List[SubjectMarkDefinition]
    grade_percentages: GradePercentages

class AcademicResultDefinitionCreate(AcademicResultDefinitionBase):
    pass

class AcademicResultDefinitionResponse(AcademicResultDefinitionBase):
    id: int
    school_id: str
    created_at: datetime
    
    @field_validator('sections', mode='before')
    def extract_section_ids(cls, v):
        if not v:
            return []
        if isinstance(v[0], int):
            return v
        return [sec.id for sec in v if hasattr(sec, 'id')]
        
    class Config:
        from_attributes = True

class SubjectSecureMark(BaseModel):
    subject_id: int
    secure_mark: float

class AcademicStudentResultCreate(BaseModel):
    secure_marks: List[SubjectSecureMark]
    last_result_day: Optional[date] = None

class AcademicStudentResultResponse(BaseModel):
    id: int
    definition_id: int
    student_id: int
    secure_marks: List[SubjectSecureMark]
    total_secure_mark: float
    grade: str
    last_result_day: Optional[date] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True

class StudentAcademicResultListItem(BaseModel):
    student_id: int
    student_name: str
    roll_no: int
    class_name: Optional[str] = None
    section_name: Optional[str] = None
    result_type: Optional[AcademicResultType] = None
    secure_mark: Optional[float] = None
    grade: Optional[str] = None
    last_result_day: Optional[date] = None
    result_id: Optional[int] = None
    definition_id: Optional[int] = None

class StudentAcademicResultListResponse(BaseModel):
    items: List[StudentAcademicResultListItem]
    total_count: int

class AcademicResultHistoryItem(BaseModel):
    result_id: int
    definition_id: int
    result_type: AcademicResultType
    exam_date: date
    class_name: str
    secure_marks: List[SubjectSecureMark]
    total_secure_mark: float
    grade: str
    last_result_day: Optional[date] = None

class AcademicResultHistoryResponse(BaseModel):
    items: List[AcademicResultHistoryItem]
