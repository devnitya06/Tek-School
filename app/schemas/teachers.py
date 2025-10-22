from pydantic import BaseModel, EmailStr
from typing import List, Literal,Optional
from datetime import time
from app.models.teachers import DayOfWeek

class Assignment(BaseModel):
    class_id: int
    section_id: int
    subject_id: int

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