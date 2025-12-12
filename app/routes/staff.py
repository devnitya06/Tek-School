from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
import re
from datetime import date

from app.core.dependencies import get_current_user
from app.core.security import get_password_hash
from app.db.session import get_db
from app.models.school import School
from app.models.staff import Staff, ActivityLog, staff_permissions, StaffPermissionType
from app.models.users import User
from app.schemas.staff import StaffCreateRequest, StaffResponse, StaffUpdateRequest, StaffPermissionAssignRequest, StaffPermissionResponse, ActivityLogResponse
from app.schemas.users import UserRole
from app.utils.email_utility import send_dynamic_email
from app.utils.permission import get_staff_permissions, require_roles
from app.services.pagination import PaginationParams
from typing import Optional

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
    if current_user.role != UserRole.SCHOOL:
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
        db.flush()  # Get staff.id
        
        # Add permissions if provided
        if data.permissions:
            for permission in data.permissions:
                db.execute(
                    staff_permissions.insert().values(
                        staff_id=staff.id,
                        permission=permission.value,
                        granted_by=current_user.id
                    )
                )
        
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

        elif "unique" in error_message.lower() or "duplicate" in error_message.lower():
            if "email" in error_message.lower():
                field_name = "email"
                error_detail = "Email already exists in the system"
            else:
                field_name = "unknown"
                error_detail = "A record with these values already exists"

        elif "foreign key" in error_message.lower():
            if "school_id" in error_message.lower():
                field_name = "school_id"
                error_detail = "Invalid school reference"
            else:
                field_name = "unknown"
                error_detail = "Invalid reference to related record"

        elif "not null" in error_message.lower() or "null value" in error_message.lower():

            match = re.search(r'column "(\w+)"', error_message)
            if match:
                field_name = match.group(1)
                error_detail = f"The '{field_name}' field is required and cannot be empty"
            else:
                field_name = "unknown"
                error_detail = "A required field is missing"
        # Check for data type errors
        elif "invalid input" in error_message.lower():

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

    if current_user.role not in [UserRole.STAFF, UserRole.SCHOOL]:
        raise HTTPException(status_code=403, detail="Only staff members and school users can access staff profiles.")

    staff = None
    
    if current_user.role == UserRole.STAFF:
        staff = db.query(Staff).filter(Staff.user_id == current_user.id).first()
        if not staff:
            raise HTTPException(status_code=404, detail="Staff profile not found.")
    elif current_user.role == UserRole.SCHOOL:
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

    # Get staff permissions
    permissions = get_staff_permissions(staff.id, db)

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
        "permissions": permissions,
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
    if current_user.role not in [UserRole.STAFF, UserRole.SCHOOL]:
        raise HTTPException(status_code=403, detail="Only staff members and school users can update staff profiles.")

    staff = None
    
    if current_user.role == UserRole.STAFF:
        # Staff updating their own profile
        staff = db.query(Staff).filter(Staff.user_id == current_user.id).first()
        if not staff:
            raise HTTPException(status_code=404, detail="Staff profile not found.")
    elif current_user.role == UserRole.SCHOOL:
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

        if data.email is not None:
            staff.email = data.email
        if data.phone is not None:
            staff.phone = data.phone

        db.commit()
        db.refresh(staff)
        db.refresh(user)

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


@router.put("/{staff_id}/permissions")
def assign_staff_permissions(
    staff_id: str,
    data: StaffPermissionAssignRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Assign/Update permissions for a staff member. Only SCHOOL users can assign permissions.
    This replaces all existing permissions with the new ones.
    """
    if current_user.role != UserRole.SCHOOL:
        raise HTTPException(status_code=403, detail="Only school users can assign staff permissions.")

    school = getattr(current_user, "school_profile", None)
    if not school:
        raise HTTPException(status_code=404, detail="School profile not found for the current user.")

    staff = db.query(Staff).filter(
        Staff.id == staff_id,
        Staff.school_id == school.id
    ).first()
    
    if not staff:
        raise HTTPException(status_code=404, detail="Staff not found or doesn't belong to your school.")

    try:
        db.execute(
            staff_permissions.delete().where(staff_permissions.c.staff_id == staff_id)
        )
        
        for permission in data.permissions:
            db.execute(
                staff_permissions.insert().values(
                    staff_id=staff_id,
                    permission=permission.value,
                    granted_by=current_user.id
                )
            )
        
        db.commit()
        
        updated_permissions = get_staff_permissions(staff_id, db)
        
        return {
            "detail": "Staff permissions updated successfully.",
            "staff_id": staff_id,
            "staff_name": f"{staff.first_name} {staff.last_name}",
            "permissions": updated_permissions
        }
    
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}") from e
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update staff permissions: {str(e)}") from e


@router.get("/{staff_id}/permissions")
def get_staff_permissions_endpoint(
    staff_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get permissions for a staff member.
    - SCHOOL users can view any staff member's permissions from their school
    - STAFF users can only view their own permissions
    """
    if current_user.role not in [UserRole.STAFF, UserRole.SCHOOL]:
        raise HTTPException(status_code=403, detail="Only staff members and school users can view permissions.")
    
    staff = None
    
    if current_user.role == UserRole.STAFF:
        staff = db.query(Staff).filter(Staff.user_id == current_user.id).first()
        if not staff:
            raise HTTPException(status_code=404, detail="Staff profile not found.")
        if staff.id != staff_id:
            raise HTTPException(status_code=403, detail="You can only view your own permissions.")
    elif current_user.role == UserRole.SCHOOL:
        school = getattr(current_user, "school_profile", None)
        if not school:
            raise HTTPException(status_code=404, detail="School profile not found for the current user.")
        
        staff = db.query(Staff).filter(
            Staff.id == staff_id,
            Staff.school_id == school.id
        ).first()
        
        if not staff:
            raise HTTPException(status_code=404, detail="Staff not found or doesn't belong to your school.")
    
    permissions = get_staff_permissions(staff_id, db)
    
    return {
        "staff_id": staff.id,
        "staff_name": f"{staff.first_name} {staff.last_name}",
        "permissions": permissions
    }


@router.get("/permissions/my")
def get_my_permissions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get current staff user's own permissions.
    """
    if current_user.role != UserRole.STAFF:
        raise HTTPException(status_code=403, detail="Only staff members can view their own permissions.")
    
    staff = db.query(Staff).filter(Staff.user_id == current_user.id).first()
    if not staff:
        raise HTTPException(status_code=404, detail="Staff profile not found.")
    
    permissions = get_staff_permissions(staff.id, db)
    
    return {
        "staff_id": staff.id,
        "staff_name": f"{staff.first_name} {staff.last_name}",
        "permissions": permissions
    }


@router.get("/activity-logs/", response_model=dict)
def get_activity_logs(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.SCHOOL, UserRole.STAFF)),
    pagination: PaginationParams = Depends(),
    user_id: Optional[str] = Query(None, description="Filter by user ID (integer) or profile ID (e.g., STF-123, TCH-456)"),
    action_type: Optional[str] = Query(None, description="Filter by action type (create, update, delete, approve, decline)"),
    resource_type: Optional[str] = Query(None, description="Filter by resource type (student, teacher, leave_request, class, transport)"),
    from_date: Optional[date] = Query(None, description="Filter from this start date"),
    to_date: Optional[date] = Query(None, description="Filter until this end date"),
):
    """
    Get activity logs for all users.
    - School users can see all logs for their school
    - Staff users can see all logs for their school
    """
    # Determine school_id
    if current_user.role == UserRole.SCHOOL:
        school = db.query(School).filter(School.user_id == current_user.id).first()
        if not school:
            raise HTTPException(status_code=404, detail="School profile not found.")
        school_id = school.id
    else:  # STAFF
        staff = db.query(Staff).filter(Staff.user_id == current_user.id).first()
        if not staff:
            raise HTTPException(status_code=404, detail="Staff profile not found.")
        school_id = staff.school_id
    
    # Build query
    query = db.query(ActivityLog).filter(ActivityLog.school_id == school_id)
    
    # ✅ Apply user_id filter (handles both integer user_id and profile IDs like STF-123, TCH-456)
    if user_id:
        try:
            # Try to parse as integer (user_id)
            user_id_int = int(user_id)
            query = query.filter(ActivityLog.user_id == user_id_int)
        except ValueError:
            # If not an integer, treat as profile ID and look up the user_id
            if user_id.startswith("STF-"):
                staff = db.query(Staff).filter(Staff.id == user_id).first()
                if staff:
                    query = query.filter(ActivityLog.user_id == staff.user_id)
                else:
                    # Staff not found, return empty result
                    query = query.filter(ActivityLog.user_id == -1)
            elif user_id.startswith("TCH-"):
                from app.models.teachers import Teacher
                teacher = db.query(Teacher).filter(Teacher.id == user_id).first()
                if teacher:
                    query = query.filter(ActivityLog.user_id == teacher.user_id)
                else:
                    query = query.filter(ActivityLog.user_id == -1)
            else:
                # Try to find student by ID (students have integer IDs)
                try:
                    student_id = int(user_id)
                    from app.models.students import Student
                    student = db.query(Student).filter(Student.id == student_id).first()
                    if student:
                        query = query.filter(ActivityLog.user_id == student.user_id)
                    else:
                        query = query.filter(ActivityLog.user_id == -1)
                except ValueError:
                    # Invalid format, return empty result
                    query = query.filter(ActivityLog.user_id == -1)
    if action_type:
        query = query.filter(ActivityLog.action_type == action_type)
    if resource_type:
        query = query.filter(ActivityLog.resource_type == resource_type)
    
    # ✅ Date filtering
    if from_date and to_date:
        query = query.filter(
            and_(
                func.date(ActivityLog.created_at) >= from_date,
                func.date(ActivityLog.created_at) <= to_date,
            )
        )
    elif from_date:
        query = query.filter(func.date(ActivityLog.created_at) >= from_date)
    elif to_date:
        query = query.filter(func.date(ActivityLog.created_at) <= to_date)
    
    # Get total count
    total_count = query.count()
    
    # Get paginated results
    logs = (
        query.order_by(ActivityLog.created_at.desc())
        .offset(pagination.offset())
        .limit(pagination.limit())
        .all()
    )
    
    # Format response with user names
    result = []
    for log in logs:
        user = db.query(User).filter(User.id == log.user_id).first()
        user_name = user.name if user else None
        result.append({
            "id": log.id,
            "user_id": log.user_id,
            "user_name": user_name,
            "user_role": log.user_role,
            "school_id": log.school_id,
            "action_type": log.action_type.value,
            "resource_type": log.resource_type.value,
            "resource_id": log.resource_id,
            "description": log.description,
            "action_metadata": log.action_metadata,
            "created_at": log.created_at.isoformat() if log.created_at else None
        })
    
    return pagination.format_response(result, total_count)


@router.get("/staff-list/", response_model=dict)
def get_staff_list(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.SCHOOL)),
    pagination: PaginationParams = Depends(),
    staff_name: Optional[str] = Query(None, description="Filter by staff name"),
):
    """
    Get list of all staff members under the school.
    Only school users can access this endpoint.
    Returns: staff name, permissions, roll number (staff.id), date of joining, and activity logs count.
    """
    # Get school
    school = db.query(School).filter(School.user_id == current_user.id).first()
    if not school:
        raise HTTPException(status_code=404, detail="School profile not found.")
    
    # Build base query for staff
    query = db.query(Staff).filter(Staff.school_id == school.id)
    
    # Apply name filter
    if staff_name:
        query = query.filter(
            (Staff.first_name.ilike(f"%{staff_name}%")) |
            (Staff.last_name.ilike(f"%{staff_name}%"))
        )
    
    # Get total count before pagination
    total_count = query.count()
    
    # Get paginated staff
    staff_members = (
        query.order_by(Staff.created_at.desc())
        .offset(pagination.offset())
        .limit(pagination.limit())
        .all()
    )
    
    # Build response with permissions and activity log counts
    result = []
    for staff in staff_members:
        # Get permissions for this staff
        permissions = get_staff_permissions(staff.id, db)
        
        # Count activity logs for this staff's user
        activity_logs_count = db.query(ActivityLog).filter(
            ActivityLog.user_id == staff.user_id,
            ActivityLog.school_id == school.id
        ).count()
        
        result.append({
            "staff_id": staff.id,
            "staff_name": f"{staff.first_name} {staff.last_name}",
            "roll_number": staff.id,  # Using staff.id as roll number
            "permissions": permissions,
            "date_of_joining": staff.created_at.isoformat() if staff.created_at else None,
            "activity_logs_count": activity_logs_count
        })
    
    return pagination.format_response(result, total_count)

