from pydantic import BaseModel, EmailStr, Field
from typing import List, Literal, Optional
from datetime import time, datetime, date
from app.models.teachers import DayOfWeek, PaymentMode

class Assignment(BaseModel):
    class_id: int
    section_id: int
    subject_id: int

class EmployeePaymentCreate(BaseModel):
    """Payment structure for teacher and staff creation"""
    monthly_in_hand_salary: float = Field(default=0.0, ge=0, description="Monthly in-hand salary amount")
    allowance: float = Field(default=0.0, ge=0, description="Allowance amount")
    bonus: float = Field(default=0.0, ge=0, description="Bonus amount")
    other_allowances: float = Field(default=0.0, ge=0, description="Other allowances amount")
    incentive_plan: float = Field(default=0.0, ge=0, description="Incentive plan amount")
    health_care_insurance: float = Field(default=0.0, ge=0, description="Health care insurance amount")
    skill_development: float = Field(default=0.0, ge=0, description="Skill development amount")

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
    designation: Optional[str] = None
    immidiate_boss: Optional[str] = None
    super_boss: Optional[str] = None
    mark_in_time: Optional[time] = None
    mark_out_time: Optional[time] = None
    employee_grade: Optional[str] = None
    is_active_hr_service: Optional[bool] = None
    assignments: List[Assignment]
    payment: Optional[EmployeePaymentCreate] = None  # Optional payment structure

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
    designation: Optional[str] = None
    immidiate_boss: Optional[str] = None
    super_boss: Optional[str] = None
    mark_in_time: Optional[time] = None
    mark_out_time: Optional[time] = None
    employee_grade: Optional[str] = None
    is_active_hr_service: Optional[bool] = None
    assignments: Optional[List[Assignment]] = None
    payment: Optional[EmployeePaymentCreate] = None  # Optional payment structure update 
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
    designation: Optional[str] = None
    immidiate_boss: Optional[str] = None
    super_boss: Optional[str] = None
    mark_in_time: Optional[time] = None
    mark_out_time: Optional[time] = None
    employee_grade: Optional[str] = None
    is_active_hr_service: Optional[bool] = None
    model_config = {
        "from_attributes": True
    }


class TeacherStaffPaymentRequest(BaseModel):
    """Request schema for making a payment to teacher or staff"""
    payment_month: str = Field(..., description="Payment month in YYYY-MM format (e.g., '2025-01')")
    release_date: datetime = Field(..., description="Date when the payment is released")
    total_amount: float = Field(..., ge=0, description="Total payment amount for this month")
    payment_mode: PaymentMode = Field(..., description="Payment mode: Online, Cash in hand, or Account transfer")
    settlement_channel: Literal["cash_offline", "bank_account"] = Field(
        default="cash_offline",
        description="Ledger: pay from school cash (offline) or a specific bank account.",
    )
    bank_account_id: Optional[int] = Field(
        default=None,
        description="Required when settlement_channel is bank_account; must belong to the school.",
    )


class TeacherStaffPaymentTransactionResponse(BaseModel):
    """Response schema for payment transaction"""
    id: int
    payment_month: str
    total_amount: float
    payment_mode: str
    release_date: datetime
    created_at: datetime
    
    model_config = {
        "from_attributes": True
    }


class TeacherPaymentItem(BaseModel):
    """Individual teacher payment item for bulk payment"""
    teacher_id: str = Field(..., description="Teacher ID")
    payment_month: str = Field(..., description="Payment month in YYYY-MM format (e.g., '2025-01')")
    release_date: datetime = Field(..., description="Date when the payment is released")
    total_amount: float = Field(..., ge=0, description="Total payment amount for this teacher")
    payment_mode: PaymentMode = Field(..., description="Payment mode: Online, Cash in hand, or Account transfer")
    settlement_channel: Literal["cash_offline", "bank_account"] = Field(
        default="cash_offline",
        description="Ledger: pay from school cash (offline) or a specific bank account.",
    )
    bank_account_id: Optional[int] = Field(
        default=None,
        description="Required when settlement_channel is bank_account.",
    )


class StaffPaymentItem(BaseModel):
    """Individual staff payment item for bulk payment"""
    staff_id: str = Field(..., description="Staff ID")
    payment_month: str = Field(..., description="Payment month in YYYY-MM format (e.g., '2025-01')")
    release_date: datetime = Field(..., description="Date when the payment is released")
    total_amount: float = Field(..., ge=0, description="Total payment amount for this staff member")
    payment_mode: PaymentMode = Field(..., description="Payment mode: Online, Cash in hand, or Account transfer")
    settlement_channel: Literal["cash_offline", "bank_account"] = Field(
        default="cash_offline",
        description="Ledger: pay from school cash (offline) or a specific bank account.",
    )
    bank_account_id: Optional[int] = Field(
        default=None,
        description="Required when settlement_channel is bank_account.",
    )


class BulkTeacherPaymentRequest(BaseModel):
    """Request schema for making bulk payments to multiple teachers"""
    payments: List[TeacherPaymentItem] = Field(..., description="List of payments with teacher_id, payment_month, release_date, total_amount, and payment_mode")


class BulkStaffPaymentRequest(BaseModel):
    """Request schema for making bulk payments to multiple staff members"""
    payments: List[StaffPaymentItem] = Field(..., description="List of payments with staff_id, payment_month, release_date, total_amount, and payment_mode")


class FailedPaymentItem(BaseModel):
    """Failed payment item with error message"""
    teacher_id: Optional[str] = None
    staff_id: Optional[str] = None
    error: str = Field(..., description="Error message explaining why payment failed")


class BulkPaymentResponse(BaseModel):
    """Response schema for bulk payment operation"""
    success_count: int
    failed_count: int
    successful_payments: List[TeacherStaffPaymentTransactionResponse]
    failed_payments: List[FailedPaymentItem]


class PendingMonthResponse(BaseModel):
    """Response schema for pending payment months"""
    month: str = Field(..., description="Month in YYYY-MM format")
    month_name: str = Field(..., description="Human-readable month name (e.g., 'January 2025')")
    is_paid: bool = Field(..., description="Whether payment has been made for this month")
    payment_date: Optional[datetime] = Field(None, description="Date when payment was made (if paid)")


class EmployeePaymentListResponse(BaseModel):
    """Response schema for employee (teacher/staff) list with payments"""
    id: str = Field(..., description="Employee ID (teacher_id or staff_id)")
    name: str = Field(..., description="Employee full name")
    role: str = Field(..., description="Employee role: 'teacher' or 'staff'")
    payment_count: int = Field(..., description="Total number of payments made")
    last_3_payments: List[TeacherStaffPaymentTransactionResponse] = Field(..., description="Last 3 payment transactions")
    
    model_config = {
        "from_attributes": True
    }

class WithdrawRequestSchema(BaseModel):
    amount: int = Field(..., gt=0)
    bank_account_id: int

class BankAccountSchema(BaseModel):
    account_holder_name: str
    account_number: str
    re_account_number: str
    ifsc_code: str
    bank_name: str
    is_default: bool = False


class WithdrawStatusSchema(BaseModel):
    status: str


class AddBalanceSchema(BaseModel):
    amount: int = Field(..., gt=0)

class AdminBankAccountSchema(BaseModel):
    account_holder_name: str
    account_number: str
    re_account_number: str
    ifsc_code: str
    bank_name: str
    is_default: bool = False


class AddBalanceSchema(BaseModel):
    amount: int = Field(..., gt=0)


class WithdrawStatusSchema(BaseModel):
    status: str   # SUCCESS / HOLD