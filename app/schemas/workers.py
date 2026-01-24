from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class WorkerBase(BaseModel):
    name: str
    role: str  # plumber, labor, electrician, technician, etc.


class WorkerCreate(WorkerBase):
    pass  # Only name and role are required


class WorkerUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None


class WorkerResponse(WorkerBase):
    id: str
    school_id: str
    user_id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {
        "from_attributes": True
    }


class PaymentRecordBase(BaseModel):
    description: Optional[str] = None
    files: Optional[List[str]] = None  # Array of file URLs
    status: str
    amount: Optional[float] = None
    payment_date: Optional[datetime] = None


class PaymentRecordCreate(PaymentRecordBase):
    pass  # worker_id comes from URL path


class PaymentRecordUpdate(BaseModel):
    description: Optional[str] = None
    files: Optional[List[str]] = None
    status: Optional[str] = None
    amount: Optional[float] = None
    payment_date: Optional[datetime] = None


class PaymentRecordResponse(PaymentRecordBase):
    id: int
    worker_id: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {
        "from_attributes": True
    }


class PaymentRecordWithWorker(PaymentRecordResponse):
    worker: Optional[WorkerResponse] = None

    model_config = {
        "from_attributes": True
    }


class WorkerWithPayments(WorkerResponse):
    payment_records: Optional[List[PaymentRecordResponse]] = None

    model_config = {
        "from_attributes": True
    }
