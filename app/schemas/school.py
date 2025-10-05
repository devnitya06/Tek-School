from pydantic import BaseModel, EmailStr, HttpUrl,Field
from typing import Optional,List,Dict
from datetime import time
from datetime import date,datetime
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
    pickup_stops: List[StopBase]
    drop_stops: List[StopBase]

class StopResponse(StopBase):
    stop_name: str
    stop_time: str

class TransportResponse(BaseModel):
    driver_id: int
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
    teachers_id: Optional[str]=None
    date: date
    status: str = Field(..., max_length=1)
    is_verified:bool =Field(default=True)

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
    # period_number: int
    subject_id: int
    teacher_id: Optional[str] = None
    start_time: time
    end_time: time


class TimetableCreate(BaseModel):
    class_id: int
    section_id: Optional[int] = None
    day: WeekDay
    periods: List[PeriodCreate]

class TimetableUpdate(BaseModel):
    day: Optional[WeekDay] = None
    periods: Optional[List[PeriodCreate]] = None
    model_config = {
        "from_attributes": True
    }
class CreateSchoolCredit(BaseModel):
    class_id: int
    credit_configuration_id: int
    margin_value: int    

class TransferSchoolCredit(BaseModel):
    receiver_school_id: str
    credit_amount: int

class CreatePaymentRequest(BaseModel):
    amount: float

class PaymentVerificationRequest(BaseModel):
    razorpay_payment_id: str
    razorpay_order_id: str
    razorpay_signature: str
    amount: float            
class ExamTypeEnum(str, Enum):
    MOCK = "mock"
    RANK = "rank"
class ExamStatusEnum(str, Enum):
    ACTIVE = "active"
    PENDING = "pending"
    EXPIRED = "expired"
    DECLINED = "declined"
class ExamCreateRequest(BaseModel):
    class_id: int
    sections: List[int]
    chapters: List[int]
    exam_type: ExamTypeEnum
    no_of_questions: int
    question_time: int
    pass_percentage: int
    exam_activation_date: datetime
    inactive_date: Optional[datetime] = None
    max_repeat: Optional[int] = 1
    status: Optional[ExamStatusEnum] = ExamStatusEnum.PENDING

class ExamUpdateRequest(BaseModel):
    exam_type: Optional[str] = None
    class_id: Optional[str] = None
    section_ids: Optional[List[str]] = None
    chapters: Optional[List[str]] = None
    no_of_questions: Optional[int] = None
    pass_percentage: Optional[float] = None
    exam_activation_date: Optional[datetime] = None
    inactive_date: Optional[datetime] = None
    max_repeat: Optional[int] = None
    status: Optional[str] = None


class ExamListResponse(BaseModel):
    id: str
    exam_type: ExamTypeEnum
    class_id: int
    standard: str
    section_ids: List[int]
    section_names: List[str]
    chapters: List[int]
    no_of_chapters: int
    no_of_questions: int
    exam_time : Optional[int] = None
    pass_percentage: int
    exam_activation_date: datetime
    inactive_date: Optional[datetime]
    max_repeat: int
    status: ExamStatusEnum
    no_students_appeared: int
    created_by: str
    created_at: datetime
    model_config = {
        "from_attributes": True
    } 

class ExamPublishResponse(BaseModel):
    exam_id: str
    is_published: bool
    published_at: datetime

class McqCreate(BaseModel):
    question: str
    mcq_type: str = Field(..., pattern="^(1|2)$") 
    image: Optional[str] = None
    option_a: str
    option_b: str
    option_c: str
    option_d: str
    correct_option: List[str]  # ["A"] or ["A","C"]

class McqBulkCreate(BaseModel):
    mcqs: List[McqCreate]

class ExamStatusUpdateRequest(BaseModel):
    status: ExamStatusEnum

class AnswerSchema(BaseModel):
    question_id: int
    selected_option: str  

class StudentExamSubmitRequest(BaseModel):
    answers: List[AnswerSchema]
class McqResponse(McqCreate):
    id: int
    exam_id: str

    model_config = {
        "from_attributes": True
    } 