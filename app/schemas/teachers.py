from pydantic import BaseModel, EmailStr
from typing import List, Literal
from datetime import time
from app.models.teachers import DayOfWeek

class Assignment(BaseModel):
    class_id: int
    section_id: int
    subject_id: int

class TeacherCreateRequest(BaseModel):
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
class TeacherResponse(BaseModel):
    id: str
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