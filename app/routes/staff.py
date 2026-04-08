from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
import re
from datetime import date, datetime
from calendar import month_name

from app.core.dependencies import get_current_user
from app.core.security import get_password_hash
from app.db.session import get_db
from app.models.school import School
from app.models.staff import (
    Staff,
    ActivityLog,
    staff_permissions,
    StaffPermissionType,
    ActionType,
    ResourceType,
    DesignationCompensationTemplate,
    EmployeeCompensation,
)
from app.models.teachers import TeacherStaffPayment, TeacherStaffPaymentTransaction
from app.models.users import User
from app.schemas.staff import (
    StaffCreateRequest,
    StaffResponse,
    StaffResponseWithCompensation,
    StaffUpdateRequest,
    StaffPermissionAssignRequest,
    StaffPermissionResponse,
    ActivityLogResponse,
    DesignationCompensationTemplateUpsert,
)
from app.schemas.teachers import TeacherStaffPaymentRequest, TeacherStaffPaymentTransactionResponse, PendingMonthResponse, BulkStaffPaymentRequest, BulkPaymentResponse, FailedPaymentItem, BulkStaffPaymentRequest, BulkPaymentResponse
from app.schemas.users import UserRole
from app.utils.email_utility import send_dynamic_email
from app.utils.permission import get_staff_permissions, require_roles, verify_school_business_access
from app.utils.staff_logging import log_action
from app.utils.staff_compensation import (
    serialize_employee_compensation,
    serialize_designation_template,
    staff_designation_for_display,
    sync_employee_compensation_from_designation_template,
)
from app.services.pagination import PaginationParams
from typing import Optional, List

router = APIRouter()


@router.post(
    "/create-staff/",
    status_code=status.HTTP_201_CREATED,
    response_model=StaffResponseWithCompensation,
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
) -> StaffResponseWithCompensation:
    """
    Create a staff account. Only school accounts have permission to create staff members.
    Creates both User and Staff profile, then emails credentials to the staff member.

    **Designation and benefits:** The school defines pay/benefits per designation via
    `PUT /staff/designation-compensation-template`. When `designation` is set on this request
    (exact match after trim, per school), that template is copied into `employee_compensation`
    for the new staff member (salary components, grade, extra benefits, leave entitlements, etc.).
    Call `GET /staff/designation-compensation?designation=...` from the UI to preview before submit.
    """
    # Permission check: Only SCHOOL role (business account) can create staff
    if current_user.role != UserRole.SCHOOL:
        raise HTTPException(status_code=403, detail="Only school accounts can create staff members.")
    
    # ✅ Verify business account access
    verify_school_business_access(current_user, db)

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

        sync_employee_compensation_from_designation_template(db, staff)

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
        
        # Create Staff Payment if payment data is provided
        if data.payment:
            staff_payment = TeacherStaffPayment(
                teacher_id=None,
                staff_id=staff.id,
                monthly_in_hand_salary=data.payment.monthly_in_hand_salary if data.payment.monthly_in_hand_salary is not None else 0.0,
                allowance=data.payment.allowance if data.payment.allowance is not None else 0.0,
                bonus=data.payment.bonus if data.payment.bonus is not None else 0.0,
                other_allowances=data.payment.other_allowances if data.payment.other_allowances is not None else 0.0,
                incentive_plan=data.payment.incentive_plan if data.payment.incentive_plan is not None else 0.0,
                health_care_insurance=data.payment.health_care_insurance if data.payment.health_care_insurance is not None else 0.0,
                skill_development=data.payment.skill_development if data.payment.skill_development is not None else 0.0
            )
            db.add(staff_payment)
        else:
            # Create default payment structure with all zeros if not provided
            staff_payment = TeacherStaffPayment(
                teacher_id=None,
                staff_id=staff.id,
                monthly_in_hand_salary=0.0,
                allowance=0.0,
                bonus=0.0,
                other_allowances=0.0,
                incentive_plan=0.0,
                health_care_insurance=0.0,
                skill_development=0.0
            )
            db.add(staff_payment)
        
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

    db.refresh(staff)
    base = StaffResponse.model_validate(staff)
    out = base.model_dump()
    out["designation"] = staff_designation_for_display(staff)
    return StaffResponseWithCompensation(
        **out,
        employee_compensation=serialize_employee_compensation(staff.compensation),
    )


@router.get("/designation-compensation")
def get_designation_compensation_preview(
    designation: str = Query(..., min_length=1, description="Staff designation (exact match after trim)."),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    When the school selects a designation in the UI, call this to load the saved compensation template
    (if any) for that designation. Use PUT /staff/designation-compensation-template to define templates.
    """
    if current_user.role != UserRole.SCHOOL:
        raise HTTPException(status_code=403, detail="Only school users can load designation compensation.")
    verify_school_business_access(current_user, db)
    school = db.query(School).filter(School.user_id == current_user.id).first()
    if not school:
        raise HTTPException(status_code=404, detail="School profile not found.")

    key = designation.strip()
    template = (
        db.query(DesignationCompensationTemplate)
        .filter(
            DesignationCompensationTemplate.school_id == school.id,
            DesignationCompensationTemplate.designation == key,
        )
        .first()
    )
    if not template:
        return {
            "designation": key,
            "has_template": False,
            "compensation": None,
        }
    return {
        "designation": key,
        "has_template": True,
        "compensation": serialize_designation_template(template),
    }


@router.get("/designation-compensation-templates")
def list_designation_compensation_templates(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Return every designation + compensation template the school has saved.
    Each `PUT /staff/designation-compensation-template` creates or updates one row; a school can
    have many rows (one per distinct designation string).
    """
    if current_user.role != UserRole.SCHOOL:
        raise HTTPException(status_code=403, detail="Only school users can list designation templates.")
    verify_school_business_access(current_user, db)
    school = db.query(School).filter(School.user_id == current_user.id).first()
    if not school:
        raise HTTPException(status_code=404, detail="School profile not found.")

    rows = (
        db.query(DesignationCompensationTemplate)
        .filter(DesignationCompensationTemplate.school_id == school.id)
        .order_by(DesignationCompensationTemplate.designation.asc())
        .all()
    )
    return {
        "count": len(rows),
        "items": [serialize_designation_template(t) for t in rows],
    }


@router.post("/designation-compensation-template")
def create_designation_compensation_template(
    data: DesignationCompensationTemplateUpsert,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Create a compensation template for a designation (per school).
    If the same designation already exists for the school, returns 400 (use PUT to update).
    """
    if current_user.role != UserRole.SCHOOL:
        raise HTTPException(status_code=403, detail="Only school users can manage designation templates.")
    verify_school_business_access(current_user, db)
    school = db.query(School).filter(School.user_id == current_user.id).first()
    if not school:
        raise HTTPException(status_code=404, detail="School profile not found.")

    payload = data.model_dump()
    designation_key = payload.pop("designation", "").strip()
    if not designation_key:
        raise HTTPException(status_code=400, detail="designation is required.")

    existing = (
        db.query(DesignationCompensationTemplate)
        .filter(
            DesignationCompensationTemplate.school_id == school.id,
            DesignationCompensationTemplate.designation == designation_key,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=400,
            detail="Template already exists for this designation. Use PUT /staff/designation-compensation-template to update.",
        )

    template = DesignationCompensationTemplate(
        school_id=school.id,
        designation=designation_key,
        **payload,
    )
    db.add(template)
    db.commit()
    db.refresh(template)
    return {
        "detail": "Designation compensation template created.",
        "compensation": serialize_designation_template(template),
    }


@router.put("/designation-compensation-template")
def upsert_designation_compensation_template(
    data: DesignationCompensationTemplateUpsert,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Create or replace the compensation template for a designation (per school).
    """
    if current_user.role != UserRole.SCHOOL:
        raise HTTPException(status_code=403, detail="Only school users can manage designation templates.")
    verify_school_business_access(current_user, db)
    school = db.query(School).filter(School.user_id == current_user.id).first()
    if not school:
        raise HTTPException(status_code=404, detail="School profile not found.")

    payload = data.model_dump()
    designation_key = payload.pop("designation", "").strip()
    if not designation_key:
        raise HTTPException(status_code=400, detail="designation is required.")

    template = (
        db.query(DesignationCompensationTemplate)
        .filter(
            DesignationCompensationTemplate.school_id == school.id,
            DesignationCompensationTemplate.designation == designation_key,
        )
        .first()
    )
    if template:
        for field, value in payload.items():
            setattr(template, field, value)
    else:
        template = DesignationCompensationTemplate(
            school_id=school.id,
            designation=designation_key,
            **payload,
        )
        db.add(template)
    db.commit()
    db.refresh(template)
    return {
        "detail": "Designation compensation template saved.",
        "compensation": serialize_designation_template(template),
    }


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

    # ✅ For SCHOOL users, verify business account access
    if current_user.role == UserRole.SCHOOL:
        verify_school_business_access(current_user, db)

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

    # Get payment/salary information from TeacherStaffPayment
    payment = db.query(TeacherStaffPayment).filter(TeacherStaffPayment.staff_id == staff.id).first()
    # Return default salary values (all zeros) if payment record doesn't exist
    if payment:
        salary = {
            "monthly_in_hand_salary": payment.monthly_in_hand_salary,
            "allowance": payment.allowance,
            "bonus": payment.bonus,
            "other_allowances": payment.other_allowances,
            "incentive_plan": payment.incentive_plan,
            "health_care_insurance": payment.health_care_insurance,
            "skill_development": payment.skill_development,
            "total_salary": (
                payment.monthly_in_hand_salary +
                payment.allowance +
                payment.bonus +
                payment.other_allowances +
                payment.incentive_plan +
                payment.health_care_insurance +
                payment.skill_development
            )
        }
    else:
        # Default salary values when payment record doesn't exist
        salary = {
            "monthly_in_hand_salary": 0.0,
            "allowance": 0.0,
            "bonus": 0.0,
            "other_allowances": 0.0,
            "incentive_plan": 0.0,
            "health_care_insurance": 0.0,
            "skill_development": 0.0,
            "total_salary": 0.0
        }

    return {
        "id": staff.id,
        "school_id": staff.school_id,
        "first_name": staff.first_name,
        "last_name": staff.last_name,
        "email": staff.email or (user.email if user else None),
        "phone": staff.phone or (user.phone if user else None),
        "designation": staff_designation_for_display(staff),
        "employee_type": staff.employee_type,
        "annual_salary": float(staff.annual_salary) if staff.annual_salary else None,
        "monthly_salary": round(monthly_salary, 2) if monthly_salary else None,
        "emergency_leave": staff.emergency_leave or 0,
        "casual_leave": staff.casual_leave or 0,
        "is_active": staff.is_active,
        "permissions": permissions,
        "salary": salary,
        "employee_compensation": serialize_employee_compensation(staff.compensation),
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

    # ✅ For SCHOOL users, verify business account access
    if current_user.role == UserRole.SCHOOL:
        verify_school_business_access(current_user, db)

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
        update_fields = data.model_dump(exclude_unset=True, exclude={"email", "phone", "payment"})
        for field, value in update_fields.items():
            if value is not None:
                setattr(staff, field, value)

        if data.email is not None:
            staff.email = data.email
        if data.phone is not None:
            staff.phone = data.phone

        # Handle payment/salary update if provided
        if data.payment is not None:
            # Get or create payment record
            payment = db.query(TeacherStaffPayment).filter(TeacherStaffPayment.staff_id == staff.id).first()
            if payment:
                # Update existing payment record
                payment.monthly_in_hand_salary = data.payment.monthly_in_hand_salary
                payment.allowance = data.payment.allowance
                payment.bonus = data.payment.bonus
                payment.other_allowances = data.payment.other_allowances
                payment.incentive_plan = data.payment.incentive_plan
                payment.health_care_insurance = data.payment.health_care_insurance
                payment.skill_development = data.payment.skill_development
            else:
                # Create new payment record
                payment = TeacherStaffPayment(
                    teacher_id=None,
                    staff_id=staff.id,
                    monthly_in_hand_salary=data.payment.monthly_in_hand_salary,
                    allowance=data.payment.allowance,
                    bonus=data.payment.bonus,
                    other_allowances=data.payment.other_allowances,
                    incentive_plan=data.payment.incentive_plan,
                    health_care_insurance=data.payment.health_care_insurance,
                    skill_development=data.payment.skill_development
                )
                db.add(payment)

        if "designation" in data.model_dump(exclude_unset=True):
            des = data.designation
            if des is None or (isinstance(des, str) and not des.strip()):
                staff.designation = None
                ec_row = (
                    db.query(EmployeeCompensation)
                    .filter(EmployeeCompensation.staff_id == staff.id)
                    .first()
                )
                if ec_row is not None:
                    ec_row.designation = None
            else:
                sync_employee_compensation_from_designation_template(db, staff)

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
                "designation": staff_designation_for_display(staff),
                "employee_type": staff.employee_type,
                "annual_salary": float(staff.annual_salary) if staff.annual_salary else None,
                "monthly_salary": round(monthly_salary, 2) if monthly_salary else None,
                "emergency_leave": staff.emergency_leave or 0,
                "casual_leave": staff.casual_leave or 0,
                "employee_compensation": serialize_employee_compensation(staff.compensation),
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
    
    # ✅ Verify business account access
    verify_school_business_access(current_user, db)

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
    
    # ✅ For SCHOOL users, verify business account access
    if current_user.role == UserRole.SCHOOL:
        verify_school_business_access(current_user, db)
    
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
        verify_school_business_access(current_user, db)
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
    permission: Optional[str] = Query(None, description="Filter by permission type(s). Can be comma-separated for multiple (e.g., 'teacher,students,exams')"),
    from_date: Optional[date] = Query(None, description="Filter from this start date (date of joining)"),
    to_date: Optional[date] = Query(None, description="Filter until this end date (date of joining)"),
):
    """
    Get list of all staff members under the school.
    Only school users can access this endpoint.
    Returns: staff name, designation, compensation details, permissions, email, phone,
    date of joining, activity logs count, salary.
    """
    # Get school
    school = db.query(School).filter(School.user_id == current_user.id).first()
    if not school:
        raise HTTPException(status_code=404, detail="School profile not found.")
    
    # Build base query for staff
    query = db.query(Staff).filter(Staff.school_id == school.id)
    
    # ✅ Apply name filter (searches in concatenated full name)
    if staff_name:
        query = query.filter(
            func.concat(Staff.first_name, " ", Staff.last_name).ilike(f"%{staff_name.strip()}%")
        )
    
    # ✅ Apply date filters (date of joining)
    if from_date and to_date:
        query = query.filter(
            and_(
                func.date(Staff.created_at) >= from_date,
                func.date(Staff.created_at) <= to_date,
            )
        )
    elif from_date:
        query = query.filter(func.date(Staff.created_at) >= from_date)
    elif to_date:
        query = query.filter(func.date(Staff.created_at) <= to_date)
    
    # ✅ Apply permission filter (supports multiple comma-separated permissions)
    if permission:
        permission_list = [p.strip() for p in permission.split(",") if p.strip()]
        valid_permissions = []
        
        for perm_str in permission_list:
            try:
                perm_enum = StaffPermissionType(perm_str)
                valid_permissions.append(perm_enum)
            except ValueError:
                continue  # Skip invalid permissions
        
        if valid_permissions:
            # Join with staff_permissions table to filter by any of the specified permissions
            query = query.join(
                staff_permissions,
                Staff.id == staff_permissions.c.staff_id
            ).filter(
                staff_permissions.c.permission.in_(valid_permissions)
            ).distinct()
        else:
            # No valid permissions, return empty result
            query = query.filter(Staff.id == None)
    
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
        
        # Get payment/salary information from TeacherStaffPayment
        payment = db.query(TeacherStaffPayment).filter(TeacherStaffPayment.staff_id == staff.id).first()
        # Return default salary values (all zeros) if payment record doesn't exist
        if payment:
            salary = {
                "monthly_in_hand_salary": payment.monthly_in_hand_salary,
                "allowance": payment.allowance,
                "bonus": payment.bonus,
                "other_allowances": payment.other_allowances,
                "incentive_plan": payment.incentive_plan,
                "health_care_insurance": payment.health_care_insurance,
                "skill_development": payment.skill_development,
                "total_salary": (
                    payment.monthly_in_hand_salary +
                    payment.allowance +
                    payment.bonus +
                    payment.other_allowances +
                    payment.incentive_plan +
                    payment.health_care_insurance +
                    payment.skill_development
                )
            }
        else:
            # Default salary values when payment record doesn't exist
            salary = {
                "monthly_in_hand_salary": 0.0,
                "allowance": 0.0,
                "bonus": 0.0,
                "other_allowances": 0.0,
                "incentive_plan": 0.0,
                "health_care_insurance": 0.0,
                "skill_development": 0.0,
                "total_salary": 0.0
            }
        
        result.append({
            "staff_id": staff.id,
            "staff_name": f"{staff.first_name} {staff.last_name}",
            "designation": staff_designation_for_display(staff),
            "employee_compensation": serialize_employee_compensation(staff.compensation),
            "email": staff.email,
            "phone": staff.phone,
            "permissions": permissions,
            "date_of_joining": staff.created_at.isoformat() if staff.created_at else None,
            "activity_logs_count": activity_logs_count,
            "salary": salary
        })
    
    return pagination.format_response(result, total_count)


def get_months_between_dates(start_date: date, end_date: date) -> List[str]:
    """Generate list of months (YYYY-MM format) between two dates"""
    months = []
    current = start_date.replace(day=1)  # Start from first day of month
    end = end_date.replace(day=1)
    
    while current <= end:
        months.append(current.strftime("%Y-%m"))
        # Move to next month
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)
    
    return months


@router.post(
    "/{staff_id}/payments/",
    status_code=status.HTTP_201_CREATED,
    response_model=TeacherStaffPaymentTransactionResponse,
    summary="Make payment to staff",
    description="Record a monthly payment for a staff member. Prevents duplicate payments for the same month."
)
def make_staff_payment(
    staff_id: str,
    data: TeacherStaffPaymentRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Make a payment to a staff member for a specific month"""
    # Only school users can make payments
    if current_user.role != UserRole.SCHOOL:
        raise HTTPException(status_code=403, detail="Only school users can make payments.")
    
    # ✅ Verify business account access
    verify_school_business_access(current_user, db)
    
    # Get school
    school = db.query(School).filter(School.user_id == current_user.id).first()
    if not school:
        raise HTTPException(status_code=404, detail="School profile not found.")
    
    # Get staff
    staff = db.query(Staff).filter(
        Staff.id == staff_id,
        Staff.school_id == school.id
    ).first()
    if not staff:
        raise HTTPException(status_code=404, detail="Staff not found or doesn't belong to your school.")
    
    # Get or create payment structure
    payment_structure = db.query(TeacherStaffPayment).filter(
        TeacherStaffPayment.staff_id == staff.id
    ).first()
    
    if not payment_structure:
        raise HTTPException(
            status_code=400,
            detail="Payment structure not found. Please set up payment structure for this staff member first."
        )
    
    # Validate payment month format (YYYY-MM)
    try:
        payment_month_date = datetime.strptime(data.payment_month, "%Y-%m").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payment_month format. Use YYYY-MM format (e.g., '2025-01').")
    
    # Check if payment already exists for this month
    existing_payment = db.query(TeacherStaffPaymentTransaction).filter(
        and_(
            TeacherStaffPaymentTransaction.staff_id == staff_id,
            TeacherStaffPaymentTransaction.payment_month == data.payment_month
        )
    ).first()
    
    if existing_payment:
        raise HTTPException(
            status_code=400,
            detail=f"Payment for month {data.payment_month} already exists. Each month can only be paid once."
        )
    
    # Validate that payment month is not in the future
    current_month = date.today().replace(day=1)
    if payment_month_date > current_month:
        raise HTTPException(
            status_code=400,
            detail="Cannot make payment for future months."
        )
    
    try:
        # Create payment transaction
        transaction = TeacherStaffPaymentTransaction(
            payment_structure_id=payment_structure.id,
            teacher_id=None,
            staff_id=staff_id,
            payment_month=data.payment_month,
            total_amount=data.total_amount,
            payment_mode=data.payment_mode,
            release_date=data.release_date,
            created_by=current_user.id
        )
        db.add(transaction)
        db.commit()
        db.refresh(transaction)
        
        return transaction
        
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@router.post(
    "/bulk-payments/",
    status_code=status.HTTP_201_CREATED,
    response_model=BulkPaymentResponse,
    summary="Make bulk payments to multiple staff members",
    description="Record monthly payments for multiple staff members at once. Prevents duplicate payments for the same month."
)
def make_bulk_staff_payments(
    data: BulkStaffPaymentRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Make payments to multiple staff members for a specific month"""
    # Only school users can make payments
    if current_user.role != UserRole.SCHOOL:
        raise HTTPException(status_code=403, detail="Only school users can make payments.")
    
    # ✅ Verify business account access
    verify_school_business_access(current_user, db)
    
    # Get school
    school = db.query(School).filter(School.user_id == current_user.id).first()
    if not school:
        raise HTTPException(status_code=404, detail="School profile not found.")
    
    successful_payments = []
    failed_payments = []
    
    try:
        for payment_item in data.payments:
            staff_id = payment_item.staff_id
            total_amount = payment_item.total_amount
            payment_month = payment_item.payment_month
            release_date = payment_item.release_date
            payment_mode = payment_item.payment_mode
            
            # Validate payment month format (YYYY-MM)
            try:
                payment_month_date = datetime.strptime(payment_month, "%Y-%m").date()
            except ValueError:
                failed_payments.append(FailedPaymentItem(
                    teacher_id=None,
                    staff_id=staff_id,
                    error="Invalid payment_month format. Use YYYY-MM format (e.g., '2025-01')."
                ))
                continue
            
            # Validate that payment month is not in the future
            current_month = date.today().replace(day=1)
            if payment_month_date > current_month:
                failed_payments.append(FailedPaymentItem(
                    teacher_id=None,
                    staff_id=staff_id,
                    error="Cannot make payment for future months."
                ))
                continue
            
            # Get staff
            staff = db.query(Staff).filter(
                Staff.id == staff_id,
                Staff.school_id == school.id
            ).first()
            
            if not staff:
                failed_payments.append(FailedPaymentItem(
                    teacher_id=None,
                    staff_id=staff_id,
                    error="Staff not found or doesn't belong to your school"
                ))
                continue
            
            # Get payment structure
            payment_structure = db.query(TeacherStaffPayment).filter(
                TeacherStaffPayment.staff_id == staff.id
            ).first()
            
            if not payment_structure:
                failed_payments.append(FailedPaymentItem(
                    teacher_id=None,
                    staff_id=staff_id,
                    error="Payment structure not found. Please set up payment structure for this staff member first."
                ))
                continue
            
            # Check if payment already exists for this month
            existing_payment = db.query(TeacherStaffPaymentTransaction).filter(
                and_(
                    TeacherStaffPaymentTransaction.staff_id == staff_id,
                    TeacherStaffPaymentTransaction.payment_month == payment_month
                )
            ).first()
            
            if existing_payment:
                failed_payments.append(FailedPaymentItem(
                    teacher_id=None,
                    staff_id=staff_id,
                    error=f"Payment for month {payment_month} already exists. Each month can only be paid once."
                ))
                continue
            
            # Create payment transaction
            transaction = TeacherStaffPaymentTransaction(
                payment_structure_id=payment_structure.id,
                teacher_id=None,
                staff_id=staff_id,
                payment_month=payment_month,
                total_amount=total_amount,
                payment_mode=payment_mode,
                release_date=release_date,
                created_by=current_user.id
            )
            db.add(transaction)
            successful_payments.append(transaction)
        
        # Commit all successful payments at once
        db.commit()
        
        # Refresh all successful transactions
        for transaction in successful_payments:
            db.refresh(transaction)
        
        return BulkPaymentResponse(
            success_count=len(successful_payments),
            failed_count=len(failed_payments),
            successful_payments=successful_payments,
            failed_payments=failed_payments
        )
        
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@router.get(
    "/{staff_id}/payments/",
    response_model=List[TeacherStaffPaymentTransactionResponse],
    summary="Get staff payment history",
    description="Get all payment transactions for a staff member"
)
def get_staff_payment_history(
    staff_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get payment history for a staff member"""
    # Allow school and staff users
    if current_user.role not in [UserRole.SCHOOL, UserRole.STAFF]:
        raise HTTPException(status_code=403, detail="Only school and staff users can view payment history.")
    
    # Get school
    if current_user.role == UserRole.SCHOOL:
        verify_school_business_access(current_user, db)
        school = db.query(School).filter(School.user_id == current_user.id).first()
        if not school:
            raise HTTPException(status_code=404, detail="School profile not found.")
    else:  # STAFF - can only view their own payment history
        staff_member = db.query(Staff).filter(Staff.user_id == current_user.id).first()
        if not staff_member:
            raise HTTPException(status_code=404, detail="Staff profile not found.")
        if staff_member.id != staff_id:
            raise HTTPException(status_code=403, detail="You can only view your own payment history.")
        school = db.query(School).filter(School.id == staff_member.school_id).first()
        if not school:
            raise HTTPException(status_code=404, detail="School not found.")
    
    # Get staff
    staff = db.query(Staff).filter(
        Staff.id == staff_id,
        Staff.school_id == school.id
    ).first()
    if not staff:
        raise HTTPException(status_code=404, detail="Staff not found or doesn't belong to your school.")
    
    # Get payment transactions
    transactions = db.query(TeacherStaffPaymentTransaction).filter(
        TeacherStaffPaymentTransaction.staff_id == staff_id
    ).order_by(TeacherStaffPaymentTransaction.payment_month.desc()).all()
    
    return transactions


@router.get(
    "/{staff_id}/payments/pending-months/",
    response_model=List[PendingMonthResponse],
    summary="Get pending payment months for staff",
    description="Get list of months that need payment, calculated from staff's created_at date"
)
def get_staff_pending_months(
    staff_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get pending payment months for a staff member"""
    # Allow school and staff users
    if current_user.role not in [UserRole.SCHOOL, UserRole.STAFF]:
        raise HTTPException(status_code=403, detail="Only school and staff users can view pending months.")
    
    # Get school
    if current_user.role == UserRole.SCHOOL:
        verify_school_business_access(current_user, db)
        school = db.query(School).filter(School.user_id == current_user.id).first()
        if not school:
            raise HTTPException(status_code=404, detail="School profile not found.")
    else:  # STAFF - can only view their own pending months
        staff_member = db.query(Staff).filter(Staff.user_id == current_user.id).first()
        if not staff_member:
            raise HTTPException(status_code=404, detail="Staff profile not found.")
        if staff_member.id != staff_id:
            raise HTTPException(status_code=403, detail="You can only view your own pending months.")
        school = db.query(School).filter(School.id == staff_member.school_id).first()
        if not school:
            raise HTTPException(status_code=404, detail="School not found.")
    
    # Get staff
    staff = db.query(Staff).filter(
        Staff.id == staff_id,
        Staff.school_id == school.id
    ).first()
    if not staff:
        raise HTTPException(status_code=404, detail="Staff not found or doesn't belong to your school.")
    
    # Calculate months from created_at to current month
    created_date = staff.created_at.date() if isinstance(staff.created_at, datetime) else staff.created_at
    current_date = date.today()
    
    # Get all months from created_at to current month
    all_months = get_months_between_dates(created_date, current_date)
    
    # Get paid months
    paid_transactions = db.query(TeacherStaffPaymentTransaction).filter(
        TeacherStaffPaymentTransaction.staff_id == staff_id
    ).all()
    paid_months = {t.payment_month for t in paid_transactions}
    
    # Build response
    result = []
    for month_str in all_months:
        month_date = datetime.strptime(month_str, "%Y-%m").date()
        month_name_str = f"{month_name[month_date.month]} {month_date.year}"
        
        # Find payment transaction for this month if paid
        payment_transaction = next(
            (t for t in paid_transactions if t.payment_month == month_str),
            None
        )
        
        result.append(PendingMonthResponse(
            month=month_str,
            month_name=month_name_str,
            is_paid=month_str in paid_months,
            payment_date=payment_transaction.release_date if payment_transaction else None
        ))
    
    return result

