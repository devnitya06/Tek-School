from pydantic import BaseModel, EmailStr, HttpUrl,Field
from typing import Optional,List,Dict
from datetime import time
from datetime import date,datetime
from enum import Enum
from fastapi import Query
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


# class ClassWithSubjectCreate(BaseModel):
#     class_name: str
#     sections: List[str]
#     subjects: List[str]
#     extra_curriculums: List[str] 
class SubjectItem(BaseModel):
    name: str
    school_class_subject_id: Optional[int] = None  # 🧩 new field for linking to global subject

class ClassWithSubjectCreate(BaseModel):
    class_name: str
    sections: List[str]
    subjects: List[SubjectItem]  # 🧠 now supports name + school_class_subject_id
    extra_curriculums: List[str]
    annual_course_fee: Optional[float] = 10000.0
    annual_transport_fee: Optional[float] = 3000.0
    tek_school_payment_annually: Optional[float] = 1000.0
    class_start_date: date
    class_end_date: date   
class ClassInput(BaseModel):
    mandatory_subject_ids: Optional[List[int]]
    optional_subject_ids: Optional[List[int]]
    assigned_teacher_ids: Optional[List[str]]
    extra_activity_ids: Optional[List[int]]
    start_time: time
    end_time: time
    annual_course_fee: Optional[float] = None
    annual_transport_fee: Optional[float] = None
    tek_school_payment_annually: Optional[float] = None    
    
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
    
class StopUpdate(BaseModel):
    id: Optional[int] = None  # existing stop id (if updating)
    stop_name: Optional[str] = None
    stop_time: Optional[time] = None


class TransportUpdate(BaseModel):
    vehicle_number: Optional[str] = None
    vehicle_name: Optional[str] = None
    driver_name: Optional[str] = None
    phone_no: Optional[str] = None
    duty_start_time: Optional[time] = None
    duty_end_time: Optional[time] = None
    pickup_stops: Optional[List[StopUpdate]] = None
    drop_stops: Optional[List[StopUpdate]] = None

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
    staff_id: Optional[str]=None
    date: date
    status: str = Field(..., max_length=1)
    is_verified:bool =Field(default=True)
    is_today_present: bool=Field(default=False)
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
    sections: Optional[List[int]] = None
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
    exam_type: Optional[ExamTypeEnum] = None
    class_id: Optional[int] = None
    section_ids: Optional[List[int]] = None
    chapters: Optional[List[int]] = None
    no_of_questions: Optional[int] = None
    question_time: Optional[int] = None
    pass_percentage: Optional[float] = None
    exam_activation_date: Optional[datetime] = None
    inactive_date: Optional[datetime] = None
    max_repeat: Optional[int] = None
    status: Optional[ExamStatusEnum] = None


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
class ExamDetailResponse(ExamListResponse):
    school_id: str
    chapters: List[int]  # override chapters type if needed
    pass_percentage: float  # override type if needed
    created_by: Optional[str] = None  # make optional if needed

class ExamPublishResponse(BaseModel):
    exam_id: str
    is_published: bool
    published_at: datetime

class ExamFilterParams(BaseModel):
    exam_name_or_id: Optional[str] = Query(None, description="Search by Exam ID or Name")
    exam_type: Optional[ExamTypeEnum] = None
    subject_id: Optional[int] = None
    teacher_name: Optional[str] = None
    from_date: Optional[datetime] = None
    to_date: Optional[datetime] = None

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

class LeaveCreate(BaseModel):
    subject: str
    start_date: date
    end_date: date
    leave_type: str
    description: Optional[str] = None
    attach_file: Optional[str] = None

class LeaveStatusUpdate(BaseModel):
    status: str
class LeaveResponse(BaseModel):
    id: int
    subject: str
    start_date: date
    end_date: date
    leave_type: str
    description: Optional[str]
    status: str
    user_id: int
    role: str

    model_config = {
        "from_attributes": True
    } 
# ---------------- Home Task ----------------
class AssignmentTaskCreate(BaseModel):
    title: str
    description: Optional[str] = None
    file: Optional[str] = None


class HomeAssignmentCreate(BaseModel):
    task_title: str
    # description: Optional[str] = None
    # file: Optional[str] = None
    task_type: str
    chapter_id: int
    tasks: List[AssignmentTaskCreate]
    student_ids: Optional[List[int]] = None

class StudentHomeTaskListResponse(BaseModel):
    id: int
    teacher_name: str
    subject_name: str
    chapter_name: str
    task_type: str
    created_at: datetime
    status: str
    no_of_tasks_completed: int
    no_of_tasks_incomplete: int

# Bank Account Schemas
class BankAccountCreate(BaseModel):
    account_holder_name: str
    account_number: str
    ifsc_code: str = Field(..., min_length=11, max_length=11, description="IFSC code must be 11 characters")
    bank_name: str
    branch_name: Optional[str] = None
    account_type: str = Field(..., pattern="^(savings|current)$", description="Account type must be 'savings' or 'current'")
    is_primary: bool = False

class BankAccountUpdate(BaseModel):
    account_holder_name: Optional[str] = None
    account_number: Optional[str] = None
    ifsc_code: Optional[str] = Field(None, min_length=11, max_length=11)
    bank_name: Optional[str] = None
    branch_name: Optional[str] = None
    account_type: Optional[str] = Field(None, pattern="^(savings|current)$")
    is_primary: Optional[bool] = None

class BankAccountResponse(BaseModel):
    id: int
    school_id: str
    account_holder_name: str
    account_number: str
    ifsc_code: str
    bank_name: str
    branch_name: Optional[str] = None
    account_type: str
    is_primary: bool
    created_at: datetime
    updated_at: datetime
    
    model_config = {
        "from_attributes": True
    }