from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
import re

from app.core.dependencies import get_current_user
from app.core.security import get_password_hash
from app.db.session import get_db
from app.models.school import School
from app.models.staff import Staff
from app.models.users import User
from app.schemas.staff import StaffCreateRequest, StaffResponse, StaffUpdateRequest
from app.schemas.users import UserRole
from app.utils.email_utility import send_dynamic_email

router = APIRouter()


@router.post(
    "/create-staff/",
    status_code=status.HTTP_201_CREATED,
    response_model=StaffResponse,
    responses={
        status.HTTP_201_CREATED: {
            "description": "Staff account created and credentials emailed."
        }
    },
)
def create_staff(
    data: StaffCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StaffResponse:
    """
    Create a staff account. Only school accounts have permission to create staff members.
    Creates both User and Staff profile, then emails credentials to the staff member.
    """
    # Permission check: Only SCHOOL role can create staff
    if current_user.role != "SCHOOL":
        raise HTTPException(status_code=403, detail="Only school accounts can create staff members.")

    # Validate email uniqueness
    existing_user = db.query(User).filter(User.email == data.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already exists.")

    # Get school profile for the current user
    school = db.query(School).filter(School.user_id == current_user.id).first()
    if not school:
        raise HTTPException(status_code=404, detail="School profile not found for the current user.")

    try:
        # Create User account for staff (following same pattern as teacher creation)
        staff_user = User(
            name=f"{data.first_name} {data.last_name}",
            email=data.email,
            phone=data.phone,
            location=current_user.location,
            website=current_user.website,
            role=UserRole.STAFF,
            hashed_password=get_password_hash(data.password),
            is_verified=True,
        )
        db.add(staff_user)
        db.flush()  # assigns user.id

        # Create Staff profile
        staff = Staff(
            first_name=data.first_name,
            last_name=data.last_name,
            email=data.email,
            phone=data.phone,
            designation=data.designation,
            employee_type=data.employee_type,
            annual_salary=data.annual_salary,
            emergency_leave=data.emergency_leave or 0,
            casual_leave=data.casual_leave or 0,
            school_id=school.id,
            user_id=staff_user.id,
        )
        db.add(staff)
        db.commit()
        db.refresh(staff)

    except SQLAlchemyError as exc:
        db.rollback()
        # Parse the error to identify which field caused the issue
        error_message = str(exc)
        field_name = None
        error_detail = "Database error occurred"
        
        # Check for enum errors
        if "enum" in error_message.lower() and "userrole" in error_message.lower():
            field_name = "role"
            error_detail = f"Invalid role value. The 'role' field must be one of: superadmin, admin, school, teacher, student, staff"
        # Check for unique constraint violations
        elif "unique" in error_message.lower() or "duplicate" in error_message.lower():
            if "email" in error_message.lower():
                field_name = "email"
                error_detail = "Email already exists in the system"
            else:
                field_name = "unknown"
                error_detail = "A record with these values already exists"
        # Check for foreign key violations
        elif "foreign key" in error_message.lower():
            if "school_id" in error_message.lower():
                field_name = "school_id"
                error_detail = "Invalid school reference"
            else:
                field_name = "unknown"
                error_detail = "Invalid reference to related record"
        # Check for not null violations
        elif "not null" in error_message.lower() or "null value" in error_message.lower():
            # Extract field name from error message
            match = re.search(r'column "(\w+)"', error_message)
            if match:
                field_name = match.group(1)
                error_detail = f"The '{field_name}' field is required and cannot be empty"
            else:
                field_name = "unknown"
                error_detail = "A required field is missing"
        # Check for data type errors
        elif "invalid input" in error_message.lower():
            # Extract field name from error message
            match = re.search(r'for enum \w+: "(\w+)"', error_message)
            if match:
                field_name = "role"
                invalid_value = match.group(1)
                error_detail = f"Invalid role value '{invalid_value}'. Valid values are: superadmin, admin, school, teacher, student, staff"
            else:
                field_name = "unknown"
                error_detail = "Invalid data format for one or more fields"
        
        # Build detailed error response
        error_response = {
            "detail": error_detail,
            "error_type": "database_error",
        }
        
        if field_name:
            error_response["field"] = field_name
            error_response["message"] = f"Error in field '{field_name}': {error_detail}"
        
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_response if field_name else error_detail,
        ) from exc

    # Send credentials email to staff member
    send_dynamic_email(
        context_key="credential.html",
        subject="Your Staff Account Credentials",
        recipient_email=staff.email,
        context_data={"email": staff.email, "password": data.password},
        db=db,
    )

    return StaffResponse.model_validate(staff)


@router.get("/profile")
def get_staff_profile(
    staff_id: str | None = Query(None, description="Staff ID (required if user is SCHOOL)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get staff profile. 
    - Staff members can view their own profile (staff_id is ignored)
    - School users can view any staff profile from their school (staff_id is required)
    """

    if current_user.role not in ["STAFF", "SCHOOL"]:
        raise HTTPException(status_code=403, detail="Only staff members and school users can access staff profiles.")

    staff = None
    
    if current_user.role == "STAFF":
        staff = db.query(Staff).filter(Staff.user_id == current_user.id).first()
        if not staff:
            raise HTTPException(status_code=404, detail="Staff profile not found.")
    elif current_user.role == "SCHOOL":
        if not staff_id:
            raise HTTPException(status_code=400, detail="staff_id is required when accessing as school user.")

        school = getattr(current_user, "school_profile", None)
        if not school:
            raise HTTPException(status_code=404, detail="School profile not found for the current user.")

        staff_exists = db.query(Staff).filter(Staff.id == staff_id).first()
        if not staff_exists:
            raise HTTPException(status_code=404, detail=f"Staff with ID '{staff_id}' not found.")

        staff = db.query(Staff).filter(
            Staff.id == staff_id,
            Staff.school_id == school.id
        ).first()
        
        if not staff:
            raise HTTPException(status_code=404, detail=f"Staff with ID '{staff_id}' does not belong to your school. Staff belongs to school_id: {staff_exists.school_id}, your school_id: {school.id}.")

    # Get associated user for email/phone fallback
    user = db.query(User).filter(User.id == staff.user_id).first()

    # Calculate monthly salary from annual salary
    monthly_salary = None
    if staff.annual_salary:
        monthly_salary = float(staff.annual_salary) / 12

    return {
        "id": staff.id,
        "school_id": staff.school_id,
        "first_name": staff.first_name,
        "last_name": staff.last_name,
        "email": staff.email or (user.email if user else None),
        "phone": staff.phone or (user.phone if user else None),
        "designation": staff.designation,
        "employee_type": staff.employee_type,
        "annual_salary": float(staff.annual_salary) if staff.annual_salary else None,
        "monthly_salary": round(monthly_salary, 2) if monthly_salary else None,
        "emergency_leave": staff.emergency_leave or 0,
        "casual_leave": staff.casual_leave or 0,
        "is_active": staff.is_active,
        "created_at": staff.created_at.isoformat() if staff.created_at else None,
        "updated_at": staff.updated_at.isoformat() if staff.updated_at else None,
    }


@router.patch("/profile")
def update_staff_profile(
    data: StaffUpdateRequest,
    staff_id: str | None = Query(None, description="Staff ID (required if user is SCHOOL)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Update staff profile. 
    - Staff members can update their own profile (staff_id is ignored)
    - School users can update any staff profile from their school (staff_id is required)
    Following the screenshot requirements:
    - First Name, Last Name, Phone, Email (can be edited, pulls from User table)
    - Employee Type (Full Time/Part Time)
    - Designation
    - Annual Salary (input)
    - Monthly Salary (auto-calculated from annual salary)
    - Emergency Leave, Casual Leave (auto)
    """
    if current_user.role not in ["STAFF", "SCHOOL"]:
        raise HTTPException(status_code=403, detail="Only staff members and school users can update staff profiles.")

    staff = None
    
    if current_user.role == "STAFF":
        # Staff updating their own profile
        staff = db.query(Staff).filter(Staff.user_id == current_user.id).first()
        if not staff:
            raise HTTPException(status_code=404, detail="Staff profile not found.")
    elif current_user.role == "SCHOOL":
        # School updating a specific staff profile
        if not staff_id:
            raise HTTPException(status_code=400, detail="staff_id is required when updating as school user.")
        
        school = getattr(current_user, "school_profile", None)
        if not school:
            raise HTTPException(status_code=404, detail="School profile not found for the current user.")
        
        staff_exists = db.query(Staff).filter(Staff.id == staff_id).first()
        if not staff_exists:
            raise HTTPException(status_code=404, detail=f"Staff with ID '{staff_id}' not found.")
        
        staff = db.query(Staff).filter(
            Staff.id == staff_id,
            Staff.school_id == school.id
        ).first()
        
        if not staff:
            raise HTTPException(status_code=404, detail=f"Staff with ID '{staff_id}' does not belong to your school.")

    try:
        # Update User table fields (name, email, phone)
        # Get the user associated with the staff being updated
        user = db.query(User).filter(User.id == staff.user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User record not found.")

        # Update user fields if provided
        if data.first_name is not None or data.last_name is not None:
            first_name = data.first_name if data.first_name is not None else staff.first_name
            last_name = data.last_name if data.last_name is not None else staff.last_name
            user.name = f"{first_name} {last_name}"

        if data.email is not None:
            # Check if email is already taken by another user
            existing_user = db.query(User).filter(
                User.email == data.email,
                User.id != staff.user_id
            ).first()
            if existing_user:
                raise HTTPException(status_code=400, detail="Email already exists.")
            user.email = data.email

        if data.phone is not None:
            user.phone = data.phone

        # Update staff fields
        update_fields = data.model_dump(exclude_unset=True, exclude={"email", "phone"})
        for field, value in update_fields.items():
            if value is not None:
                setattr(staff, field, value)

        # Also update staff email/phone if provided (to keep in sync)
        if data.email is not None:
            staff.email = data.email
        if data.phone is not None:
            staff.phone = data.phone

        db.commit()
        db.refresh(staff)
        db.refresh(user)

        # Calculate monthly salary
        monthly_salary = None
        if staff.annual_salary:
            monthly_salary = float(staff.annual_salary) / 12

        return {
            "detail": "Staff profile updated successfully.",
            "data": {
                "id": staff.id,
                "first_name": staff.first_name,
                "last_name": staff.last_name,
                "email": staff.email,
                "phone": staff.phone,
                "designation": staff.designation,
                "employee_type": staff.employee_type,
                "annual_salary": float(staff.annual_salary) if staff.annual_salary else None,
                "monthly_salary": round(monthly_salary, 2) if monthly_salary else None,
                "emergency_leave": staff.emergency_leave or 0,
                "casual_leave": staff.casual_leave or 0,
            }
        }

    except HTTPException:
        db.rollback()
        raise
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}") from e
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update staff profile: {str(e)}") from e

