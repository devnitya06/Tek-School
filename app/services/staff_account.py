"""Create staff User + Staff profile + payment row (school-linked or platform / admin)."""

from __future__ import annotations

import re
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.security import get_password_hash
from app.models.staff import Staff, staff_permissions
from app.models.teachers import TeacherStaffPayment
from app.models.users import User
from app.schemas.staff import StaffCreateRequest
from app.schemas.users import UserRole
from app.utils.staff_compensation import sync_employee_compensation_from_designation_template
from app.utils.permission import normalize_staff_permissions


def map_staff_creation_sql_error(exc: SQLAlchemyError) -> HTTPException:
    """Map DB errors from staff creation to HTTP (same behaviour as school create-staff)."""
    error_message = str(exc)
    field_name = None
    error_detail = "Database error occurred"

    if "enum" in error_message.lower() and "userrole" in error_message.lower():
        field_name = "role"
        error_detail = (
            "Invalid role value. The 'role' field must be one of: superadmin, admin, school, "
            "teacher, student, staff"
        )
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
    elif "invalid input" in error_message.lower():
        match = re.search(r'for enum \w+: "(\w+)"', error_message)
        if match:
            field_name = "role"
            invalid_value = match.group(1)
            error_detail = (
                f"Invalid role value '{invalid_value}'. Valid values are: superadmin, admin, school, "
                "teacher, student, staff"
            )
        else:
            field_name = "unknown"
            error_detail = "Invalid data format for one or more fields"

    error_response = {
        "detail": error_detail,
        "error_type": "database_error",
    }
    if field_name:
        error_response["field"] = field_name
        error_response["message"] = f"Error in field '{field_name}': {error_detail}"

    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=error_response if field_name else error_detail,
    )


def persist_staff_account(
    db: Session,
    data: StaffCreateRequest,
    school_id: Optional[str],
    creator_user: User,
) -> Staff:
    """
    Create User (role STAFF), Staff row, optional permissions, TeacherStaffPayment defaults.
    `school_id` None = platform staff (admin/superadmin), not tied to a school.
    Commits on success; rolls back and re-raises SQLAlchemyError on failure.
    """
    try:
        if data.immidiate_boss:
            immediate_boss = db.query(Staff).filter(Staff.id == data.immidiate_boss).first()
            if not immediate_boss:
                raise HTTPException(status_code=404, detail="immidiate_boss staff not found.")
            if school_id and immediate_boss.school_id != school_id:
                raise HTTPException(status_code=400, detail="immidiate_boss must belong to the same school.")

        if data.super_boss:
            super_boss = db.query(Staff).filter(Staff.id == data.super_boss).first()
            if not super_boss:
                raise HTTPException(status_code=404, detail="super_boss staff not found.")
            if school_id and super_boss.school_id != school_id:
                raise HTTPException(status_code=400, detail="super_boss must belong to the same school.")

        staff_user = User(
            name=f"{data.first_name} {data.last_name}",
            email=data.email,
            phone=data.phone,
            location=creator_user.location,
            website=creator_user.website,
            role=UserRole.STAFF,
            hashed_password=get_password_hash(data.password),
            is_verified=True,
        )
        db.add(staff_user)
        db.flush()

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
            immidiate_boss=data.immidiate_boss,
            super_boss=data.super_boss,
            mark_in_time=data.mark_in_time,
            mark_out_time=data.mark_out_time,
            employee_grade=data.employee_grade,
            is_active_hr_service=data.is_active_hr_service if data.is_active_hr_service is not None else False,
            hiring_for_board=data.hiring_for_board,
            teaching_language=data.teaching_language,
            subjects=data.subjects,
            assigned_class=data.assigned_class,
            assigned_subjects=data.assigned_subjects,
            school_id=school_id,
            user_id=staff_user.id,
        )
        db.add(staff)
        db.flush()

        sync_employee_compensation_from_designation_template(db, staff)

        if data.permissions:
            normalized_permissions = normalize_staff_permissions(data.permissions)
            for permission in normalized_permissions:
                db.execute(
                    staff_permissions.insert().values(
                        staff_id=staff.id,
                        permission=permission.value,
                        granted_by=creator_user.id,
                    )
                )

        if data.payment:
            staff_payment = TeacherStaffPayment(
                teacher_id=None,
                staff_id=staff.id,
                monthly_in_hand_salary=data.payment.monthly_in_hand_salary
                if data.payment.monthly_in_hand_salary is not None
                else 0.0,
                allowance=data.payment.allowance if data.payment.allowance is not None else 0.0,
                bonus=data.payment.bonus if data.payment.bonus is not None else 0.0,
                other_allowances=data.payment.other_allowances
                if data.payment.other_allowances is not None
                else 0.0,
                incentive_plan=data.payment.incentive_plan
                if data.payment.incentive_plan is not None
                else 0.0,
                health_care_insurance=data.payment.health_care_insurance
                if data.payment.health_care_insurance is not None
                else 0.0,
                skill_development=data.payment.skill_development
                if data.payment.skill_development is not None
                else 0.0,
            )
            db.add(staff_payment)
        else:
            db.add(
                TeacherStaffPayment(
                    teacher_id=None,
                    staff_id=staff.id,
                    monthly_in_hand_salary=0.0,
                    allowance=0.0,
                    bonus=0.0,
                    other_allowances=0.0,
                    incentive_plan=0.0,
                    health_care_insurance=0.0,
                    skill_development=0.0,
                )
            )

        db.commit()
        db.refresh(staff)
        return staff
    except SQLAlchemyError:
        db.rollback()
        raise
