from pydantic import BaseModel, EmailStr, HttpUrl,Field
from typing import Optional,List
from datetime import time
from datetime import date
from enum import Enum
class SchoolProfileBase(BaseModel):
    # School Information
    school_name: str
    school_type: str
    school_medium: str
    school_board: str
    establishment_year: int
    
    # Address Information
    pin_code: str
    block_division: Optional[str] = None
    district: str
    state: str
    country: Optional[str] = "India"
    
    # Contact Information
    school_email: EmailStr
    school_phone: str
    school_alt_phone: Optional[str] = None
    school_website: Optional[str] = None
    # school_website: Optional[HttpUrl] = None
    
    # Principal Information
    principal_name: str
    principal_designation: Optional[str] = None
    principal_email: Optional[EmailStr] = None
    principal_phone: Optional[str] = None

class SchoolProfileCreate(SchoolProfileBase):
    pass

class SchoolProfileOut(SchoolProfileBase):
    id: str
    user_id: int
    school_type: Optional[str] = None
    school_medium: Optional[str] = None
    school_board: Optional[str] = None
    
    model_config = {
        "from_attributes": True,
        "arbitrary_types_allowed": True  
    }

class SchoolProfileUpdate(BaseModel):
    school_type: Optional[str]
    school_medium: Optional[str]
    school_board: Optional[str]
    establishment_year: Optional[int]
    pin_code: Optional[str]
    block_division: Optional[str]
    district: Optional[str]
    state: Optional[str]
    country: Optional[str]
    # profile_pic_url:Optional[str]
    # banner_pic_url:Optional[str]
    school_alt_phone: Optional[str]
    principal_name: Optional[str]
    principal_designation: Optional[str]
    principal_email: Optional[EmailStr]
    principal_phone: Optional[str]


class ClassWithSubjectCreate(BaseModel):
    class_name: str
    sections: List[str]
    subjects: List[str]
    extra_curriculums: List[str]    
class ClassInput(BaseModel):
    mandatory_subject_ids: Optional[List[int]]
    optional_subject_ids: Optional[List[int]]
    assigned_teacher_ids: Optional[List[str]]
    extra_activity_ids: Optional[List[int]]
    start_time: time
    end_time: time    
    
class ClassOut(BaseModel):
    id: int
    class_name: str
    section: str
    start_time: Optional[time]
    end_time: Optional[time]
           

class StopBase(BaseModel):
    stop_name: str
    stop_time: time

class TransportCreate(BaseModel):
    vehicle_number: str
    vehicle_name: str
    driver_name: str
    phone_no: str
    duty_start_time: time
    duty_end_time: time
    school_id: str

    pickup_stops: List[StopBase]
    drop_stops: List[StopBase]

class StopResponse(StopBase):
    stop_name: str
    stop_time: str

class TransportResponse(BaseModel):
    id: int
    vehicle_number: str
    vehicle_name: str
    driver_name: str
    phone_no: str
    duty_start_time: time
    duty_end_time: time
    school_id: str
    pickup_stops: List[StopResponse]
    drop_stops: List[StopResponse]
    model_config = {
        "from_attributes": True
    }

class AttendanceCreate(BaseModel):
    student_id: Optional[int]=None
    teachers_id: Optional[str]
    class_id: int
    section_id: Optional[int] = None
    subject_id: int
    date: date
    status: str = Field(..., max_length=1)

    model_config = {
        "from_attributes": True
    } 
    
class WeekDay(str,Enum):
    MONDAY = "MONDAY"
    TUESDAY = "TUESDAY"
    WEDNESDAY = "WEDNESDAY"
    THURSDAY = "THURSDAY"
    FRIDAY = "FRIDAY"
    SATURDAY = "SATURDAY"    

class PeriodCreate(BaseModel):
    period_number: int
    subject_id: str
    teacher_id: Optional[str] = None
    start_time: time
    end_time: time


class TimetableCreate(BaseModel):
    class_id: int
    section_id: Optional[int] = None
    day: WeekDay
    periods: List[PeriodCreate]