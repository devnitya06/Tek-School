from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_
from typing import Optional, List
from datetime import datetime

from app.core.dependencies import get_current_user
from app.core.security import get_password_hash
from app.db.session import get_db
from app.models.school import School, Worker, PaymentRecord
from app.models.users import User
from app.schemas.workers import (
    WorkerCreate,
    WorkerUpdate,
    WorkerResponse,
    PaymentRecordCreate,
    PaymentRecordUpdate,
    PaymentRecordResponse,
    PaymentRecordWithWorker,
    WorkerWithPayments
)
from app.schemas.users import UserRole
from app.utils.permission import require_roles, verify_school_business_access
from app.utils.s3 import upload_base64_to_s3
from app.services.pagination import PaginationParams

router = APIRouter()


def get_school_id(current_user: User, db: Session) -> str:
    """Helper function to get school_id based on user role"""
    if current_user.role == UserRole.SCHOOL:
        # ✅ Verify business account access
        verify_school_business_access(current_user, db)
        school = db.query(School).filter(School.user_id == current_user.id).first()
        if not school:
            raise HTTPException(status_code=404, detail="School profile not found for the current user.")
        return school.id
    elif current_user.role == UserRole.STAFF:
        from app.models.staff import Staff
        staff = db.query(Staff).filter(Staff.user_id == current_user.id).first()
        if not staff:
            raise HTTPException(status_code=404, detail="Staff profile not found.")
        return staff.school_id
    elif current_user.role == UserRole.TEACHER:
        from app.models.teachers import Teacher
        teacher = db.query(Teacher).filter(Teacher.user_id == current_user.id).first()
        if not teacher:
            raise HTTPException(status_code=404, detail="Teacher profile not found.")
        return teacher.school_id
    else:
        raise HTTPException(status_code=403, detail="Only school, staff, and teacher users can access this resource.")


# ==================== WORKER ENDPOINTS ====================

@router.post(
    "/workers/",
    status_code=status.HTTP_201_CREATED,
    response_model=WorkerResponse,
    summary="Create a new worker",
    description="Create a new worker (plumber, labor, electrician, etc.) for the school"
)
def create_worker(
    data: WorkerCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.SCHOOL, UserRole.STAFF))
):
    """Create a new worker. Only school and staff users can create workers. Automatically creates a User and generates worker ID based on role."""
    school_id = get_school_id(current_user, db)
    
    # Get school profile for location/website
    school = db.query(School).filter(School.id == school_id).first()
    if not school:
        raise HTTPException(status_code=404, detail="School not found.")
    
    # Generate email based on name and role (you can customize this)
    # Using a simple format: name.lower().replace(" ", ".") + "@worker.local"
    email_base = data.name.lower().replace(" ", ".").replace("'", "")
    email = f"{email_base}@worker.local"
    
    # Check if email already exists
    existing_user = db.query(User).filter(User.email == email).first()
    if existing_user:
        # If user exists, check if they already have a worker profile for this school
        existing_worker = db.query(Worker).filter(
            and_(Worker.user_id == existing_user.id, Worker.school_id == school_id)
        ).first()
        if existing_worker:
            raise HTTPException(
                status_code=400,
                detail="Worker profile already exists for this user in this school."
            )
        # Use existing user
        user = existing_user
    else:
        # Create new User for the worker
        user = User(
            name=data.name,
            email=email,
            role=UserRole.STAFF,  # Using STAFF role for workers, or you can create a WORKER role
            hashed_password=get_password_hash("worker123"),  # Default password, should be changed
            is_verified=True,
            is_active=True,
            location=current_user.location,
            website=current_user.website
        )
        db.add(user)
        db.flush()  # Get user.id
    
    # Create worker (ID will be auto-generated in __init__ based on role)
    worker = Worker(
        school_id=school_id,
        user_id=user.id,
        name=data.name,
        role=data.role
    )
    db.add(worker)
    db.commit()
    db.refresh(worker)
    
    return worker


@router.get(
    "/workers/",
    response_model=List[WorkerResponse],
    summary="Get all workers",
    description="Get a list of all workers for the school"
)
def get_workers(
    role: Optional[str] = Query(None, description="Filter by role (plumber, labor, electrician, etc.)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.SCHOOL, UserRole.STAFF, UserRole.TEACHER))
):
    """Get all workers for the school. Can filter by role."""
    school_id = get_school_id(current_user, db)
    
    query = db.query(Worker).filter(Worker.school_id == school_id)
    
    if role:
        query = query.filter(Worker.role == role)
    
    workers = query.order_by(Worker.created_at.desc()).all()
    
    return workers


@router.get(
    "/workers/{worker_id}",
    response_model=WorkerWithPayments,
    summary="Get worker by ID",
    description="Get detailed information about a specific worker including payment records"
)
def get_worker(
    worker_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.SCHOOL, UserRole.STAFF, UserRole.TEACHER))
):
    """Get a specific worker by ID with their payment records."""
    school_id = get_school_id(current_user, db)
    
    worker = db.query(Worker).filter(
        and_(Worker.id == worker_id, Worker.school_id == school_id)
    ).first()
    
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found.")
    
    return worker


@router.patch(
    "/workers/{worker_id}",
    response_model=WorkerResponse,
    summary="Update worker",
    description="Update worker information"
)
def update_worker(
    worker_id: str,
    data: WorkerUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.SCHOOL, UserRole.STAFF))
):
    """Update worker information. Only school and staff users can update workers."""
    school_id = get_school_id(current_user, db)
    
    worker = db.query(Worker).filter(
        and_(Worker.id == worker_id, Worker.school_id == school_id)
    ).first()
    
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found.")
    
    # Update fields
    if data.name is not None:
        worker.name = data.name
    if data.role is not None:
        worker.role = data.role
    
    db.commit()
    db.refresh(worker)
    
    return worker


@router.delete(
    "/workers/{worker_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete worker",
    description="Delete a worker and all associated payment records"
)
def delete_worker(
    worker_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.SCHOOL))
):
    """Delete a worker. Only school users can delete workers."""
    school_id = get_school_id(current_user, db)
    
    worker = db.query(Worker).filter(
        and_(Worker.id == worker_id, Worker.school_id == school_id)
    ).first()
    
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found.")
    
    db.delete(worker)
    db.commit()
    
    return None


# ==================== PAYMENT RECORD ENDPOINTS ====================

@router.post(
    "/workers/{worker_id}/payments/",
    status_code=status.HTTP_201_CREATED,
    response_model=PaymentRecordResponse,
    summary="Create payment record",
    description="Create a new payment record for a worker"
)
def create_payment_record(
    worker_id: str,
    data: PaymentRecordCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.SCHOOL, UserRole.STAFF))
):
    """Create a payment record for a worker. Files should be base64 encoded."""
    school_id = get_school_id(current_user, db)
    
    # Verify worker exists and belongs to the school
    worker = db.query(Worker).filter(
        and_(Worker.id == worker_id, Worker.school_id == school_id)
    ).first()
    
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found.")
    
    # Handle file uploads if provided
    uploaded_file_urls = []
    if data.files:
        for file_base64 in data.files:
            try:
                # Extract file extension from base64 string
                file_ext = "pdf"  # Default extension
                if "," in file_base64:
                    if "image/png" in file_base64:
                        file_ext = "png"
                    elif "image/jpeg" in file_base64 or "image/jpg" in file_base64:
                        file_ext = "jpg"
                    elif "application/pdf" in file_base64:
                        file_ext = "pdf"
                
                # Upload to S3
                file_url = upload_base64_to_s3(
                    base64_string=file_base64,
                    filename_prefix=f"workers/{worker_id}/payments",
                    ext=file_ext
                )
                uploaded_file_urls.append(file_url)
            except Exception as e:
                print(f"Warning: Failed to upload file: {str(e)}")
                # Continue with other files even if one fails
    
    # Create payment record
    payment_record = PaymentRecord(
        worker_id=worker_id,
        description=data.description,
        files=uploaded_file_urls if uploaded_file_urls else None,
        status=data.status,
        amount=data.amount,
        payment_date=data.payment_date or datetime.utcnow()
    )
    db.add(payment_record)
    db.commit()
    db.refresh(payment_record)
    
    return payment_record


@router.get(
    "/workers/{worker_id}/payments/",
    response_model=List[PaymentRecordResponse],
    summary="Get payment records for a worker",
    description="Get all payment records for a specific worker"
)
def get_payment_records(
    worker_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.SCHOOL, UserRole.STAFF, UserRole.TEACHER))
):
    """Get all payment records for a worker."""
    school_id = get_school_id(current_user, db)
    
    # Verify worker exists and belongs to the school
    worker = db.query(Worker).filter(
        and_(Worker.id == worker_id, Worker.school_id == school_id)
    ).first()
    
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found.")
    
    payment_records = db.query(PaymentRecord).filter(
        PaymentRecord.worker_id == worker_id
    ).order_by(PaymentRecord.payment_date.desc()).all()
    
    return payment_records


@router.get(
    "/payments/",
    summary="Get all payment records for school",
    description="Get all payment records for all workers in the school with pagination and filtering"
)
def get_all_payment_records(
    pagination: PaginationParams = Depends(),
    worker_id: Optional[str] = Query(None, description="Filter by worker ID (e.g., TEC-324567)"),
    status: Optional[str] = Query(None, description="Filter by payment status"),
    start_date: Optional[str] = Query(None, description="Filter by start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="Filter by end date (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.SCHOOL, UserRole.STAFF, UserRole.TEACHER))
):
    """Get all payment records for all workers in the school with pagination and filtering."""
    school_id = get_school_id(current_user, db)
    
    # Get all workers for this school
    workers = db.query(Worker).filter(Worker.school_id == school_id).all()
    worker_ids = [worker.id for worker in workers]
    
    if not worker_ids:
        return pagination.format_response([], 0)
    
    # Build query
    query = db.query(PaymentRecord).filter(PaymentRecord.worker_id.in_(worker_ids))
    
    # Apply filters
    if worker_id:
        if worker_id not in worker_ids:
            raise HTTPException(status_code=404, detail="Worker not found or doesn't belong to your school.")
        query = query.filter(PaymentRecord.worker_id == worker_id)
    
    if status:
        query = query.filter(PaymentRecord.status == status)
    
    if start_date:
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            query = query.filter(PaymentRecord.payment_date >= start_dt)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid start_date format. Use YYYY-MM-DD")
    
    if end_date:
        try:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")
            # Include the entire end date
            end_dt = end_dt.replace(hour=23, minute=59, second=59)
            query = query.filter(PaymentRecord.payment_date <= end_dt)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid end_date format. Use YYYY-MM-DD")
    
    # Get total count before pagination
    total_count = query.count()
    
    # Apply pagination and ordering
    payment_records = query.order_by(
        PaymentRecord.payment_date.desc()
    ).offset(pagination.offset()).limit(pagination.limit()).all()
    
    return pagination.format_response(payment_records, total_count)


@router.get(
    "/payments/{payment_id}",
    response_model=PaymentRecordWithWorker,
    summary="Get payment record by ID",
    description="Get detailed information about a specific payment record"
)
def get_payment_record(
    payment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.SCHOOL, UserRole.STAFF, UserRole.TEACHER))
):
    """Get a specific payment record by ID."""
    school_id = get_school_id(current_user, db)
    
    payment_record = db.query(PaymentRecord).filter(PaymentRecord.id == payment_id).first()
    
    if not payment_record:
        raise HTTPException(status_code=404, detail="Payment record not found.")
    
    # Verify the payment record belongs to a worker in this school
    worker = db.query(Worker).filter(
        and_(Worker.id == payment_record.worker_id, Worker.school_id == school_id)
    ).first()
    
    if not worker:
        raise HTTPException(status_code=403, detail="You don't have access to this payment record.")
    
    return payment_record


@router.patch(
    "/payments/{payment_id}",
    response_model=PaymentRecordResponse,
    summary="Update payment record",
    description="Update a payment record"
)
def update_payment_record(
    payment_id: int,
    data: PaymentRecordUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.SCHOOL, UserRole.STAFF))
):
    """Update a payment record. Only school and staff users can update payment records."""
    school_id = get_school_id(current_user, db)
    
    payment_record = db.query(PaymentRecord).filter(PaymentRecord.id == payment_id).first()
    
    if not payment_record:
        raise HTTPException(status_code=404, detail="Payment record not found.")
    
    # Verify the payment record belongs to a worker in this school
    worker = db.query(Worker).filter(
        and_(Worker.id == payment_record.worker_id, Worker.school_id == school_id)
    ).first()
    
    if not worker:
        raise HTTPException(status_code=403, detail="You don't have access to this payment record.")
    
    # Handle file uploads if provided
    if data.files is not None:
        uploaded_file_urls = []
        for file_base64 in data.files:
            try:
                file_ext = "pdf"
                if "," in file_base64:
                    if "image/png" in file_base64:
                        file_ext = "png"
                    elif "image/jpeg" in file_base64 or "image/jpg" in file_base64:
                        file_ext = "jpg"
                    elif "application/pdf" in file_base64:
                        file_ext = "pdf"
                
                file_url = upload_base64_to_s3(
                    base64_string=file_base64,
                    filename_prefix=f"workers/{payment_record.worker_id}/payments",
                    ext=file_ext
                )
                uploaded_file_urls.append(file_url)
            except Exception as e:
                print(f"Warning: Failed to upload file: {str(e)}")
        
        payment_record.files = uploaded_file_urls if uploaded_file_urls else None
    
    # Update other fields
    if data.description is not None:
        payment_record.description = data.description
    if data.status is not None:
        payment_record.status = data.status
    if data.amount is not None:
        payment_record.amount = data.amount
    if data.payment_date is not None:
        payment_record.payment_date = data.payment_date
    
    db.commit()
    db.refresh(payment_record)
    
    return payment_record


@router.delete(
    "/payments/{payment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete payment record",
    description="Delete a payment record"
)
def delete_payment_record(
    payment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.SCHOOL))
):
    """Delete a payment record. Only school users can delete payment records."""
    school_id = get_school_id(current_user, db)
    
    payment_record = db.query(PaymentRecord).filter(PaymentRecord.id == payment_id).first()
    
    if not payment_record:
        raise HTTPException(status_code=404, detail="Payment record not found.")
    
    # Verify the payment record belongs to a worker in this school
    worker = db.query(Worker).filter(
        and_(Worker.id == payment_record.worker_id, Worker.school_id == school_id)
    ).first()
    
    if not worker:
        raise HTTPException(status_code=403, detail="You don't have access to this payment record.")
    
    db.delete(payment_record)
    db.commit()
    
    return None
