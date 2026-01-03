from pydantic import BaseModel, EmailStr, Field
from typing import List, Literal,Optional
from datetime import time
from app.models.teachers import DayOfWeek

class Assignment(BaseModel):
    class_id: int
    section_id: int
    subject_id: int

class TeacherPaymentCreate(BaseModel):
    """Payment structure for teacher creation"""
    basic_salary: float = Field(default=0.0, ge=0, description="Basic salary amount")
    allowance: float = Field(default=0.0, ge=0, description="Allowance amount")
    bonus: float = Field(default=0.0, ge=0, description="Bonus amount")
    other_allowances: float = Field(default=0.0, ge=0, description="Other allowances amount")
    incentive_plan: float = Field(default=0.0, ge=0, description="Incentive plan amount")
    health_care_insurance: float = Field(default=0.0, ge=0, description="Health care insurance amount")
    skill_development: float = Field(default=0.0, ge=0, description="Skill development amount")

class TeacherCreateRequest(BaseModel):
    profile_image: Optional[str]=None
    first_name: str
    last_name: str
    highest_qualification: str
    university: str
    phone: str
    email: EmailStr
    start_duty: time
    end_duty: time
    teacher_type: Literal["full_time", "part_time"]
    present_in: List[DayOfWeek]
    assignments: List[Assignment]
    payment: Optional[TeacherPaymentCreate] = None  # Optional payment structure

class TeacherUpdateRequest(BaseModel):
    profile_image: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    highest_qualification: Optional[str] = None
    university: Optional[str] = None
    start_duty: Optional[time] = None  
    end_duty: Optional[time] = None 
    teacher_type: Optional[Literal["full_time", "part_time"]] = None
    present_in: Optional[List[DayOfWeek]] = None
    assignments: Optional[List[Assignment]] = None 
class TeacherResponse(BaseModel):
    id: str
    profile_image:str
    first_name: str
    last_name: str
    highest_qualification: str
    university: str
    phone: str
    email: EmailStr
    start_duty: time
    end_duty: time
    teacher_type: Literal["full_time", "part_time"]
    present_in: DayOfWeek
    model_config = {
        "from_attributes": True
    }