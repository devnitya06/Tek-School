from pydantic import BaseModel, EmailStr, HttpUrl
from typing import Optional,List
from datetime import time

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
    school_type: Optional[str] = None  # Make optional to match SQLAlchemy
    school_medium: Optional[str] = None
    school_board: Optional[str] = None
    
    model_config = {
        "from_attributes": True,
        "arbitrary_types_allowed": True  # Allows handling of SQLAlchemy enums
    }

class SchoolProfileUpdate(BaseModel):
    # All fields optional for PATCH
    # school_name: Optional[str] = None
    school_type: Optional[str] = None
    school_medium: Optional[str] = None
    school_board: Optional[str] = None
    establishment_year: Optional[int] = None
    pin_code: Optional[str] = None
    block_division: Optional[str] = None
    district: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    # school_email: Optional[EmailStr] = None
    # school_phone: Optional[str] = None
    school_alt_phone: Optional[str] = None
    # school_website: Optional[HttpUrl] = None
    principal_name: Optional[str] = None
    principal_designation: Optional[str] = None
    principal_email: Optional[EmailStr] = None
    principal_phone: Optional[str] = None

    
class ClassInput(BaseModel):
    class_name: str
    sections: List[str]
    mandatory_subjects: List[str]
    optional_subjects: Optional[List[str]] = []
    extra_curriculums: Optional[List[str]] = []
    teacher_ids: List[str]
    start_time: time
    end_time: time    
    
class ClassOut(BaseModel):
    id: int
    class_name: str
    section: str
    start_time: Optional[time]
    end_time: Optional[time]
           