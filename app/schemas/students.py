from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import date, time
from enum import Enum

class InstallmentTypeEnum(str, Enum):
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    HALF_YEARLY = "half_yearly"
    YEARLY = "yearly"

class StudentPaymentCreate(BaseModel):
    course_fee: float
    course_fee_installment_type: InstallmentTypeEnum
    transport_fee: float
    transport_fee_installment_type: InstallmentTypeEnum
    tek_school_fee: float
    tek_school_fee_installment_type: InstallmentTypeEnum

class StudentPaymentUpdate(BaseModel):
    course_fee: Optional[float] = None
    course_fee_installment_type: Optional[InstallmentTypeEnum] = None
    transport_fee: Optional[float] = None
    transport_fee_installment_type: Optional[InstallmentTypeEnum] = None
    tek_school_fee: Optional[float] = None
    tek_school_fee_installment_type: Optional[InstallmentTypeEnum] = None
    # Payment clear amounts (how much has been paid)
    course_fee_paid: Optional[float] = None
    transport_fee_paid: Optional[float] = None
    tek_school_fee_paid: Optional[float] = None
    # Payment documents and description (optional)
    files: Optional[List[str]] = None  # List of base64 encoded files (payslips, receipts, etc.)
    description: Optional[str] = None  # Description/notes about the payment

class PaymentTransactionCreate(BaseModel):
    """Schema for creating payment transaction(s).
    You can pay one, two, or all three fees in a single request.
    At least one payment amount must be provided.
    """
    # Optional amounts for each fee type - at least one must be provided
    course_fee_amount: Optional[float] = None  # Amount to pay for course fee
    transport_fee_amount: Optional[float] = None  # Amount to pay for transport fee
    tek_school_fee_amount: Optional[float] = None  # Amount to pay for tek school fee
    
    # Common fields for all transactions
    description: Optional[str] = None  # Description/notes about the payment
    files: Optional[List[str]] = None  # List of base64 encoded files (payslips, receipts, etc.)
    payment_method: Optional[str] = None  # "cash", "bank_transfer", "cheque", etc.
    transaction_reference: Optional[str] = None  # Transaction ID, cheque number, etc.

class StudentCreateRequest(BaseModel):
    profile_image:Optional[str]=None
    first_name: str
    last_name: str
    gender: str
    dob: date
    email: EmailStr
    roll_no: int
    class_id: int
    section_id: int
    is_transport: bool = True
    driver_id: Optional[int] = None
    pickup_point: Optional[str] = None
    pickup_time: Optional[str] = None
    drop_point: Optional[str] = None
    drop_time: Optional[str] = None
    payment: StudentPaymentCreate
    # school_id: str

class StudentUpdateRequest(BaseModel):
    profile_image: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    gender: Optional[str] = None
    dob: Optional[date] = None
    class_id: Optional[int] = None
    section_id: Optional[int] = None
    is_transport: Optional[bool] = None
    driver_id: Optional[int] = None
    pickup_point: Optional[str] = None
    pickup_time: Optional[str] = None
    drop_point: Optional[str] = None
    drop_time: Optional[str] = None

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
    select_class: Optional[int] = None
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

