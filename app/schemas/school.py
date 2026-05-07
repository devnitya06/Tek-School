from pydantic import BaseModel, EmailStr, HttpUrl, Field, field_validator
from typing import Optional, List, Dict, Literal
from datetime import time
from datetime import date, datetime
from enum import Enum
from fastapi import Query
from app.models.school import *


class SchoolProfileBase(BaseModel):
    # School Information
    school_name: str
    school_type: str
    school_medium: str
    school_board: str
    establishment_year: int
    establishment_month: Optional[int] = None
    register_no: Optional[str] = None

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

    model_config = {"from_attributes": True, "arbitrary_types_allowed": True}


class SchoolProfileUpdate(BaseModel):
    school_name: Optional[str] = None
    school_type: Optional[str] = None
    school_medium: Optional[str] = None
    school_board: Optional[str] = None
    establishment_year: Optional[int] = None
    establishment_month: Optional[int] = None
    register_no: Optional[str] = None
    pin_code: Optional[str] = None
    block_division: Optional[str] = None
    district: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    school_email: Optional[str] = None
    school_phone: Optional[str] = None
    school_alt_phone: Optional[str] = None
    school_website: Optional[str] = None
    principal_name: Optional[str] = None
    principal_designation: Optional[str] = None
    principal_email: Optional[EmailStr] = None
    principal_phone: Optional[str] = None
    school_other_email: Optional[str] = None
    school_location: Optional[str] = None
    total_teachers: Optional[int] = None
    total_students: Optional[int] = None
    class_from: Optional[str] = None
    class_to: Optional[str] = None
    due_installment_type: Optional[List[str]] = None
    transportation_facility: Optional[bool] = None
    playground_facility: Optional[bool] = None
    teaching_method: Optional[List[str]] = None
    catalogue: Optional[List[str]] = None
    photo_gallery: Optional[List[str]] = None
    school_logo: Optional[str] = (
        None  # URL or base64 data URL (data:image/...;base64,...)
    )


class SubjectItem(BaseModel):
    name: str
    school_class_subject_id: Optional[int] = (
        None  # 🧩 new field for linking to global subject
    )


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


class ClassWithSubjectUpdate(BaseModel):
    class_name: Optional[str] = None

    sections: Optional[List[str]] = None
    subjects: Optional[List[SubjectItem]] = None
    extra_curriculums: Optional[List[str]] = None

    annual_course_fee: Optional[float] = None
    annual_transport_fee: Optional[float] = None
    tek_school_payment_annually: Optional[float] = None

    class_start_date: Optional[date] = None
    class_end_date: Optional[date] = None


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
    model_config = {"from_attributes": True}


class AttendanceCreate(BaseModel):
    student_id: Optional[int] = None
    teachers_id: Optional[str] = None
    staff_id: Optional[str] = None
    date: date
    status: Optional[str] = Field(
        None,
        max_length=1,
        description="Required for student/staff single-shot attendance; for teachers, required unless using mark_in/mark_out.",
    )
    action: Optional[Literal["mark_in", "mark_out"]] = Field(
        None,
        description="Teacher/staff attendance only: mark_in (present) / optional mark_out. Ignored for students.",
    )
    mark_in_at: Optional[datetime] = None
    mark_out_at: Optional[datetime] = None
    is_verified: bool = Field(default=True)
    is_today_present: bool = Field(default=False)
    model_config = {"from_attributes": True}


class TeacherAttendanceVerifyBody(BaseModel):
    """Optional times the school accepts when verifying teacher attendance."""

    mark_in_at: Optional[datetime] = None
    mark_out_at: Optional[datetime] = None

    model_config = {
        "from_attributes": True,
    }


class AttendanceBulkApproveRequest(BaseModel):
    attendance_ids: List[int] = Field(
        ...,
        min_length=1,
        description="Attendance record IDs to approve in bulk.",
    )

    model_config = {
        "from_attributes": True,
    }


class AttendanceQRCheckinRequest(BaseModel):
    token: str = Field(..., min_length=8)

    model_config = {
        "from_attributes": True,
    }


class WeekDay(str, Enum):
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
    model_config = {"from_attributes": True}


class PeriodUpdate(BaseModel):
    subject_id: Optional[int] = None
    teacher_id: Optional[str] = None
    start_time: Optional[time] = None
    end_time: Optional[time] = None


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


class ExamCreateRequest(BaseModel):
    class_id: Optional[int] = None
    selected_class_id: Optional[int] = None
    subject_id: Optional[int] = None
    section_ids: List[int] = None
    chapters: List[int] = None
    exam_type: ExamTypeEnum
    evaluation_scope: Optional[EvaluationScopeEnum] = None
    # total_marks: int
    pass_percentage: int
    question_time: Optional[int] = None
    exam_description: Optional[str] = None
    exam_activation_date: datetime
    inactive_date: Optional[datetime] = None
    max_repeat: Optional[int] = 1


class ExamUpdateRequest(BaseModel):
    class_id: Optional[int] = None
    subject_id: Optional[int] = None
    selected_class_id: Optional[int] = None
    section_ids: Optional[List[int]] = None
    chapters: Optional[List[int]] = None

    exam_type: Optional[ExamTypeEnum] = None
    evaluation_scope: Optional[EvaluationScopeEnum] = None

    total_marks: Optional[int] = None
    pass_percentage: Optional[int] = None

    question_time: Optional[int] = None
    exam_description: Optional[str] = None

    exam_activation_date: Optional[datetime] = None
    inactive_date: Optional[datetime] = None

    max_repeat: Optional[int] = None
    status: Optional[ExamStatusEnum] = None


class ExamListResponse(BaseModel):
    id: str
    # is_published: bool
    exam_type: ExamTypeEnum
    class_id: Optional[int] = None
    selected_class_id: Optional[int] = None
    standard: Optional[str] = None
    subject_id: Optional[int] = None
    subject_name: Optional[str] = None
    section_ids: List[int]
    section_names: List[str]
    chapters: List[int]
    no_of_chapters: int
    total_marks: int
    no_of_questions: int
    question_time: Optional[int] = None
    pass_percentage: int
    exam_activation_date: datetime
    inactive_date: Optional[datetime]
    max_repeat: int
    status: ExamStatusEnum
    no_students_appeared: int
    created_by: Optional[str] = None
    created_by_admin: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class ExamDetailResponse(BaseModel):
    id: str
    is_published: bool

    exam_type: ExamTypeEnum
    evaluation_scope: Optional[EvaluationScopeEnum] = None

    school_id: Optional[str] = None
    school_name: Optional[str] = None

    class_id: Optional[int] = None
    selected_class_id: Optional[int] = None
    standard: Optional[str] = None

    subject_id: Optional[int] = None
    subject_name: Optional[str] = None

    section_ids: List[int]
    section_names: List[str]

    chapters: List[int]
    no_of_chapters: int

    total_marks: int
    no_of_questions: int

    question_time: Optional[int] = None
    pass_percentage: float

    exam_description: Optional[str] = None

    exam_activation_date: datetime
    inactive_date: Optional[datetime] = None

    max_repeat: int
    status: ExamStatusEnum

    no_students_appeared: int
    attempt_no: Optional[int] = None
    created_by: Optional[str] = None
    created_by_admin: bool
    created_at: datetime


class ExamQuestionOptionCreate(BaseModel):
    option_text: str
    is_correct: bool


class ExamQuestionCreate(BaseModel):
    question_type: QuestionTypeEnum
    question_text: str
    marks: int
    image: Optional[str] = None
    # For SHORT
    correct_text_answer: Optional[str] = None
    # For LONG
    answer_keywords: Optional[List[str]] = None
    # For MCQ
    options: Optional[List["ExamQuestionOptionCreate"]] = None


class ExamQuestionOptionUpdate(BaseModel):
    option_text: Optional[str] = None
    is_correct: Optional[bool] = None


class ExamQuestionUpdate(BaseModel):
    question_type: Optional[QuestionTypeEnum] = None
    question_text: Optional[str] = None
    marks: Optional[int] = None
    image: Optional[str] = None
    correct_text_answer: Optional[str] = None
    answer_keywords: Optional[List[str]] = None

    options: Optional[List[ExamQuestionOptionUpdate]] = None


class AnswerSchema(BaseModel):
    question_id: int
    # For MCQ
    selected_option_id: Optional[int] = None
    # For SHORT / LONG
    descriptive_answer: Optional[str] = None


class ExamQuestionOptionResponse(BaseModel):
    id: int
    option_text: str

    model_config = {"from_attributes": True}


class ExamQuestionResponse(BaseModel):
    id: int
    question_type: QuestionTypeEnum
    question_text: str
    marks: int
    image: Optional[str] = None

    options: Optional[List[ExamQuestionOptionResponse]] = None

    model_config = {"from_attributes": True}


class StudentExamSubmitRequest(BaseModel):
    answers: List[AnswerSchema]


class ExamPublishResponse(BaseModel):
    exam_id: str
    is_published: bool
    published_at: datetime


class ExamFilterParams(BaseModel):
    exam_name_or_id: Optional[str] = Query(
        None, description="Search by Exam ID or Name"
    )
    exam_type: Optional[ExamTypeEnum] = None
    subject_id: Optional[int] = None
    teacher_name: Optional[str] = None
    from_date: Optional[datetime] = None
    to_date: Optional[datetime] = None
    class_name: Optional[str] = None


# class McqCreate(BaseModel):
#     question: str
#     mcq_type: str = Field(..., pattern="^(1|2)$")
#     image: Optional[str] = None
#     option_a: str
#     option_b: str
#     option_c: str
#     option_d: str
#     correct_option: List[str]  # ["A"] or ["A","C"]

# class McqBulkCreate(BaseModel):
#     mcqs: List[McqCreate]


class ExamStatusUpdateRequest(BaseModel):
    status: ExamStatusEnum


# class AnswerSchema(BaseModel):
#     question_id: int
#     selected_option: str

# class StudentExamSubmitRequest(BaseModel):
#     answers: List[AnswerSchema]
# class McqResponse(McqCreate):
#     id: int
#     exam_id: str

#     model_config = {
#         "from_attributes": True
#     }


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

    model_config = {"from_attributes": True}


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
    ifsc_code: str = Field(
        ..., min_length=11, max_length=11, description="IFSC code must be 11 characters"
    )
    bank_name: str
    branch_name: Optional[str] = None
    account_type: str = Field(
        ...,
        pattern="^(savings|current)$",
        description="Account type must be 'savings' or 'current'",
    )
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

    model_config = {"from_attributes": True}


class SchoolSettlementTransactionResponse(BaseModel):
    """One ledger row: bank account or cash (offline)."""

    id: int
    school_id: str
    settlement_channel: str
    bank_account_id: Optional[int] = None
    amount: float = Field(
        ...,
        description="Signed: negative when school pays out (salary), positive when fee is credited.",
    )
    direction: str
    category: Optional[str] = None
    source_reference: Optional[str] = None
    description: Optional[str] = None
    recorded_by_user_id: Optional[int] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class BankAccountWithTransactionsResponse(BankAccountResponse):
    """Bank account plus all settlement rows tied to this account."""

    transactions: List[SchoolSettlementTransactionResponse] = Field(
        default_factory=list,
        description="History of amounts recorded against this bank account.",
    )


class BankAccountsOverviewResponse(BaseModel):
    """
    School finance overview: default channel is cash until bank accounts exist;
    each bank account lists its own transaction history; cash uses a virtual bucket.
    """

    default_settlement_channel: str = Field(
        ...,
        description="Preferred default: 'cash_offline' or 'bank_account'. New schools start as cash_offline.",
    )
    cash_offline: dict = Field(
        ...,
        description="Virtual 'Cash (offline)' bucket and its transaction history.",
    )
    bank_accounts: List[BankAccountWithTransactionsResponse] = Field(
        default_factory=list,
        description="Configured bank accounts, each with transaction history.",
    )


class CashDepositCreate(BaseModel):
    payment_title: str
    deposite_amount: float = Field(..., gt=0)
    bank_acount: int = Field(..., description="Target bank account id")
    associate_in_payment: Optional[str] = None
    payment_description: Optional[str] = None
    depositor_name: str
    deposite_date: Optional[datetime] = None
    attached_file: Optional[str] = Field(
        default=None,
        description="Optional base64 file (image/pdf). Uploaded to S3 and stored as URL.",
    )


class CashDepositResponse(BaseModel):
    id: int
    school_id: str
    bank_account_id: int
    payment_title: str
    deposite_amount: float
    associate_in_payment: Optional[str] = None
    payment_description: Optional[str] = None
    depositor_name: str
    deposite_date: datetime
    attached_file: Optional[str] = None
    created_by: Optional[int] = None
    created_at: Optional[datetime] = None
    bank_account: Optional[BankAccountResponse] = None

    model_config = {"from_attributes": True}


# Promotion Account Schemas
class PromoteAccountRequest(BaseModel):
    pass  # No additional data needed, just triggers request


class PromoteAccountResponse(BaseModel):
    detail: str
    status: str  # "pending", "approved", "rejected"


# ListedSchoolStudent Schemas (school listing students)
class ListedSchoolStudentCreate(BaseModel):
    student_name: str
    gender: Optional[str] = None
    phone_no: Optional[str] = None
    email_id: Optional[str] = None
    class_name: Optional[str] = None
    batch_of_student: Optional[str] = None
    secured_mark_in_percentage: Optional[float] = Field(None, ge=0, le=100)
    profile_picture: Optional[str] = None  # URL or base64 for upload


class ListedSchoolStudentUpdate(BaseModel):
    student_name: Optional[str] = None
    gender: Optional[str] = None
    phone_no: Optional[str] = None
    email_id: Optional[str] = None
    class_name: Optional[str] = None
    batch_of_student: Optional[str] = None
    secured_mark_in_percentage: Optional[float] = Field(None, ge=0, le=100)
    profile_picture: Optional[str] = None


class ListedSchoolStudentResponse(BaseModel):
    id: int
    school_id: str
    student_name: str
    gender: Optional[str] = None
    phone_no: Optional[str] = None
    email_id: Optional[str] = None
    class_name: Optional[str] = None
    batch_of_student: Optional[str] = None
    secured_mark_in_percentage: Optional[float] = None
    profile_picture: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# SchoolInfo (one-to-one with School): admission path, vision, mission, about us
class SchoolInfoCreate(BaseModel):
    school_id: Optional[str] = (
        None  # Required for super admin; ignored for school (uses own school)
    )
    admission_path: Optional[str] = None
    vision: Optional[str] = None
    mission: Optional[str] = None
    about_us: Optional[str] = None


class SchoolInfoUpdate(BaseModel):
    admission_path: Optional[str] = None
    vision: Optional[str] = None
    mission: Optional[str] = None
    about_us: Optional[str] = None


class SchoolInfoResponse(BaseModel):
    id: int
    school_id: str
    admission_path: Optional[str] = None
    vision: Optional[str] = None
    mission: Optional[str] = None
    about_us: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# SchoolClassFee: under school - class name, admission fee, course fee, transport fee
class SchoolClassFeeCreate(BaseModel):
    school_id: Optional[str] = None  # Required for super admin; ignored for school
    class_name: str
    admission_fee: Optional[float] = Field(None, ge=0)
    course_fee: Optional[float] = Field(None, ge=0)
    transport_fee: Optional[float] = Field(None, ge=0)


class SchoolClassFeeUpdate(BaseModel):
    class_name: Optional[str] = None
    admission_fee: Optional[float] = Field(None, ge=0)
    course_fee: Optional[float] = Field(None, ge=0)
    transport_fee: Optional[float] = Field(None, ge=0)


class SchoolClassFeeResponse(BaseModel):
    id: int
    school_id: str
    class_name: str
    admission_fee: Optional[float] = None
    course_fee: Optional[float] = None
    transport_fee: Optional[float] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# SchoolTeamMember: name, designation, school_id, member_story, profile_picture
class SchoolTeamMemberCreate(BaseModel):
    school_id: Optional[str] = None  # Required for super admin; ignored for school
    name: str
    designation: Optional[str] = None
    member_story: Optional[str] = None
    profile_picture: Optional[str] = None  # URL


class SchoolTeamMemberUpdate(BaseModel):
    name: Optional[str] = None
    designation: Optional[str] = None
    member_story: Optional[str] = None
    profile_picture: Optional[str] = None


class SchoolTeamMemberResponse(BaseModel):
    id: int
    school_id: str
    name: str
    designation: Optional[str] = None
    member_story: Optional[str] = None
    profile_picture: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ExcellentStudent: school_id, school_name, gender, student_photo, phone_no, email, class_name, batch_of_student, secure_mark
class ExcellentStudentCreate(BaseModel):
    school_id: Optional[str] = None
    school_name: Optional[str] = None
    gender: Optional[str] = None
    phone_no: Optional[str] = None
    email: Optional[str] = None
    class_name: Optional[str] = None
    batch_of_student: Optional[str] = None
    secure_mark: Optional[float] = Field(None, ge=0, le=100)


class ExcellentStudentUpdate(BaseModel):
    school_name: Optional[str] = None
    gender: Optional[str] = None
    phone_no: Optional[str] = None
    email: Optional[str] = None
    class_name: Optional[str] = None
    batch_of_student: Optional[str] = None
    secure_mark: Optional[float] = Field(None, ge=0, le=100)


class ExcellentStudentResponse(BaseModel):
    id: int
    school_id: str
    school_name: Optional[str] = None
    gender: Optional[str] = None
    student_photo: Optional[str] = None
    phone_no: Optional[str] = None
    email: Optional[str] = None
    class_name: Optional[str] = None
    batch_of_student: Optional[str] = None
    secure_mark: Optional[float] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class BackupUserResponse(BaseModel):
    user_id: str | int
    name: str
    role: str
    enrolled_date: date | None
    session: str | None
    record_date: datetime | None
    updated_by: str | None


# SchoolRating: any user can submit rating/feedback for a listed school
class SchoolRatingCreate(BaseModel):
    school_id: str
    user_name: str = Field(..., min_length=1, max_length=200)
    user_role: Literal["visitor", "student", "parent"] = Field(
        ..., description="One of: visitor, student, parent"
    )
    mobile: str = Field(..., min_length=1, max_length=20)
    email_id: EmailStr
    feedback: Optional[str] = None
    rating: int = Field(..., ge=1, le=5, description="Rating from 1 to 5 stars")


class SchoolRatingResponse(BaseModel):
    id: int
    school_id: str
    user_name: str
    user_role: str
    mobile: str
    email_id: str
    feedback: Optional[str] = None
    rating: int
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# Support Plus: school creates; admin updates status
class SupportPlusCreate(BaseModel):
    looking_for: str = Field(..., max_length=255)
    whatsapp_number: str = Field(..., max_length=20)
    discussion_datetime: datetime
    message: Optional[str] = None


class SupportPlusResponse(BaseModel):
    id: int
    school_id: str
    looking_for: str
    whatsapp_number: str
    discussion_datetime: datetime
    files: Optional[List[str]] = None
    message: Optional[str] = None
    status: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class SupportPlusStatusUpdate(BaseModel):
    status: Literal["pending", "in_progress", "resolved", "cancelled"]


# Business Inquiry: visitor (non-authenticated) submits; school sees own; admin sees all
class BusinessInquiryResponse(BaseModel):
    id: int
    school_ids: List[str]
    guardian_name: str
    phone: str
    email: str
    location: Optional[str] = None
    student_name: Optional[str] = None
    standard_in_academic: Optional[str] = None
    inquiry_for_class: Optional[List[str]] = None
    desire_to_know: Optional[List[str]] = None
    files: Optional[List[str]] = None
    message: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class BusinessInquiryListFilter(BaseModel):
    """Query filters for listing inquiries."""

    school_id: Optional[str] = (
        None  # filter by one school (admin) or scopes to that school (school)
    )
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None


class SchoolHolidaySelectRequest(BaseModel):
    holiday_ids: List[int] = Field(..., min_length=1)

    @field_validator("holiday_ids")
    @classmethod
    def validate_ids(cls, v):
        if len(set(v)) != len(v):
            raise ValueError("Duplicate holiday IDs are not allowed")

        if any(i <= 0 for i in v):
            raise ValueError("Holiday IDs must be positive integers")

        return v


class SchoolHolidayResponse(BaseModel):
    id: int
    holiday_master_id: int
    name: str = Field(..., max_length=255)
    type: str = Field(..., max_length=100)
    date: date
    file: Optional[str] = None
    description: Optional[str] = None

    class Config:
        from_attributes = True
