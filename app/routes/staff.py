from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
import re

from app.core.dependencies import get_current_user
from app.core.security import get_password_hash
from app.db.session import get_db
from app.models.school import School
from app.models.staff import Staff
from app.models.users import User
from app.schemas.staff import StaffCreateRequest, StaffResponse
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
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only school accounts can create staff members.",
        )

    # Validate email uniqueness
    existing_user = db.query(User).filter(User.email == data.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already exists.",
        )

    # Get school profile for the current user
    school = db.query(School).filter(School.user_id == current_user.id).first()
    if not school:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="School profile not found for the current user.",
        )

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

