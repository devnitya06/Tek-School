from pydantic import BaseModel, EmailStr
from typing import List, Literal
from datetime import time

class TeacherCreateRequest(BaseModel):
    first_name: str
    last_name: str
    highest_qualification: str
    university: str
    phone: str
    email: EmailStr
    teacher_in_classes: List[str]
    subjects: List[str]
    start_duty: time
    end_duty: time
    teacher_type: Literal["full_time", "part_time"]
    present_in: List[str]
class TeacherResponse(BaseModel):
    id: str
    first_name: str
    last_name: str
    highest_qualification: str
    university: str
    phone: str
    email: EmailStr
    teacher_in_classes: List[str]
    subjects: List[str]
    start_duty: time
    end_duty: time
    teacher_type: Literal["full_time", "part_time"]
    present_in: List[str]
    model_config = {
        "from_attributes": True
    }