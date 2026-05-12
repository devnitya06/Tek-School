from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import date, time
from enum import Enum
from datetime import datetime
from app.models.students import DoubtStatus, ResponseAction
class InstallmentTypeEnum(str, Enum):
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    HALF_YEARLY = "half_yearly"
    YEARLY = "yearly"

class StudentPaymentCreate(BaseModel):
    course_fee: float
    transport_fee: float
    tek_school_fee: float
    installment_type: InstallmentTypeEnum

class StudentPaymentUpdate(BaseModel):
    course_fee: Optional[float] = None
    transport_fee: Optional[float] = None
    tek_school_fee: Optional[float] = None
    installment_type: Optional[InstallmentTypeEnum] = None
    # Payment clear amounts (how much has been paid)
    course_fee_paid: Optional[float] = None
    transport_fee_paid: Optional[float] = None
    tek_school_fee_paid: Optional[float] = None
    # Payment documents and description (optional)
    files: Optional[List[str]] = None  # List of base64 encoded files (payslips, receipts, etc.)
    description: Optional[str] = None  # Description/notes about the payment
    # Bank account selection
    bank_account_id: Optional[int] = Field(None, description="Bank account ID to use for this payment (optional)")

class PaymentTransactionCreate(BaseModel):
    """Schema for creating payment transaction(s).
    You can pay one, two, or all three fees in a single request.
    At least one payment amount must be provided.
    """
    # Optional amounts for each fee type - at least one must be provided
    course_fee_amount: Optional[float] = None  # Amount to pay for course fee
    transport_fee_amount: Optional[float] = None  # Amount to pay for transport fee
    tek_school_fee_amount: Optional[float] = None  # Amount to pay for tek school fee
    

    description: Optional[str] = None  # Description/notes about the payment
    files: Optional[List[str]] = None  # List of base64 encoded files (payslips, receipts, etc.)
    payment_method: Optional[str] = None  # "cash", "bank_transfer", "cheque", etc.
    transaction_reference: Optional[str] = None  # Transaction ID, cheque number, etc.
    bank_account_id: Optional[int] = Field(
        default=None,
        description="School bank account receiving this fee; omit for cash (offline) ledger.",
    )

class PaymentReminderRequest(BaseModel):
    """Schema for school to send payment reminder to student"""
    message: Optional[str] = Field(None, max_length=1000, description="Optional custom message")
    amount_due: Optional[float] = Field(None, ge=0, description="Optional amount due information")
    # Fee fields for the payment request
    course_fee: Optional[float] = Field(None, ge=0, description="Course fee amount for this payment request")
    transport_fee: Optional[float] = Field(None, ge=0, description="Transport fee amount for this payment request")
    tek_school_fee: Optional[float] = Field(None, ge=0, description="Tek School fee amount for this payment request")
    installment_type: Optional[InstallmentTypeEnum] = Field(None, description="Installment type (applies to all fees)")
    # Bank account selection
    bank_account_id: Optional[int] = Field(None, description="Bank account ID to use for this payment (optional)")

class BulkPaymentReminderRequest(BaseModel):
    """Schema for school to send payment reminders to multiple students"""
    student_ids: List[int] = Field(..., min_items=1, description="List of student IDs to send reminders to")
    message: Optional[str] = Field(None, max_length=1000, description="Optional custom message for all reminders")
    bank_account_id: Optional[int] = Field(None, description="Bank account ID to use for all reminders (optional)")

class StudentPaymentSubmit(BaseModel):
    """Schema for student to update payment transaction (pending verification)"""
    # Optional amounts for each fee type - at least one must be provided
    course_fee_amount: Optional[float] = Field(None, gt=0, description="Amount to pay for course fee (must be > 0)")
    transport_fee_amount: Optional[float] = Field(None, gt=0, description="Amount to pay for transport fee (must be > 0)")
    tek_school_fee_amount: Optional[float] = Field(None, gt=0, description="Amount to pay for tek school fee (must be > 0)")
    
    # Common fields
    description: Optional[str] = Field(None, max_length=500, description="Payment description/notes")
    files: Optional[List[str]] = Field(None, max_items=10, description="List of base64 encoded files (receipts, payslips, etc.) - max 10 files")
    payment_method: Optional[str] = Field(None, max_length=50, description="Payment method: cash, bank_transfer, cheque, etc.")
    transaction_reference: Optional[str] = Field(None, max_length=100, description="Transaction ID, cheque number, etc.")
    bank_account_id: Optional[int] = Field(
        default=None,
        description="School bank account where fee was paid; omit for cash (offline).",
    )

class PaymentVerificationRequest(BaseModel):
    """Schema for school to verify (done) or cancel payment request"""
    status: str = Field(..., pattern="^(done|cancel)$", description="Status must be 'done' (verify and calculate amounts) or 'cancel' (cancel the request)")
    rejection_reason: Optional[str] = Field(None, max_length=500, description="Required if status is 'cancel'")

class StudentCreateRequest(BaseModel):
    profile_image:Optional[str]=None
    first_name: str
    last_name: str
    gender: str
    dob: date
    email: EmailStr
    roll_no: int
    registration_no: Optional[str] = None
    class_id: int
    section_id: int
    select_class_id: Optional[int] = None
    is_transport: bool = True
    driver_id: Optional[int] = None
    pickup_point: Optional[str] = None
    pickup_time: Optional[str] = None
    drop_point: Optional[str] = None
    drop_time: Optional[str] = None
    blood_group: Optional[str] = None
    date_of_admission: Optional[date] = None
    previous_class_marks_obtained: Optional[int] = None
    previous_class_overall_percentage: Optional[float] = None
    previous_class_final_grade: Optional[str] = None
    payment: StudentPaymentCreate
    # school_id: str

class StudentUpdateRequest(BaseModel):
    profile_image: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    gender: Optional[str] = None
    dob: Optional[date] = None
    select_class_id: Optional[int] = None
    class_id: Optional[int] = None
    section_id: Optional[int] = None
    is_transport: Optional[bool] = None
    driver_id: Optional[int] = None
    pickup_point: Optional[str] = None
    pickup_time: Optional[str] = None
    drop_point: Optional[str] = None
    drop_time: Optional[str] = None
    blood_group: Optional[str] = None
    date_of_admission: Optional[date] = None
    previous_class_marks_obtained: Optional[int] = None
    previous_class_overall_percentage: Optional[float] = None
    previous_class_final_grade: Optional[str] = None
    payment: Optional[StudentPaymentCreate] = None  # Optional payment update

class AddressBase(BaseModel):
    enter_pin: str
    division: Optional[str] = None
    district: str
    state: str
    country: str
    building: Optional[str] = None
    house_no: Optional[str] = None
    floor_name: Optional[str] = None

class PresentAddressCreate(AddressBase):
    is_this_permanent_as_well: bool = False

class PermanentAddressCreate(AddressBase):
    pass

class ParentCreate(BaseModel):
    parent_name: str
    relation: str 
    phone: str
    email: EmailStr
    occupation: Optional[str] = None
    education: Optional[str] = None
    organization: Optional[str] = None

class ParentWithAddressCreate(BaseModel):
    parent: ParentCreate
    present_address: PresentAddressCreate
    permanent_address: Optional[PermanentAddressCreate] = None    

# ---------------- Parent ----------------
class ParentUpdate(BaseModel):
    parent_name: Optional[str] = None
    relation: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    occupation: Optional[str] = None
    education: Optional[str] = None
    organization: Optional[str] = None

# ---------------- Address Base ----------------
class AddressBaseUpdate(BaseModel):
    enter_pin: Optional[str] = None
    division: Optional[str] = None
    district: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    building: Optional[str] = None
    house_no: Optional[str] = None
    floor_name: Optional[str] = None

# ---------------- Present Address ----------------
class PresentAddressUpdate(AddressBaseUpdate):
    is_this_permanent_as_well: Optional[bool] = None

# ---------------- Permanent Address ----------------
class PermanentAddressUpdate(AddressBaseUpdate):
    pass

# ---------------- Wrapper ----------------
class ParentWithAddressUpdate(BaseModel):
    parent: Optional[ParentUpdate] = None
    present_address: Optional[PresentAddressUpdate] = None
    permanent_address: Optional[PermanentAddressUpdate] = None

class SelfSignedStudentUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    profile_image: Optional[str] = None
    select_board: Optional[str] = None
    select_class_id: Optional[int] = None
    school_name: Optional[str] = None
    school_location: Optional[str] = None

    pin: Optional[int] = None
    division: Optional[str] = None
    district: Optional[str] = None
    state: Optional[str] = None
    plot: Optional[str] = None

    parent_name : Optional[str] = None
    relation : Optional[str] = None
    parent_phone : Optional[str] = None
    parent_email : Optional[EmailStr] = None
    occupation : Optional[str] = None

class CreateDoubtRequest(BaseModel):
    subject_id: int
    chapter_name: str = Field(..., max_length=255)
    question: str
    key_points: Optional[str] = None
    attachment: Optional[str] = None
    teacher_ids: List[str]

class RespondDoubtRequest(BaseModel):
    answer: str
    attachment: Optional[str] = None
    action: ResponseAction

class UpdateDoubtStatusRequest(BaseModel):
    status: DoubtStatus

class TeacherSelectionResponse(BaseModel):
    teacher_id: str
    name: str
    type: str  # In-Class / In-School
    subject: str
    class_name: str
    section_name: str
    pending_doubt_count: int

class DoubtListResponse(BaseModel):
    id: int
    subject: str
    chapter_name: str
    question: str
    status: DoubtStatus
    created_at: datetime

class StudentDashboardResponse(BaseModel):
    total_doubts: int
    responses_received: int
    solved_doubts: int
    unsolved_doubts: int
    pending_doubts: int

class TeacherDashboardResponse(BaseModel):
    total_doubts: int
    responded_doubts: int
    solved_ratio: float

class StudentInfo(BaseModel):
    name: str
    class_name: str
    section_name: str
    school: str


class DoubtDetailResponse(BaseModel):
    id: int
    student: StudentInfo
    subject: str
    chapter_name: str
    question: str
    key_points: Optional[str]
    attachment: Optional[str]
    status: DoubtStatus
    created_at: datetime

class TeacherResponseView(BaseModel):
    teacher_name: str
    answer: str
    attachment: Optional[str]
    action: ResponseAction
    created_at: datetime

class TeacherNameResponse(BaseModel):
    teacher_id: str
    teacher_name: str


class StudentDoubtListResponse(BaseModel):
    id: int
    subject: str
    chapter_name: str
    question: str
    teachers: List[TeacherNameResponse]
    status: str
    created_at: datetime