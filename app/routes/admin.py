from fastapi import (
    APIRouter,
    Depends,
    Form,
    File,
    UploadFile,
    HTTPException,
    status,
    Query,
)
from sqlalchemy.orm import Session, joinedload
from app.db.session import get_db
from app.utils.s3 import upload_to_s3
from app.models.admin import *
from app.models.school import (
    School,
    StudentExamData,
    SchoolBoard,
    SchoolMedium,
    SchoolType,
    HomeAssignment,
    SupportPlus,
    SupportPlusStatus,
    BusinessInquiry,
)
from app.models.users import User
from app.models.teachers import Teacher, TeacherClassSectionSubject
from app.models.students import Student, StudentStatus, SelfSignedStudent
from app.models.staff import Staff, staff_permissions, StaffPermissionType
from app.schemas.admin import *
from app.schemas.school import (
    SchoolRatingCreate,
    SchoolRatingResponse,
    SupportPlusResponse,
    SupportPlusStatusUpdate,
    BusinessInquiryResponse,
)
from app.services.students import update_admin_exam_class_ranks
from app.models.admin import *
from app.models.school import *
from app.models.teachers import *
from sqlalchemy.exc import SQLAlchemyError
from app.utils.permission import (
    require_roles,
    get_staff_permissions,
    has_staff_permission,
    normalize_staff_permissions,
)
from app.schemas.users import UserRole
from sqlalchemy import func, cast, String, case, or_, and_
from collections import defaultdict
from calendar import monthrange
from app.core.dependencies import get_current_user
from typing import Optional, List
from app.services.pagination import PaginationParams
from datetime import datetime, timedelta, date, timezone
from app.utils.services import get_validity_days
from app.utils.razorpay_client import razorpay_client
from sqlalchemy.orm import joinedload
from app.services.staff_account import (
    persist_staff_account,
    map_staff_creation_sql_error,
)
from app.schemas.staff import (
    StaffCreateRequest,
    StaffResponse,
    StaffResponseWithCompensation,
    StaffPermissionAssignRequest,
)
from app.utils.staff_compensation import (
    serialize_employee_compensation,
    staff_designation_for_display,
)
from app.utils.email_utility import send_dynamic_email

from app.models.admin import HolidayMaster
from app.schemas.admin import HolidayMasterResponse


router = APIRouter()


def _ensure_admin_staff_permission(
    current_user: User,
    db: Session,
    permission: StaffPermissionType,
) -> None:
    """
    In admin routes: admins/superadmins are fully allowed.
    STAFF must be platform staff (school_id null) and hold the given permission.
    """
    if current_user.role in (UserRole.ADMIN, UserRole.SUPERADMIN):
        return
    if current_user.role != UserRole.STAFF:
        return

    staff = db.query(Staff).filter(Staff.user_id == current_user.id).first()
    if not staff:
        raise HTTPException(status_code=404, detail="Staff profile not found.")
    if staff.school_id is not None:
        raise HTTPException(
            status_code=403,
            detail="School staff cannot access admin-staff features.",
        )
    if not has_staff_permission(staff.id, permission, db):
        raise HTTPException(
            status_code=403,
            detail=f"You do not have '{permission.value}' permission.",
        )


@router.post(
    "/platform-staff/",
    status_code=status.HTTP_201_CREATED,
    response_model=StaffResponseWithCompensation,
    summary="Create platform staff (no school)",
    description=(
        "Admin or superadmin only. Creates a User with role STAFF and a Staff profile with "
        "`school_id` null (not under any school). Same JSON body as `POST /staff/create-staff/`. "
        "Designation templates do not apply (no school); optional `designation` is stored on staff/compensation only."
    ),
)
def create_platform_staff(
    data: StaffCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.SUPERADMIN)),
) -> StaffResponseWithCompensation:
    existing_user = db.query(User).filter(User.email == data.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already exists.")

    try:
        staff = persist_staff_account(db, data, None, current_user)
    except SQLAlchemyError as exc:
        raise map_staff_creation_sql_error(exc) from exc

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


@router.put("/platform-staff/{staff_id}/permissions")
def assign_platform_staff_permissions(
    staff_id: str,
    data: StaffPermissionAssignRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.SUPERADMIN)),
):
    """
    Assign/replace permissions for platform staff (school_id is NULL).
    """
    staff = db.query(Staff).filter(Staff.id == staff_id).first()
    if not staff:
        raise HTTPException(status_code=404, detail="Staff not found.")
    if staff.school_id is not None:
        raise HTTPException(
            status_code=400,
            detail="Only platform/admin staff (school_id is null) can be managed here.",
        )

    try:
        db.execute(staff_permissions.delete().where(staff_permissions.c.staff_id == staff_id))
        normalized_permissions = normalize_staff_permissions(data.permissions)
        for permission in normalized_permissions:
            db.execute(
                staff_permissions.insert().values(
                    staff_id=staff_id,
                    permission=permission.value,
                    granted_by=current_user.id,
                )
            )
        db.commit()
        return {
            "detail": "Platform staff permissions updated successfully.",
            "staff_id": staff_id,
            "staff_name": f"{staff.first_name} {staff.last_name}",
            "permissions": get_staff_permissions(staff_id, db),
        }
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@router.get("/platform-staff/{staff_id}/permissions")
def get_platform_staff_permissions(
    staff_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.SUPERADMIN)),
):
    staff = db.query(Staff).filter(Staff.id == staff_id).first()
    if not staff:
        raise HTTPException(status_code=404, detail="Staff not found.")
    if staff.school_id is not None:
        raise HTTPException(
            status_code=400,
            detail="Only platform/admin staff (school_id is null) can be viewed here.",
        )
    return {
        "staff_id": staff.id,
        "staff_name": f"{staff.first_name} {staff.last_name}",
        "permissions": get_staff_permissions(staff.id, db),
    }


@router.get("/platform-staff/permissions/my")
def get_my_platform_staff_permissions(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.STAFF)),
):
    staff = db.query(Staff).filter(Staff.user_id == current_user.id).first()
    if not staff:
        raise HTTPException(status_code=404, detail="Staff profile not found.")
    if staff.school_id is not None:
        raise HTTPException(status_code=403, detail="Only platform/admin staff can use this endpoint.")
    return {
        "staff_id": staff.id,
        "staff_name": f"{staff.first_name} {staff.last_name}",
        "permissions": get_staff_permissions(staff.id, db),
    }


@router.post("/account-credit/configuration/")
def create_account_credit_config(
    config_data: ConfigurationCreateSchema,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(UserRole.ADMIN)),
):
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin account is allowed to create configurations.",
        )

    try:
        # Optional: If you want to clear previous configurations
        db.query(AccountConfiguration).delete()
        db.query(CreditConfiguration).delete()

        # Save all account configurations
        for config in config_data.account_configurations:
            account_config = AccountConfiguration(**config.dict())
            db.add(account_config)

        # Save all credit configurations
        for credit in config_data.credit_configurations:
            credit_config = CreditConfiguration(**credit.dict())
            db.add(credit_config)

        db.commit()
        return {"detail": "Configurations saved successfully."}

    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error occurred: {str(e)}",
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error occurred: {str(e)}",
        )


@router.post("/account-configurations/", status_code=status.HTTP_201_CREATED)
def create_account_configurations(
    data: list[AccountConfigurationCreate],
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(UserRole.ADMIN)),
):
    existing_names = {name for (name,) in db.query(AccountConfiguration.name).all()}

    for item in data:
        if item.name in existing_names:
            raise HTTPException(
                status_code=400, detail=f"Configuration '{item.name}' already exists"
            )

        db.add(AccountConfiguration(**item.dict()))

    db.commit()
    return {"detail": "Account configurations created successfully."}


@router.get(
    "/account-configurations/", response_model=list[AccountConfigurationResponse]
)
def get_account_configurations(
    db: Session = Depends(get_db), current_user=Depends(require_roles(UserRole.ADMIN))
):
    return db.query(AccountConfiguration).order_by(AccountConfiguration.id.asc()).all()


@router.get(
    "/account-configurations/{config_id}", response_model=AccountConfigurationResponse
)
def get_single_account_configuration(
    config_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(UserRole.ADMIN)),
):
    config = (
        db.query(AccountConfiguration)
        .filter(AccountConfiguration.id == config_id)
        .first()
    )

    if not config:
        raise HTTPException(status_code=404, detail="Configuration not found")

    return config


@router.put("/account-configurations/{config_id}")
def update_account_configuration(
    config_id: int,
    data: AccountConfigurationUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(UserRole.ADMIN)),
):
    config = (
        db.query(AccountConfiguration)
        .filter(AccountConfiguration.id == config_id)
        .first()
    )

    if not config:
        raise HTTPException(status_code=404, detail="Configuration not found")

    print("BEFORE:", config.value)
    config.value = data.value

    db.commit()
    db.refresh(config)

    print("AFTER:", config.value)

    return {
        "detail": "Account configuration updated successfully.",
        "updated_value": config.value,
    }


@router.get("/all-school/")
def get_all_school(
    school_name: Optional[str] = None,
    school_id: Optional[str] = None,
    status: Optional[bool] = None,  # True = active, False = inactive
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    pagination: PaginationParams = Depends(),
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(UserRole.ADMIN)),
):
    # Admin check
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=403, detail="Only admin account is allowed to view all schools."
        )

    try:
        # Base Query
        query = db.query(School)

        # Filters
        if school_name:
            query = query.filter(School.school_name.ilike(f"%{school_name}%"))

        if school_id:
            query = query.filter(School.id == school_id)

        if status is not None:
            query = query.filter(School.is_active == status)

        if start_date:
            query = query.filter(School.created_at >= start_date)

        if end_date:
            query = query.filter(School.created_at <= end_date)

        # Count before pagination
        total_count = query.count()

        # Apply pagination
        schools = (
            query.order_by(School.created_at.desc())
            .offset(pagination.offset())
            .limit(pagination.limit())
            .all()
        )

        if not schools:
            return pagination.format_response([], total_count=0)

        result = []

        for school in schools:
            # Count teachers
            teacher_count = (
                db.query(func.count())
                .select_from(Teacher)
                .filter(Teacher.school_id == school.id)
                .scalar()
            )

            # Count students
            student_count = (
                db.query(func.count())
                .select_from(Student)
                .filter(Student.school_id == school.id)
                .scalar()
            )

            # Count ACTIVE students
            active_student_count = (
                db.query(func.count())
                .select_from(Student)
                .filter(
                    Student.school_id == school.id,
                    Student.status == StudentStatus.ACTIVE,
                )
                .scalar()
            )

            # Count INACTIVE students
            inactive_student_count = (
                db.query(func.count())
                .select_from(Student)
                .filter(
                    Student.school_id == school.id,
                    Student.status == StudentStatus.INACTIVE,
                )
                .scalar()
            )

            # Related user
            user = db.query(User).filter(User.id == school.user_id).first()

            # Build result
            result.append(
                {
                    "school_id": school.id,
                    "school_name": school.school_name,
                    "location": user.location if user else None,
                    "no_of_teachers": teacher_count,
                    "no_of_students": student_count,
                    "active_students": active_student_count,
                    "inactive_students": inactive_student_count,
                    "created_at": school.created_at,
                    "is_active": school.is_active,
                    "is_verified": school.is_verified,
                    "principal_name": school.principal_name,
                }
            )

        return pagination.format_response(result, total_count=total_count)

    except SQLAlchemyError as e:
        raise HTTPException(
            status_code=500, detail=f"Database error occurred: {str(e)}"
        )


@router.put("/school/{school_id}/verify/")
def verify_school(
    school_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(UserRole.ADMIN)),
):
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin account is allowed to verify schools.",
        )

    try:
        school = db.query(School).filter(School.id == school_id).first()
        if not school:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="School not found."
            )
        user = db.query(User).filter(User.id == school.user_id).first()
        user.is_verified = True
        school.is_verified = True
        existing_credit = (
            db.query(CreditMaster).filter(CreditMaster.school_id == school.id).first()
        )
        if not existing_credit:
            credit_master = CreditMaster(school_id=school.id, earned_credit=100)
            db.add(credit_master)
        db.commit()
        return {"detail": "School verified successfully."}

    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error occurred: {str(e)}",
        )


@router.get("/platform-summary/")
def get_admin_platform_summary(
    month: int = Query(..., ge=1, le=12, description="Calendar month (1-12)"),
    year: int = Query(..., ge=2000, le=2100, description="Four-digit year"),
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(UserRole.ADMIN)),
):
    period_start_date = date(year, month, 1)
    period_end_date = date(year, month, monthrange(year, month)[1])
    range_start = datetime(year, month, 1)
    range_end_exclusive = (
        datetime(year + 1, 1, 1) if month == 12 else datetime(year, month + 1, 1)
    )

    def in_created_month(column):
        return and_(column >= range_start, column < range_end_exclusive)

    total_business_school_count = (
        db.query(func.count(School.id))
        .filter(
            School.account_type == SchoolAccountType.BUSINESS,
            in_created_month(School.created_at),
        )
        .scalar()
    ) or 0

    total_listing_school_count = (
        db.query(func.count(School.id))
        .filter(
            School.account_type == SchoolAccountType.LISTING,
            in_created_month(School.created_at),
        )
        .scalar()
    ) or 0

    total_teachers = (
        db.query(func.count(Teacher.id))
        .filter(in_created_month(Teacher.created_at))
        .scalar()
    ) or 0

    total_students = (
        db.query(func.count(Student.id))
        .filter(in_created_month(Student.created_at))
        .scalar()
    ) or 0

    total_self_signup_students = (
        db.query(func.count(SelfSignedStudent.id))
        .filter(in_created_month(SelfSignedStudent.created_at))
        .scalar()
    ) or 0

    return {
        "month": month,
        "year": year,
        "period_start": period_start_date.isoformat(),
        "period_end": period_end_date.isoformat(),
        "total_business_school_count": total_business_school_count,
        "total_listing_school_count": total_listing_school_count,
        "total_teachers": total_teachers,
        "total_students": total_students,
        "total_self_signup_students": total_self_signup_students,
    }


@router.get("/schools/")
def list_all_schools(
    pagination: PaginationParams = Depends(),
    school_id: Optional[str] = Query(
        None,
        description="Filter by school ID (exact match). No authentication required.",
    ),
    id: Optional[str] = Query(None, description="Alias for school_id (exact match)"),
    school_name: Optional[str] = Query(
        None, description="Filter by school name (partial match)"
    ),
    account_type: Optional[str] = Query(
        None, description="Filter by type: 'business' or 'listing'"
    ),
    is_business_approved: Optional[bool] = Query(
        None, description="Filter by is_business_approved (true/false)"
    ),
    state: Optional[str] = Query(None, description="Filter by state (partial match)"),
    district: Optional[List[str]] = Query(
        None,
        description="Filter by district (multiple, exact match). Pass multiple: ?district=Khorda&district=Cuttack",
    ),
    school_board: Optional[List[str]] = Query(
        None,
        description="Filter by school board (multiple). Values: cbse, icse, stateboard, ib, other",
    ),
    school_medium: Optional[List[str]] = Query(
        None,
        description="Filter by school medium (multiple). Values: english, hindi, bilingual, other",
    ),
    due_installment_type: Optional[List[str]] = Query(
        None,
        description="Filter by due_installment_type (multiple, JSON field contains any value)",
    ),
    teaching_method: Optional[List[str]] = Query(
        None,
        description="Filter by teaching_method (multiple, JSON field contains any value)",
    ),
    transportation_facility: Optional[bool] = Query(
        None, description="Filter by transportation_facility (true/false)"
    ),
    from_date: Optional[str] = Query(
        None, description="Filter by created_at from (YYYY-MM-DD)"
    ),
    to_date: Optional[str] = Query(
        None, description="Filter by created_at to (YYYY-MM-DD)"
    ),
    db: Session = Depends(get_db),
):
    """List all schools with filters. Public endpoint - no authentication required. Pass school_id to get a specific school."""
    query = db.query(School)
    filter_id = school_id or id
    if filter_id:
        query = query.filter(School.id == filter_id)
    if school_name:
        query = query.filter(School.school_name.ilike(f"%{school_name}%"))
    if account_type:
        at = account_type.lower()
        if at == "business":
            query = query.filter(School.account_type == SchoolAccountType.BUSINESS)
        elif at == "listing":
            query = query.filter(School.account_type == SchoolAccountType.LISTING)
        else:
            raise HTTPException(
                status_code=400, detail="account_type must be 'business' or 'listing'"
            )
    if is_business_approved is not None:
        query = query.filter(School.is_business_approved == is_business_approved)
    if state:
        query = query.filter(School.state.ilike(f"%{state}%"))
    if district:
        query = query.filter(
            School.district.in_([d.strip() for d in district if d and d.strip()])
        )
    if school_board:
        try:
            boards = [
                SchoolBoard(v.strip().lower()) for v in school_board if v and v.strip()
            ]
            if boards:
                query = query.filter(School.school_board.in_(boards))
        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid school_board. Use: cbse, icse, stateboard, ib, other. {e}",
            )
    if school_medium:
        try:
            mediums = [
                SchoolMedium(v.strip().lower())
                for v in school_medium
                if v and v.strip()
            ]
            if mediums:
                query = query.filter(School.school_medium.in_(mediums))
        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid school_medium. Use: english, hindi, bilingual, other. {e}",
            )
    if due_installment_type:
        conds = [
            cast(School.due_installment_type, String).ilike(f"%{v.strip()}%")
            for v in due_installment_type
            if v and v.strip()
        ]
        if conds:
            query = query.filter(or_(*conds))
    if teaching_method:
        conds = [
            cast(School.teaching_method, String).ilike(f"%{v.strip()}%")
            for v in teaching_method
            if v and v.strip()
        ]
        if conds:
            query = query.filter(or_(*conds))
    if transportation_facility is not None:
        query = query.filter(School.transportation_facility == transportation_facility)
    if from_date:
        try:
            from_dt = datetime.strptime(from_date, "%Y-%m-%d")
            query = query.filter(School.created_at >= from_dt)
        except ValueError:
            raise HTTPException(
                status_code=400, detail="Invalid from_date format. Use YYYY-MM-DD"
            )
    if to_date:
        try:
            to_dt = datetime.strptime(to_date, "%Y-%m-%d")
            to_dt = to_dt.replace(hour=23, minute=59, second=59)
            query = query.filter(School.created_at <= to_dt)
        except ValueError:
            raise HTTPException(
                status_code=400, detail="Invalid to_date format. Use YYYY-MM-DD"
            )
    total_count = query.count()
    schools = (
        query.order_by(School.created_at.desc())
        .offset(pagination.offset())
        .limit(pagination.limit())
        .all()
    )
    school_ids = [s.id for s in schools]
    rating_by_school = {}
    if school_ids:
        rating_stats = (
            db.query(
                SchoolRating.school_id,
                func.count(SchoolRating.id).label("rating_count"),
                func.avg(SchoolRating.rating).label("average_rating"),
            )
            .filter(SchoolRating.school_id.in_(school_ids))
            .group_by(SchoolRating.school_id)
        )
        rating_by_school = {
            row.school_id: {
                "rating_count": row.rating_count,
                "average_rating": float(round(row.average_rating, 2))
                if row.average_rating is not None
                else None,
            }
            for row in rating_stats
        }
    items = [
        {
            "id": s.id,
            "user_id": s.user_id,
            "school_name": s.school_name,
            "school_type": s.school_type.value
            if hasattr(s.school_type, "value")
            else (s.school_type if s.school_type else None),
            "school_medium": s.school_medium.value
            if hasattr(s.school_medium, "value")
            else (s.school_medium if s.school_medium else None),
            "school_board": s.school_board.value
            if hasattr(s.school_board, "value")
            else (s.school_board if s.school_board else None),
            "school_logo": s.profile_pic_url,
            "school_banner": s.banner_pic_url,
            "establishment_year": s.establishment_year,
            "pin_code": s.pin_code,
            "block_division": s.block_division,
            "district": s.district,
            "state": s.state,
            "country": s.country,
            "school_email": s.school_email,
            "school_phone": s.school_phone,
            "school_alt_phone": s.school_alt_phone,
            "school_website": s.school_website,
            "principal_name": s.principal_name,
            "principal_designation": s.principal_designation,
            "principal_email": s.principal_email,
            "principal_phone": s.principal_phone,
            "account_type": s.account_type.value
            if hasattr(s.account_type, "value")
            else str(s.account_type),
            "is_business_approved": s.is_business_approved,
            "is_promotion_pending": s.is_promotion_pending,
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "school_other_email": s.school_other_email,
            "school_location": s.school_location,
            "total_teachers": s.total_teachers if s.total_teachers is not None else 0,
            "total_students": s.total_students if s.total_students is not None else 0,
            "class_from": s.class_from,
            "class_to": s.class_to,
            "due_installment_type": s.due_installment_type,
            "transportation_facility": s.transportation_facility
            if s.transportation_facility is not None
            else False,
            "playground_facility": s.playground_facility
            if s.playground_facility is not None
            else False,
            "teaching_method": s.teaching_method,
            "rating_count": rating_by_school.get(s.id, {}).get("rating_count", 0),
            "average_rating": rating_by_school.get(s.id, {}).get("average_rating"),
        }
        for s in schools
    ]
    return pagination.format_response(items, total_count)


@router.post(
    "/schools/rating/",
    response_model=SchoolRatingResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_school_rating(
    data: SchoolRatingCreate,
    db: Session = Depends(get_db),
):
    """
    Submit a rating and feedback for a listed school. Any user can submit (no authentication required).
    Pass: school_id, user_name, user_role (visitor | student | parent), mobile, email_id, feedback, rating (1-5).
    One rating per combination of school_id + mobile + email_id (duplicate not allowed).
    """
    school = db.query(School).filter(School.id == data.school_id).first()
    if not school:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="School not found.",
        )
    email_normalized = data.email_id.strip().lower()
    existing = (
        db.query(SchoolRating)
        .filter(
            SchoolRating.school_id == data.school_id,
            SchoolRating.mobile == data.mobile.strip(),
            func.lower(SchoolRating.email_id) == email_normalized,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You have already submitted a rating for this school with this mobile and email.",
        )
    rating = SchoolRating(
        school_id=data.school_id,
        user_name=data.user_name,
        user_role=data.user_role,
        mobile=data.mobile.strip(),
        email_id=email_normalized,
        feedback=data.feedback,
        rating=data.rating,
    )
    db.add(rating)
    try:
        db.commit()
        db.refresh(rating)
    except SQLAlchemyError as e:
        db.rollback()
        if (
            "uq_school_rating_school_mobile_email" in str(e).lower()
            or "unique" in str(e).lower()
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="You have already submitted a rating for this school with this mobile and email.",
            )
        raise
    return rating


@router.get("/schools/{school_id}/ratings/")
def list_school_ratings(
    school_id: str,
    pagination: PaginationParams = Depends(),
    db: Session = Depends(get_db),
):
    """
    List all ratings for a school with user details and feedback. Paginated.
    Pass school_id in the path. Query params: page (default 1), per_page (default 10, max 100).
    """
    school = db.query(School).filter(School.id == school_id).first()
    if not school:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="School not found.",
        )
    query = db.query(SchoolRating).filter(SchoolRating.school_id == school_id)
    total_count = query.count()
    ratings = (
        query.order_by(SchoolRating.created_at.desc())
        .offset(pagination.offset())
        .limit(pagination.limit())
        .all()
    )
    items = [
        {
            "id": r.id,
            "school_id": r.school_id,
            "user_name": r.user_name,
            "user_role": r.user_role,
            "mobile": r.mobile,
            "email_id": r.email_id,
            "feedback": r.feedback,
            "rating": r.rating,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in ratings
    ]
    return pagination.format_response(items, total_count)


@router.delete(
    "/schools/{school_id}/ratings/{rating_id}/", status_code=status.HTTP_204_NO_CONTENT
)
def delete_school_rating(
    school_id: str,
    rating_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Delete a rating. Admin can delete any rating; school can delete only ratings for their own school.
    """
    rating = (
        db.query(SchoolRating)
        .filter(SchoolRating.id == rating_id, SchoolRating.school_id == school_id)
        .first()
    )
    if not rating:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rating not found.",
        )
    if current_user.role == UserRole.ADMIN:
        pass
    elif current_user.role == UserRole.SCHOOL:
        school = db.query(School).filter(School.user_id == current_user.id).first()
        if not school or school.id != school_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only delete ratings for your own school.",
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin or school can delete ratings.",
        )
    db.delete(rating)
    db.commit()
    return None


@router.get("/schools/pending-approvals/")
def get_pending_approvals(
    pagination: PaginationParams = Depends(),
    request_type: Optional[str] = Query(
        None,
        description="Filter by request type: 'business_signup' or 'promotion'. Leave empty for all.",
    ),
    school_name: Optional[str] = Query(
        None, description="Filter by school name (case-insensitive search)"
    ),
    school_email: Optional[str] = Query(None, description="Filter by school email"),
    account_type: Optional[str] = Query(
        None, description="Filter by account type: 'business' or 'listing'"
    ),
    from_date: Optional[str] = Query(
        None, description="Filter by created date from (YYYY-MM-DD)"
    ),
    to_date: Optional[str] = Query(
        None, description="Filter by created date to (YYYY-MM-DD)"
    ),
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(UserRole.ADMIN)),
):
    """
    Get all pending school approvals (business signups and promotions).
    Combines both pending business signups and pending promotions in one endpoint.

    Filters:
    - request_type: 'business_signup' (new business accounts) or 'promotion' (listing to business upgrade)
    - school_name: Search by school name
    - school_email: Filter by school email
    - account_type: Filter by current account type
    - from_date/to_date: Filter by creation date range
    """
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin account is allowed to view pending approvals.",
        )

    try:
        # Build base query
        query = db.query(School)

        # Apply filters based on request_type
        if request_type == "business_signup":
            # Business signups: account_type == BUSINESS AND is_business_approved == False
            query = query.filter(
                School.account_type == SchoolAccountType.BUSINESS,
                School.is_business_approved == False,
            )
        elif request_type == "promotion":
            # Promotions: account_type == LISTING AND is_promotion_pending == True
            query = query.filter(
                School.account_type == SchoolAccountType.LISTING,
                School.is_promotion_pending == True,
            )
        else:
            # All pending: either business signups OR promotions
            query = query.filter(
                or_(
                    and_(
                        School.account_type == SchoolAccountType.BUSINESS,
                        School.is_business_approved == False,
                    ),
                    and_(
                        School.account_type == SchoolAccountType.LISTING,
                        School.is_promotion_pending == True,
                    ),
                )
            )

        # Apply additional filters
        if school_name:
            query = query.filter(School.school_name.ilike(f"%{school_name}%"))

        if school_email:
            query = query.filter(School.school_email.ilike(f"%{school_email}%"))

        if account_type:
            if account_type.lower() == "business":
                query = query.filter(School.account_type == SchoolAccountType.BUSINESS)
            elif account_type.lower() == "listing":
                query = query.filter(School.account_type == SchoolAccountType.LISTING)

        if from_date:
            try:
                from_datetime = datetime.strptime(from_date, "%Y-%m-%d")
                query = query.filter(School.created_at >= from_datetime)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid from_date format. Use YYYY-MM-DD",
                )

        if to_date:
            try:
                to_datetime = datetime.strptime(to_date, "%Y-%m-%d")
                # Add 23:59:59 to include the entire day
                to_datetime = to_datetime.replace(hour=23, minute=59, second=59)
                query = query.filter(School.created_at <= to_datetime)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid to_date format. Use YYYY-MM-DD",
                )

        # Get total count before pagination
        total = query.count()

        # Apply pagination and ordering
        schools = (
            query.order_by(School.created_at.desc())
            .offset(pagination.offset())
            .limit(pagination.limit())
            .all()
        )

        # Build result
        result = []
        for school in schools:
            user = db.query(User).filter(User.id == school.user_id).first()

            # Determine request type
            if (
                school.account_type == SchoolAccountType.BUSINESS
                and not school.is_business_approved
            ):
                request_type_value = "business_signup"
            elif (
                school.account_type == SchoolAccountType.LISTING
                and school.is_promotion_pending
            ):
                request_type_value = "promotion"
            else:
                request_type_value = "unknown"

            result.append(
                {
                    "school_id": school.id,
                    "school_name": school.school_name,
                    "school_email": school.school_email,
                    "school_phone": school.school_phone,
                    "school_website": school.school_website,
                    "account_type": school.account_type.value,
                    "request_type": request_type_value,  # "business_signup" or "promotion"
                    "is_business_approved": school.is_business_approved,
                    "is_promotion_pending": school.is_promotion_pending,
                    "created_at": school.created_at,
                    "user_id": user.id if user else None,
                    "user_name": user.name if user else None,
                    "user_email": user.email if user else None,
                }
            )

        return pagination.format_response(result, total)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching pending approvals: {str(e)}",
        )


@router.get("/schools/pending-business-signups/")
def get_pending_business_signups(
    pagination: PaginationParams = Depends(),
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(UserRole.ADMIN)),
):
    """
    DEPRECATED: Use /schools/pending-approvals/?request_type=business_signup instead
    Get all schools with business signup waiting for approval.
    """
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin account is allowed to view pending business signups.",
        )

    try:
        schools = (
            db.query(School)
            .filter(
                School.account_type == SchoolAccountType.BUSINESS,
                School.is_business_approved == False,
            )
            .order_by(School.created_at.desc())
            .offset(pagination.offset())
            .limit(pagination.limit())
            .all()
        )

        total = (
            db.query(func.count(School.id))
            .filter(
                School.account_type == SchoolAccountType.BUSINESS,
                School.is_business_approved == False,
            )
            .scalar()
        )

        result = []
        for school in schools:
            user = db.query(User).filter(User.id == school.user_id).first()
            result.append(
                {
                    "school_id": school.id,
                    "school_name": school.school_name,
                    "school_email": school.school_email,
                    "school_phone": school.school_phone,
                    "school_website": school.school_website,
                    "account_type": school.account_type.value,
                    "created_at": school.created_at,
                    "user_name": user.name if user else None,
                    "user_email": user.email if user else None,
                }
            )

        return pagination.format_response(result, total)

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching pending business signups: {str(e)}",
        )


@router.put("/schools/{school_id}/approve-business/")
def approve_business_signup(
    school_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(UserRole.ADMIN)),
):
    """
    Approve business school signup. Allows school to login.
    """
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin account is allowed to approve business signups.",
        )

    try:
        school = db.query(School).filter(School.id == school_id).first()
        if not school:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="School not found."
            )

        if school.account_type != SchoolAccountType.BUSINESS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This school is not a business signup.",
            )

        if school.is_business_approved:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="School is already approved.",
            )

        school.is_business_approved = True
        school.is_verified = True  # Also set general verification

        # Create credit master if doesn't exist
        existing_credit = (
            db.query(CreditMaster).filter(CreditMaster.school_id == school.id).first()
        )
        if not existing_credit:
            credit_master = CreditMaster(school_id=school.id, earned_credit=100)
            db.add(credit_master)

        db.commit()

        # TODO: Notify school via email

        return {
            "detail": "Business school approved successfully. School can now login."
        }

    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error occurred: {str(e)}",
        )


@router.put("/schools/{school_id}/approve/")
def approve_school_request(
    school_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(UserRole.ADMIN)),
):
    """
    Unified approval endpoint for both business signups and promotions.
    Automatically detects the request type and approves accordingly.

    - For business signups: Sets is_business_approved = True
    - For promotions: Upgrades account_type to BUSINESS and sets is_business_approved = True
    """
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin account is allowed to approve school requests.",
        )

    try:
        school = db.query(School).filter(School.id == school_id).first()
        if not school:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="School not found."
            )

        # Determine request type and approve accordingly
        if (
            school.account_type == SchoolAccountType.BUSINESS
            and not school.is_business_approved
        ):
            # Business signup approval
            school.is_business_approved = True
            school.is_verified = True
            request_type = "business_signup"
            message = "Business school approved successfully. School can now login."

        elif (
            school.account_type == SchoolAccountType.LISTING
            and school.is_promotion_pending
        ):
            # Promotion approval - upgrade to business
            school.account_type = SchoolAccountType.BUSINESS
            school.is_business_approved = True
            school.is_promotion_pending = False
            school.is_verified = True
            request_type = "promotion"
            message = "Promotion approved. Account upgraded to business (has both listing and business access)."

        else:
            # No pending request found
            if school.is_business_approved:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="School is already approved.",
                )
            elif school.account_type == SchoolAccountType.BUSINESS:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="This school is already a business account and approved.",
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No pending approval request found for this school.",
                )

        # Create credit master if doesn't exist
        existing_credit = (
            db.query(CreditMaster).filter(CreditMaster.school_id == school.id).first()
        )
        if not existing_credit:
            credit_master = CreditMaster(school_id=school.id, earned_credit=100)
            db.add(credit_master)

        db.commit()

        # TODO: Notify school via email

        return {
            "detail": message,
            "request_type": request_type,
            "school_id": school.id,
            "school_name": school.school_name,
            "account_type": school.account_type.value,
            "is_business_approved": school.is_business_approved,
        }

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error occurred: {str(e)}",
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error approving school request: {str(e)}",
        )


@router.get("/schools/pending-promotions/")
def get_pending_promotions(
    pagination: PaginationParams = Depends(),
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(UserRole.ADMIN)),
):
    """
    Get all listing schools requesting promotion to business.
    """
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin account is allowed to view pending promotions.",
        )

    try:
        schools = (
            db.query(School)
            .filter(
                School.account_type == SchoolAccountType.LISTING,
                School.is_promotion_pending == True,
            )
            .order_by(School.created_at.desc())
            .offset(pagination.offset())
            .limit(pagination.limit())
            .all()
        )

        total = (
            db.query(func.count(School.id))
            .filter(
                School.account_type == SchoolAccountType.LISTING,
                School.is_promotion_pending == True,
            )
            .scalar()
        )

        result = []
        for school in schools:
            user = db.query(User).filter(User.id == school.user_id).first()
            result.append(
                {
                    "school_id": school.id,
                    "school_name": school.school_name,
                    "school_email": school.school_email,
                    "school_phone": school.school_phone,
                    "school_website": school.school_website,
                    "account_type": school.account_type.value,
                    "created_at": school.created_at,
                    "user_name": user.name if user else None,
                    "user_email": user.email if user else None,
                }
            )

        return pagination.format_response(result, total)

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching pending promotions: {str(e)}",
        )


@router.put("/schools/{school_id}/approve-promotion/")
def approve_promotion(
    school_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(UserRole.ADMIN)),
):
    """
    Approve promotion request. Changes account_type to BUSINESS (which has both listing + business permissions).
    """
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin account is allowed to approve promotions.",
        )

    try:
        school = db.query(School).filter(School.id == school_id).first()
        if not school:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="School not found."
            )

        if school.account_type != SchoolAccountType.LISTING:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This school is not a listing account.",
            )

        if not school.is_promotion_pending:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No promotion request pending for this school.",
            )

        # Upgrade to BUSINESS account type (business = both listing + business permissions)
        school.account_type = SchoolAccountType.BUSINESS
        school.is_business_approved = True
        school.is_promotion_pending = False
        school.is_verified = True

        # Create credit master if doesn't exist
        existing_credit = (
            db.query(CreditMaster).filter(CreditMaster.school_id == school.id).first()
        )
        if not existing_credit:
            credit_master = CreditMaster(school_id=school.id, earned_credit=100)
            db.add(credit_master)

        db.commit()

        # TODO: Notify school via email

        return {
            "detail": "Promotion approved. Account upgraded to business (has both listing and business access)."
        }

    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error occurred: {str(e)}",
        )


@router.get("/school/{school_id}/")
def get_school_details(
    school_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(UserRole.ADMIN)),
):
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin account is allowed to view school details.",
        )

    try:
        school = db.query(School).filter(School.id == school_id).first()
        if not school:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="School not found."
            )
        # Get user location from User table using user_id from school
        user = db.query(User).filter(User.id == school.user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Associated user not found.",
            )
        credits = (
            db.query(CreditMaster).filter(CreditMaster.school_id == school.id).first()
        )
        if not school.is_verified:
            available_credit = 0
            earned_credit = 0
        else:
            # If school is verified, use credits from DB or 0 if no record exists
            available_credit = credits.available_credit if credits else 0
            earned_credit = credits.used_credit if credits else 0
        teacher_count = (
            db.query(func.count())
            .select_from(Teacher)
            .filter(Teacher.school_id == school.id)
            .scalar()
        )
        student_count = (
            db.query(func.count())
            .select_from(Student)
            .filter(Student.school_id == school.id)
            .scalar()
        )
        rating_stats = (
            db.query(
                func.count(SchoolRating.id).label("rating_count"),
                func.avg(SchoolRating.rating).label("average_rating"),
            )
            .filter(SchoolRating.school_id == school.id)
            .first()
        )
        rating_count = int(rating_stats.rating_count or 0)
        average_rating = (
            float(rating_stats.average_rating)
            if rating_stats and rating_stats.average_rating is not None
            else None
        )

        return {
            "school_id": school.id,
            "school_name": school.school_name,
            "school_phone": school.school_phone,
            "school_email": school.school_email,
            "school_website": school.school_website,
            "school_board": school.school_board,
            "affilation": school.school_medium,
            "profile_image": school.profile_pic_url,
            "banner_image": school.banner_pic_url,
            "location": user.location,
            "pin_code": school.pin_code,
            "block": school.block_division,
            "district": school.district,
            "state": school.state,
            "country": school.country,
            "no_of_teachers": teacher_count,
            "no_of_students": student_count,
            "created_at": school.created_at,
            "is_active": school.is_active,
            "is_verified": school.is_verified,
            "principal_name": school.principal_name,
            "principal_designation": school.principal_designation,
            "principal_phone": school.principal_phone,
            "principal_email": school.principal_email,
            "teacher_count": teacher_count,
            "student_count": student_count,
            "rating_count": rating_count,
            "average_rating": average_rating,
            "available_credit": available_credit,
            "earned_credit": earned_credit,
        }

    except SQLAlchemyError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error occurred: {str(e)}",
        )


@router.get("/all-students/")
def get_all_students(
    student_id: int = None,
    student_name: str = None,
    school_name: str = None,
    status: str = None,
    pagination: PaginationParams = Depends(),
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(UserRole.ADMIN)),
):

    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=403,
            detail="Only admin account is allowed to view all students.",
        )

    # Base query — NO SCHOOL FILTER
    query = (
        db.query(Student)
        .options(joinedload(Student.school))
        .options(joinedload(Student.classes))
    )

    # Apply filters
    if student_id:
        query = query.filter(Student.id == student_id)

    if student_name:
        query = query.filter(
            (Student.first_name.ilike(f"%{student_name}%"))
            | (Student.last_name.ilike(f"%{student_name}%"))
        )

    if school_name:
        query = query.join(Student.school).filter(
            School.school_name.ilike(f"%{school_name}%")
        )

    if status:
        query = query.filter(Student.status == status)

    # Total count BEFORE pagination
    total_count = query.count()

    # Apply pagination
    students = query.offset(pagination.offset()).limit(pagination.limit()).all()

    # Format student data
    items = []
    for student in students:
        items.append(
            {
                "student_id": student.id,
                "name": f"{student.first_name} {student.last_name}",
                "class_name": student.classes.name if student.classes else "N/A",
                "school_name": student.school.school_name if student.school else "N/A",
                "status": student.status.value,
                "created_at": student.created_at,
            }
        )

    # Return paginated response
    return pagination.format_response(items, total_count)


@router.get("/student/{student_id}/")
def get_student_details(
    student_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(UserRole.ADMIN)),
):
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin account is allowed to view student details.",
        )

    try:
        student = db.query(Student).filter(Student.id == student_id).first()
        if not student:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Student not found."
            )

        user = db.query(User).filter(User.id == student.user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Associated user not found.",
            )
        last_exam = (
            db.query(StudentExamData)
            .filter(StudentExamData.student_id == student.id)
            .order_by(StudentExamData.submitted_at.desc())
            .first()
        )

        return {
            "student_id": student.id,
            "name": f"{student.first_name} {student.last_name}",
            "profile_image": student.profile_image,
            "class_name": student.classes.name if student.classes else "N/A",
            "school_name": student.school.school_name if student.school else "N/A",
            # "location": student.school.location if student.school else "N/A",
            "block_division": student.school.block_division
            if student.school
            else "N/A",
            "district": student.school.district if student.school else "N/A",
            "state": student.school.state if student.school else "N/A",
            "location": user.location,
            "last_appeared_exam": last_exam.submitted_at if last_exam else None,
            "exam_type": last_exam.exam.exam_type
            if last_exam and last_exam.exam
            else None,
            "exam_result": last_exam.result if last_exam else None,
            "status": student.status,
            # "email": student.email,
            # "is_active": student.is_active,
            "created_at": student.created_at,
        }

    except SQLAlchemyError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error occurred: {str(e)}",
        )


@router.get("/all-teachers/")
def get_all_teachers(
    teacher_id: str = None,
    teacher_name: str = None,
    school_name: str = None,
    status: str = None,  # active / inactive or whatever your enum is
    pagination: PaginationParams = Depends(),
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(UserRole.ADMIN)),
):

    # Only admin can access
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=403,
            detail="Only admin account is allowed to view all teachers.",
        )

    # Base query (NO SCHOOL LIMIT)
    query = db.query(Teacher).options(joinedload(Teacher.school))

    # Apply filters
    if teacher_id:
        query = query.filter(Teacher.id == teacher_id)

    if teacher_name:
        query = query.filter(
            (Teacher.first_name.ilike(f"%{teacher_name}%"))
            | (Teacher.last_name.ilike(f"%{teacher_name}%"))
        )

    if school_name:
        query = query.join(Teacher.school).filter(
            School.school_name.ilike(f"%{school_name}%")
        )

    if status:
        query = query.filter(Teacher.status == status)

    # Total before pagination
    total_count = query.count()

    # Apply pagination
    teachers = query.offset(pagination.offset()).limit(pagination.limit()).all()

    # Build response data
    items = []
    for teacher in teachers:
        items.append(
            {
                "teacher_id": teacher.id,
                "name": f"{teacher.first_name} {teacher.last_name}",
                "phone": teacher.phone,
                "email": teacher.email,
                "school_name": teacher.school.school_name if teacher.school else "N/A",
                "status": teacher.status.value if hasattr(teacher, "status") else None,
                "created_at": teacher.created_at,
            }
        )

    # Return paginated response
    return pagination.format_response(items, total_count)


@router.get("/teacher/{teacher_id}/")
def get_teacher_details(
    teacher_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(UserRole.ADMIN)),
):
    # 🔐 Extra safety (even though require_roles already enforces this)
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Only admin can access this.")

    teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher not found.")

    user = db.query(User).filter(User.id == teacher.user_id).first()
    school = db.query(School).filter(School.id == teacher.school_id).first()

    # =========================
    # Assignments
    # =========================
    assignments = (
        db.query(TeacherClassSectionSubject)
        .filter(TeacherClassSectionSubject.teacher_id == teacher.id)
        .all()
    )

    detailed_assignments = [
        {
            "class_id": a.class_id,
            "class_name": a.class_.name if a.class_ else None,
            "section_id": a.section_id,
            "section_name": a.section.name if a.section else None,
            "subject_id": a.subject_id,
            "subject_name": a.subject.name if a.subject else None,
        }
        for a in assignments
    ]

    # =========================
    # Exams conducted by teacher
    # =========================
    exams = (
        db.query(Exam)
        .filter(Exam.created_by == teacher.id)
        .order_by(Exam.created_at.desc())
        .all()
    )

    exam_count = len(exams)
    last_exam = exams[0] if exams else None

    last_exam_data = {
        "last_exam_date_time": last_exam.created_at if last_exam else None,
        "last_exam_type": last_exam.exam_type.value if last_exam else None,
        "last_exam_status": last_exam.status.value if last_exam else None,
        "last_exam_total_mark": (last_exam.no_of_questions if last_exam else 0),
    }

    # =========================
    # Leave summary
    # =========================
    leaves = db.query(LeaveRequest).filter(LeaveRequest.teacher_id == teacher.id).all()

    sick_total = sum(1 for l in leaves if l.leave_type == LeaveType.EMERGENCY)
    sick_used = sum(
        1
        for l in leaves
        if l.leave_type == LeaveType.EMERGENCY and l.status == LeaveStatus.APPROVED
    )

    casual_total = sum(1 for l in leaves if l.leave_type == LeaveType.CASUAL)
    casual_used = sum(
        1
        for l in leaves
        if l.leave_type == LeaveType.CASUAL and l.status == LeaveStatus.APPROVED
    )

    leave_summary = {
        "sick": {"total": sick_total, "used": sick_used},
        "casual": {"total": casual_total, "used": casual_used},
    }

    # =========================
    # Salary (reference payment table)
    # =========================
    payment = (
        db.query(TeacherStaffPayment)
        .filter(TeacherStaffPayment.teacher_id == teacher.id)
        .first()
    )

    salary_per_month = payment.monthly_in_hand_salary if payment else 0.0

    # =========================
    # Final response
    # =========================
    return {
        "teacher_id": teacher.id,
        "profile_image": teacher.profile_image,
        "name": f"{teacher.first_name} {teacher.last_name}",
        "email": teacher.email,
        "phone": teacher.phone,
        "school_name": school.school_name if school else None,
        "location": user.location if user else None,
        # 🔥 New fields
        "exam_conduct_count": exam_count,
        "exam_details": last_exam_data,
        "active_since": teacher.created_at,
        "leave_summary": leave_summary,
        "salary_per_month": salary_per_month,
        # Existing
        "assignments": detailed_assignments,
        "created_at": teacher.created_at,
        "status": "active" if teacher.is_active else "inactive",
    }


@router.get("/class_subjects/")
def get_class_subjects(
    class_name: str | None = None,
    school_board: str | None = None,
    school_medium: str | None = None,
    pagination: PaginationParams = Depends(),
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(UserRole.ADMIN, UserRole.SELF_SIGNED_STUDENT)),
):
    try:
        query = db.query(
            func.min(SchoolClassSubject.id).label("class_id"),
            SchoolClassSubject.school_board,
            SchoolClassSubject.school_medium,
            SchoolClassSubject.class_name,
            func.array_agg(
                func.json_build_object(
                    "subject_id",
                    SchoolClassSubject.id,
                    "subject_name",
                    SchoolClassSubject.subject,
                )
            ).label("subjects"),
            func.min(SchoolClassSubject.created_at).label("created_at"),
        ).group_by(
            SchoolClassSubject.school_board,
            SchoolClassSubject.school_medium,
            SchoolClassSubject.class_name,
        )

        # 🔍 Filters
        if class_name:
            query = query.filter(SchoolClassSubject.class_name.ilike(f"%{class_name}%"))

        if school_board:
            query = query.filter(
                cast(SchoolClassSubject.school_board, String).ilike(f"%{school_board}%")
            )
        if school_medium:
            query = query.filter(
                cast(SchoolClassSubject.school_medium, String).ilike(
                    f"%{school_medium}%"
                )
            )

        # 🔢 Count before pagination
        total_count = query.count()

        # 📄 Pagination
        records = query.offset(pagination.offset()).limit(pagination.limit()).all()

        result = []
        for row in records:
            result.append(
                {
                    "class_id": row.class_id,
                    "school_board": row.school_board,
                    "school_medium": row.school_medium,
                    "class_name": row.class_name,
                    "subjects": row.subjects,
                    "created_at": row.created_at,
                }
            )

        return pagination.format_response(result, total_count)

    except SQLAlchemyError as e:
        raise HTTPException(
            status_code=500, detail=f"Database error occurred: {str(e)}"
        )


@router.post("/class_subjects/")
def create_class_subjects(
    payload: SchoolClassSubjectBase,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(UserRole.ADMIN)),
):
    # Access control
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin account is allowed to create class subjects.",
        )

    try:
        # 🔍 Check duplicate (class_name + subject + board + medium combo)
        existing = (
            db.query(SchoolClassSubject)
            .filter(
                SchoolClassSubject.class_name == payload.class_name,
                SchoolClassSubject.subject == payload.subject,
                SchoolClassSubject.school_board == payload.school_board,
                SchoolClassSubject.school_medium == payload.school_medium,
            )
            .first()
        )

        if existing:
            raise HTTPException(
                status_code=400,
                detail="This subject already exists for the selected class, board and medium.",
            )

        # Create record
        new_record = SchoolClassSubject(
            school_board=payload.school_board,
            school_medium=payload.school_medium,
            class_name=payload.class_name,
            subject=payload.subject,
        )

        db.add(new_record)
        db.commit()
        db.refresh(new_record)

        return {
            "detail": "Class subject created successfully.",
            "class_subject_id": new_record.id,
        }

    except SQLAlchemyError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error occurred: {str(e)}",
        )


@router.put("/class_subjects/{class_subject_id}")
def update_class_subject(
    class_subject_id: int,
    payload: SchoolClassSubjectUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(UserRole.ADMIN)),
):
    # 🔐 Access control
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin account is allowed to update class subjects.",
        )

    record = (
        db.query(SchoolClassSubject)
        .filter(SchoolClassSubject.id == class_subject_id)
        .first()
    )

    if not record:
        raise HTTPException(status_code=404, detail="Class subject not found.")

    # Use existing values if field not provided
    new_board = payload.school_board or record.school_board
    new_medium = payload.school_medium or record.school_medium
    new_class_name = payload.class_name or record.class_name
    new_subject = payload.subject or record.subject

    # 🔍 Duplicate check
    duplicate = (
        db.query(SchoolClassSubject)
        .filter(
            SchoolClassSubject.id != class_subject_id,
            SchoolClassSubject.school_board == new_board,
            SchoolClassSubject.school_medium == new_medium,
            SchoolClassSubject.class_name == new_class_name,
            SchoolClassSubject.subject == new_subject,
        )
        .first()
    )

    if duplicate:
        raise HTTPException(
            status_code=400,
            detail="Another record already exists with the same class, subject, board, and medium.",
        )

    # ✏️ Update fields
    record.school_board = new_board
    record.school_medium = new_medium
    record.class_name = new_class_name
    record.subject = new_subject

    db.commit()
    db.refresh(record)

    return {
        "detail": "Class subject updated successfully.",
        "class_subject_id": record.id,
    }


@router.get("/classes/")
def get_all_classes(
    school_board: Optional[SchoolBoard] = None,
    school_medium: Optional[SchoolMedium] = None,
    pagination: PaginationParams = Depends(),
    db: Session = Depends(get_db),
    current_user=Depends(
        require_roles(
            UserRole.ADMIN,
            UserRole.SCHOOL,
            UserRole.TEACHER,
            UserRole.STUDENT,
            UserRole.SELF_SIGNED_STUDENT,
        )
    ),
):
    """Fetch all unique classes with class_id & class_name filtered by board & medium."""

    try:
        query = db.query(
            func.min(SchoolClassSubject.id).label("class_id"),
            SchoolClassSubject.class_name,
        ).group_by(SchoolClassSubject.class_name)

        # 🔍 Filters
        if school_board:
            query = query.filter(SchoolClassSubject.school_board == school_board)

        if school_medium:
            query = query.filter(SchoolClassSubject.school_medium == school_medium)

        total_count = query.count()

        results = (
            query.order_by(SchoolClassSubject.class_name.asc())
            .offset(pagination.offset())
            .limit(pagination.limit())
            .all()
        )

        # ✅ Proper response format
        class_list = [
            {"id": row.class_id, "class_name": row.class_name} for row in results
        ]

        return pagination.format_response(class_list, total_count)

    except SQLAlchemyError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error occurred: {str(e)}",
        )


@router.get("/subjects/")
def get_subjects_for_class(
    board: Optional[str] = None,
    medium: Optional[str] = None,
    class_name: Optional[str] = None,
    pagination: PaginationParams = Depends(),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if current_user.role == UserRole.SELF_SIGNED_STUDENT:
        student = (
            db.query(SelfSignedStudent)
            .filter(SelfSignedStudent.user_id == current_user.id)
            .first()
        )

        if not student:
            raise HTTPException(status_code=404, detail="Student not found")

        board = student.select_board
        medium = student.select_medium
        class_name = student.select_class

        if not all([board, medium, class_name]):
            raise HTTPException(status_code=400, detail="Student profile incomplete")

    elif current_user.role in [UserRole.TEACHER, UserRole.SCHOOL]:
        if not all([board, medium, class_name]):
            raise HTTPException(status_code=400, detail="Filters required")

    elif current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Unauthorized")

    try:
        query = db.query(
            SchoolClassSubject.id.label("id"),
            SchoolClassSubject.subject.label("subject"),
            func.count(Chapter.id).label("chapter_count"),
        ).outerjoin(Chapter, Chapter.school_class_subject_id == SchoolClassSubject.id)

        if board:
            query = query.filter(SchoolClassSubject.school_board == board)

        if medium:
            query = query.filter(SchoolClassSubject.school_medium == medium)

        if class_name:
            query = query.filter(SchoolClassSubject.class_name == class_name)

        query = query.group_by(SchoolClassSubject.id, SchoolClassSubject.subject)

        total_count = db.query(func.count()).select_from(query.subquery()).scalar()

        results = (
            query.order_by(SchoolClassSubject.subject.asc())
            .offset(pagination.offset())
            .limit(pagination.limit())
            .all()
        )

        return pagination.format_response(
            [
                {
                    "id": row.id,
                    "subject": row.subject,
                    "total_chapters": row.chapter_count,
                }
                for row in results
            ],
            total_count,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@router.get("/my-subjects/")
def get_my_subjects(
    pagination: PaginationParams = Depends(),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if current_user.role != UserRole.SELF_SIGNED_STUDENT:
        raise HTTPException(status_code=403, detail="Only self signed students allowed")

    student = (
        db.query(SelfSignedStudent)
        .filter(SelfSignedStudent.user_id == current_user.id)
        .first()
    )

    if not student:
        raise HTTPException(status_code=404, detail="Student profile not found")

    if not student.select_class_id:
        raise HTTPException(status_code=400, detail="Student class not selected")

    try:
        # ✅ Step 1: Get class details using selected id
        selected_class = (
            db.query(SchoolClassSubject)
            .filter(SchoolClassSubject.id == student.select_class_id)
            .first()
        )

        if not selected_class:
            raise HTTPException(status_code=404, detail="Selected class not found")

        # ✅ Step 2: Get all subjects of same board + medium + class
        query = (
            db.query(
                SchoolClassSubject.id.label("school_class_subject_id"),
                SchoolClassSubject.subject.label("subject"),
                func.count(Chapter.id).label("chapter_count"),
            )
            .outerjoin(
                Chapter, Chapter.school_class_subject_id == SchoolClassSubject.id
            )
            .filter(
                SchoolClassSubject.school_board == selected_class.school_board,
                SchoolClassSubject.school_medium == selected_class.school_medium,
                SchoolClassSubject.class_name == selected_class.class_name,
            )
            .group_by(SchoolClassSubject.id, SchoolClassSubject.subject)
        )

        total_count = db.query(func.count()).select_from(query.subquery()).scalar()

        results = (
            query.order_by(SchoolClassSubject.subject.asc())
            .offset(pagination.offset())
            .limit(pagination.limit())
            .all()
        )

        return pagination.format_response(
            [
                {
                    "school_class_subject_id": row.school_class_subject_id,
                    "subject": row.subject,
                    "total_chapters": row.chapter_count,
                }
                for row in results
            ],
            total_count,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@router.get("/subjects/{subject_id}/chapters/")
def get_chapters_by_subject(
    subject_id: int,
    limit: int = 10,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    View all chapters under a given subject with:
    - Video count
    - Task count (home assignments count)
    - Pagination
    """

    # Role check
    if current_user.role not in [
        UserRole.ADMIN,
        UserRole.SCHOOL,
        UserRole.TEACHER,
        UserRole.STUDENT,
        UserRole.SELF_SIGNED_STUDENT,
    ]:
        raise HTTPException(status_code=403, detail="Access denied")

    # Check subject exists
    subject = (
        db.query(SchoolClassSubject).filter(SchoolClassSubject.id == subject_id).first()
    )
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")

    # Main query: chapter + video count + task count
    chapters_query = (
        db.query(
            Chapter.id.label("chapter_id"),
            Chapter.title.label("chapter_title"),
            Chapter.created_at.label("created_at"),
            func.count(ChapterVideo.id).label("video_count"),
            func.count(HomeAssignment.id).label("task_count"),
        )
        .outerjoin(ChapterVideo, ChapterVideo.chapter_id == Chapter.id)
        .outerjoin(HomeAssignment, HomeAssignment.chapter_id == Chapter.id)
        .filter(Chapter.school_class_subject_id == subject_id)
        .group_by(Chapter.id)
        .order_by(Chapter.created_at.desc())
    )

    total_chapters = chapters_query.count()

    chapters = chapters_query.offset(offset).limit(limit).all()

    result = [
        {
            "chapter_id": c.chapter_id,
            "chapter_title": c.chapter_title,
            "number_of_videos": c.video_count,
            "number_of_tasks": c.task_count,
            "created_at": c.created_at,
        }
        for c in chapters
    ]

    return {
        "total": total_chapters,
        "limit": limit,
        "offset": offset,
        "chapters": result,
    }


@router.post("/class_subjects/{subject_id}/chapters/")
def add_chapter_to_subject(
    subject_id: int,
    chapter: ChapterCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(UserRole.ADMIN)),
):
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin account is allowed to add chapters.",
        )

    try:
        # Check if subject exists
        subject = (
            db.query(SchoolClassSubject)
            .filter(SchoolClassSubject.id == subject_id)
            .first()
        )
        if not subject:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Class subject not found."
            )

        # Create Chapter
        new_chapter = Chapter(
            title=chapter.title,
            description=chapter.description,
            school_class_subject_id=subject.id,
        )
        db.add(new_chapter)
        db.commit()
        db.refresh(new_chapter)

        # Add videos
        for v in chapter.videos:
            db.add(ChapterVideo(url=v.url, chapter_id=new_chapter.id))
        # Add images
        for i in chapter.images:
            db.add(ChapterImage(url=i.url, chapter_id=new_chapter.id))
        # Add PDFs
        for p in chapter.pdfs:
            db.add(ChapterPDF(url=p.url, chapter_id=new_chapter.id))
        # Add QnAs
        for q in chapter.qnas:
            db.add(
                ChapterQnA(
                    question=q.question, answer=q.answer, chapter_id=new_chapter.id
                )
            )
        for k in chapter.keypoints:
            db.add(ChapterKeyPoint(point=k.point, chapter_id=new_chapter.id))

        db.commit()

        return {
            "detail": f"Chapter '{new_chapter.title}' added successfully to subject '{subject.subject}'.",
            "chapter_id": new_chapter.id,
        }

    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error occurred: {str(e)}",
        )


@router.put("/chapters/{chapter_id}/")
def update_chapter(
    chapter_id: int,
    chapter_data: ChapterUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(UserRole.ADMIN)),
):
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin account is allowed to update chapters.",
        )

    try:
        chapter = db.query(Chapter).filter(Chapter.id == chapter_id).first()
        if not chapter:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Chapter not found."
            )

        # Update basic fields
        if chapter_data.title is not None:
            chapter.title = chapter_data.title
        if chapter_data.description is not None:
            chapter.description = chapter_data.description

        # Update videos
        if chapter_data.videos:
            chapter.videos.clear()  # remove existing
            for v in chapter_data.videos:
                chapter.videos.append(ChapterVideo(url=v.url))

        # Update images
        if chapter_data.images:
            chapter.images.clear()
            for i in chapter_data.images:
                chapter.images.append(ChapterImage(url=i.url))

        # Update PDFs
        if chapter_data.pdfs:
            chapter.pdfs.clear()
            for p in chapter_data.pdfs:
                chapter.pdfs.append(ChapterPDF(url=p.url))

        # Update QnAs
        if chapter_data.qnas:
            chapter.qnas.clear()
            for q in chapter_data.qnas:
                chapter.qnas.append(ChapterQnA(question=q.question, answer=q.answer))
        if chapter_data.keypoints:
            chapter.keypoints.clear()
            for k in chapter_data.keypoints:
                chapter.keypoints.append(ChapterKeyPoint(point=k.point))

        db.commit()
        db.refresh(chapter)

        return {
            "detail": f"Chapter '{chapter.title}' updated successfully.",
            "chapter_id": chapter.id,
        }

    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error occurred: {str(e)}",
        )


@router.get("/chapters/{chapter_id}/")
def get_chapter_details(
    chapter_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),  # allow all roles
):
    # ✅ Role check: only allow Admin, School, Teacher, Student
    if current_user.role not in [
        UserRole.ADMIN,
        UserRole.SCHOOL,
        UserRole.TEACHER,
        UserRole.STUDENT,
        UserRole.SELF_SIGNED_STUDENT,
    ]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to view this chapter.",
        )

    try:
        chapter = db.query(Chapter).filter(Chapter.id == chapter_id).first()
        if not chapter:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Chapter not found."
            )

        return {
            "chapter_id": chapter.id,
            "title": chapter.title,
            "description": chapter.description,
            "subject_id": chapter.school_class_subject_id,
            "videos": [{"id": v.id, "url": v.url} for v in chapter.videos],
            "images": [{"id": i.id, "url": i.url} for i in chapter.images],
            "pdfs": [{"id": p.id, "url": p.url} for p in chapter.pdfs],
            "qnas": [
                {"id": q.id, "question": q.question, "answer": q.answer}
                for q in chapter.qnas
            ],
            "keypoints": [{"id": k.id, "points": k.point} for k in chapter.keypoints],
            "created_at": chapter.created_at,
            "updated_at": chapter.updated_at,
        }

    except SQLAlchemyError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error occurred: {str(e)}",
        )


@router.get("/classes-with-subjects/")
def get_classes_with_subject_names(
    class_name: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(UserRole.SCHOOL, UserRole.STAFF)),
):
    # 🔹 Get school
    if current_user.role == UserRole.SCHOOL:
        school = db.query(School).filter(School.user_id == current_user.id).first()
        if not school:
            raise HTTPException(status_code=404, detail="School profile not found.")

    elif current_user.role == UserRole.STAFF:
        staff = db.query(Staff).filter(Staff.user_id == current_user.id).first()
        if not staff:
            raise HTTPException(status_code=404, detail="Staff profile not found.")

        school = db.query(School).filter(School.id == staff.school_id).first()
        if not school:
            raise HTTPException(
                status_code=404, detail="School not found for this staff member."
            )

    try:
        # ✅ Build query (DON'T call .all() yet)
        query = db.query(SchoolClassSubject).filter(
            SchoolClassSubject.school_board == school.school_board,
            SchoolClassSubject.school_medium == school.school_medium,
        )

        # ✅ Optional class filter
        if class_name:
            query = query.filter(SchoolClassSubject.class_name == class_name)

        # ✅ Execute query ONCE
        class_subjects = query.all()

        if not class_subjects:
            return {
                "school_name": school.school_name,
                "school_board": school.school_board,
                "school_medium": school.school_medium,
                "classes": [],
            }

        # 🔹 Group subjects by class
        classes_dict = defaultdict(list)
        for cs in class_subjects:
            classes_dict[cs.class_name].append(
                {"name": cs.subject, "school_class_subject_id": cs.id}
            )

        result = [
            {"class_name": cls, "subjects": subjects}
            for cls, subjects in classes_dict.items()
        ]

        return {
            "school_name": school.school_name,
            "school_board": school.school_board,
            "school_medium": school.school_medium,
            "classes": result,
        }

    except SQLAlchemyError as e:
        raise HTTPException(
            status_code=500, detail=f"Database error occurred: {str(e)}"
        )


@router.get("/available-credit/")
def get_available_credit(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.SCHOOL, UserRole.STAFF)),
):
    # ✅ Get school_id based on user role
    if current_user.role == UserRole.SCHOOL:
        school_id = current_user.school_profile.id
    elif current_user.role == UserRole.STAFF:
        staff = db.query(Staff).filter(Staff.user_id == current_user.id).first()
        if not staff:
            raise HTTPException(status_code=404, detail="Staff profile not found.")
        school_id = staff.school_id
    else:
        raise HTTPException(
            status_code=403, detail="Not authorized to access this resource."
        )

    # Fetch school credit
    credit = db.query(CreditMaster).filter(CreditMaster.school_id == school_id).first()
    if not credit:
        raise HTTPException(
            status_code=404, detail="Credit account not found for this school."
        )

    # Calculate available credit (just in case)
    credit.calculate_available_credit()

    return {
        "school_id": school_id,
        "available_credit": credit.available_credit,
        "self_added_credit": credit.self_added_credit or 0,
        "earned_credit": credit.earned_credit or 0,
        "used_credit": credit.used_credit or 0,
        "transfer_credit": credit.transfer_credit or 0,
        "last_updated": credit.updated_at,
    }


@router.post("/exams/")
def create_exam(
    payload: AdminExamCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(UserRole.ADMIN)),
):
    scs = (
        db.query(SchoolClassSubject)
        .filter(SchoolClassSubject.id == payload.school_class_subject_id)
        .first()
    )

    if not scs:
        raise HTTPException(
            status_code=404, detail="Invalid school_class_subject_id provided."
        )

    existing_exam = (
        db.query(AdminExam)
        .filter(
            AdminExam.name == payload.name,
            AdminExam.school_class_subject_id == payload.school_class_subject_id,
        )
        .first()
    )

    if existing_exam:
        raise HTTPException(
            status_code=400,
            detail="Exam with same name already exists for this class & subject.",
        )

    try:
        new_exam = AdminExam(
            name=payload.name,
            school_class_subject_id=payload.school_class_subject_id,
            exam_type=payload.exam_type,
            question_type=payload.question_type,
            passing_mark=payload.passing_mark,
            repeat=payload.repeat,
            duration=payload.duration,
            exam_validity=payload.exam_validity,
            description=payload.description,
        )

        db.add(new_exam)
        db.commit()
        db.refresh(new_exam)

        return {"detail": "Exam created successfully.", "exam_id": new_exam.id}

    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@router.get("/exams/")
def get_exams(
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(UserRole.ADMIN, UserRole.SELF_SIGNED_STUDENT)),
):
    exams_query = db.query(AdminExam).join(SchoolClassSubject)

    if current_user.role == UserRole.SELF_SIGNED_STUDENT:
        student = (
            db.query(SelfSignedStudent)
            .filter(SelfSignedStudent.user_id == current_user.id)
            .first()
        )

        if not student:
            raise HTTPException(404, "Student profile not found.")

        if not student.select_class_id:
            raise HTTPException(400, "Student has not selected a class yet.")

        exams_query = exams_query.filter(
            AdminExam.school_class_subject_id == student.select_class_id
        )

    exams = exams_query.all()

    if not exams:
        return {"message": "No exams found.", "count": 0, "data": []}

    # Optimized counts
    student_counts = dict(
        db.query(StudentAdminExamData.exam_id, func.count(StudentAdminExamData.id))
        .group_by(StudentAdminExamData.exam_id)
        .all()
    )

    question_counts = dict(
        db.query(AdminExamBank.exam_id, func.count(AdminExamBank.id))
        .group_by(AdminExamBank.exam_id)
        .all()
    )

    response = []
    now = datetime.now(timezone.utc)
    expired_updated = False

    for exam in exams:
        # ✅ SAFE expiry handling
        if exam.exam_validity:
            validity = exam.exam_validity

            # Convert string → datetime if needed
            if isinstance(validity, str):
                try:
                    validity = datetime.fromisoformat(validity)
                except ValueError:
                    validity = None

            # Make timezone-aware if naive
            if validity and validity.tzinfo is None:
                validity = validity.replace(tzinfo=timezone.utc)

            if validity and validity < now:
                if exam.status != AdminExamStatus.EXPIRED:
                    exam.status = AdminExamStatus.EXPIRED
                    expired_updated = True

        response.append(
            {
                "exam_id": exam.id,
                "name": exam.name,
                "class_name": exam.school_class_subject.class_name,
                "subject": exam.school_class_subject.subject,
                "exam_type": exam.exam_type.value,
                "question_type": exam.question_type.value,
                "passing_mark": exam.passing_mark,
                "duration": exam.duration,
                "repeat_allowed": exam.repeat,
                "valid_until": exam.exam_validity,
                "status": exam.status.value,
                "no_of_questions": question_counts.get(exam.id, 0),
                "no_of_students_attempted": student_counts.get(exam.id, 0),
            }
        )

    # Commit once if any expired updated
    if expired_updated:
        db.commit()

    return {
        "message": "Exam list retrieved successfully.",
        "count": len(response),
        "data": response,
    }


@router.put("/exams/{exam_id}/")
def update_exam(
    exam_id: str,
    payload: AdminExamUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(UserRole.ADMIN, UserRole.STAFF)),
):
    _ensure_admin_staff_permission(current_user, db, StaffPermissionType.EXAMS)
    exam = db.query(AdminExam).filter(AdminExam.id == exam_id).first()

    if not exam:
        raise HTTPException(404, "Exam not found.")

    update_data = payload.dict(exclude_unset=True)

    if "school_class_subject_id" in update_data:
        scs = (
            db.query(SchoolClassSubject)
            .filter(SchoolClassSubject.id == update_data["school_class_subject_id"])
            .first()
        )

        if not scs:
            raise HTTPException(404, "Invalid school_class_subject_id provided.")

    for field, value in update_data.items():
        setattr(exam, field, value)

    try:
        db.commit()
        db.refresh(exam)

        return {"detail": "Exam updated successfully.", "exam_id": exam.id}

    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(500, f"Database error: {str(e)}")


@router.delete("/exams/{exam_id}/")
def delete_exam(
    exam_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(UserRole.ADMIN)),
):
    exam = db.query(AdminExam).filter(AdminExam.id == exam_id).first()

    if not exam:
        raise HTTPException(404, "Exam not found.")

    try:
        db.delete(exam)
        db.commit()

        return {"detail": "Exam deleted successfully."}

    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(500, f"Database error: {str(e)}")


@router.post("/add-questions/{exam_id}/")
async def add_questions(
    exam_id: str,
    payload: ExamQuestionPayloadList,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(UserRole.ADMIN)),
):
    try:
        exam = db.query(AdminExam).filter(AdminExam.id == exam_id).first()
        if not exam:
            raise HTTPException(status_code=404, detail="Exam not found")

        questions_to_insert = []

        for q in payload.questions:
            if q.que_type not in ["short", "long"]:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unsupported exam question type: {q.que_type}",
                )

            # --- COMMON FIELDS ---
            db_entry = AdminExamBank(
                exam_id=exam_id, question=q.question, que_type=q.que_type, image=q.image
            )

            # --- SHORT TYPE (MCQ) ---
            if q.que_type == "short":
                if not (
                    q.option_a
                    and q.option_b
                    and q.option_c
                    and q.option_d
                    and q.correct_option
                ):
                    raise HTTPException(
                        status_code=400,
                        detail="Short questions require options and correct_option",
                    )

                db_entry.option_a = q.option_a
                db_entry.option_b = q.option_b
                db_entry.option_c = q.option_c
                db_entry.option_d = q.option_d
                db_entry.correct_option = q.correct_option

                # Clear descriptive fields
                db_entry.descriptive_answer = None
                db_entry.answer_keys = None

            # --- LONG TYPE ---
            elif q.que_type == "long":
                if not (q.descriptive_answer and q.answer_keys):
                    raise HTTPException(
                        status_code=400,
                        detail="Long questions require descriptive_answer and answer_keys",
                    )

                db_entry.descriptive_answer = q.descriptive_answer
                db_entry.answer_keys = q.answer_keys

                # Clear MCQ fields
                db_entry.option_a = None
                db_entry.option_b = None
                db_entry.option_c = None
                db_entry.option_d = None
                db_entry.correct_option = None

            questions_to_insert.append(db_entry)

        db.add_all(questions_to_insert)
        db.commit()

        return {
            "message": "Questions added successfully",
            "count": len(questions_to_insert),
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500, detail=f"Error processing questions: {str(e)}"
        )


@router.get("/exams/{exam_id}/questions/")
def get_exam_questions(
    exam_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(UserRole.ADMIN, UserRole.SELF_SIGNED_STUDENT)),
):
    # Check if exam exists
    exam = db.query(AdminExam).filter(AdminExam.id == exam_id).first()
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found.")

    # Fetch question list
    questions = db.query(AdminExamBank).filter(AdminExamBank.exam_id == exam_id).all()

    if not questions:
        return []

    response_data = []

    for q in questions:
        base = {
            "id": q.id,
            "question": q.question,
            "que_type": q.que_type,
            "image": q.image,
        }

        if q.que_type == QuestionType.short:  # MCQ
            base["options"] = {
                "option_a": q.option_a,
                "option_b": q.option_b,
                "option_c": q.option_c,
                "option_d": q.option_d,
            }

            # Show answer only to ADMIN
            if current_user.role == UserRole.ADMIN:
                base["correct_option"] = q.correct_option

        elif q.que_type == QuestionType.long:  # Descriptive
            # Only admin sees answer
            if current_user.role == UserRole.ADMIN:
                base["descriptive_answer"] = q.descriptive_answer
                base["answer_keys"] = q.answer_keys

        response_data.append(base)

    return response_data


@router.get("/exams/{exam_id}/details/")
def get_exam_details(
    exam_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(UserRole.ADMIN, UserRole.SELF_SIGNED_STUDENT)),
):
    # 1️⃣ Fetch exam with relationship
    exam = (
        db.query(AdminExam)
        .join(SchoolClassSubject)
        .filter(AdminExam.id == exam_id)
        .first()
    )

    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found.")

    # 2️⃣ Count total questions
    total_questions = (
        db.query(func.count(AdminExamBank.id))
        .filter(AdminExamBank.exam_id == exam_id)
        .scalar()
    )

    # 3️⃣ Count total students appeared
    total_students_appeared = (
        db.query(func.count(StudentAdminExamData.id))
        .filter(StudentAdminExamData.exam_id == exam_id)
        .scalar()
    )

    # 4️⃣ Safe expiry handling (NO DB update)
    status = exam.status
    now = datetime.now(timezone.utc)

    if exam.exam_validity:
        validity = exam.exam_validity

        if isinstance(validity, str):
            try:
                validity = datetime.fromisoformat(validity)
            except ValueError:
                validity = None

        if validity and validity.tzinfo is None:
            validity = validity.replace(tzinfo=timezone.utc)

        if validity and validity < now:
            status = AdminExamStatus.EXPIRED

    return {
        "exam_id": exam.id,
        "name": exam.name,
        "exam_type": exam.exam_type.value,
        "question_type": exam.question_type.value,
        # ✅ FIXED HERE
        "class_name": exam.school_class_subject.class_name,
        "subject": exam.school_class_subject.subject,
        "duration": exam.duration,
        "passing_mark": exam.passing_mark,
        "total_questions": total_questions,
        "attempts_allowed": exam.repeat,
        "total_students_appeared": total_students_appeared,
        "status": status.value,
        "description": exam.description,
        "exam_validity": exam.exam_validity,
    }


@router.post("/admin-exams/{exam_id}/submit")
def submit_admin_exam(
    exam_id: str,
    submission: StudentExamSubmitRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 1️⃣ Role check
    if current_user.role != UserRole.SELF_SIGNED_STUDENT:
        raise HTTPException(
            status_code=403, detail="Only students can submit admin exams"
        )

    # 2️⃣ Student profile check
    student_profile = current_user.self_signed_student_profile
    if not student_profile:
        raise HTTPException(status_code=400, detail="Student profile not found")

    # 3️⃣ Attempt number
    last_attempt = (
        db.query(StudentAdminExamData)
        .filter(
            StudentAdminExamData.student_id == student_profile.id,
            StudentAdminExamData.exam_id == exam_id,
        )
        .order_by(StudentAdminExamData.attempt_no.desc())
        .first()
    )
    next_attempt_no = last_attempt.attempt_no + 1 if last_attempt else 1

    # 4️⃣ Fetch admin MCQs
    mcqs = db.query(AdminExamBank).filter(AdminExamBank.exam_id == exam_id).all()

    if not mcqs:
        raise HTTPException(status_code=404, detail="No questions found for this exam")

    mcq_map = {mcq.id: mcq for mcq in mcqs}

    # 5️⃣ Evaluation
    correct_count = 0
    total = len(submission.answers)

    for ans in submission.answers:
        mcq = mcq_map.get(ans.question_id)
        if not mcq:
            continue

        correct_options = mcq.correct_option
        selected_options = ans.selected_option

        # Normalize to list
        if not isinstance(correct_options, list):
            correct_options = [correct_options]
        if not isinstance(selected_options, list):
            selected_options = [selected_options]

        matched = [opt for opt in selected_options if opt in correct_options]
        correct_count += len(matched)

    result_percentage = (correct_count / total * 100) if total > 0 else 0
    status_result = (
        StudentExamStatus.pass_ if result_percentage >= 40 else StudentExamStatus.fail
    )

    # 6️⃣ Save submission
    student_exam = StudentAdminExamData(
        student_id=student_profile.id,
        exam_id=exam_id,
        attempt_no=next_attempt_no,
        answers=[ans.dict() for ans in submission.answers],
        result=result_percentage,
        status=status_result,
        appeared_count=1,
        submitted_at=datetime.utcnow(),
    )

    db.add(student_exam)
    db.commit()
    db.refresh(student_exam)

    # 7️⃣ Update class rank
    update_admin_exam_class_ranks(
        db=db, exam_id=exam_id, class_name=student_profile.select_class
    )

    return {
        "detail": "Admin exam submitted successfully",
        "exam_id": exam_id,
        "attempt_no": next_attempt_no,
        "result": result_percentage,
        "status": status_result,
    }


@router.post("/set/")
def create_question_set(
    payload: QuestionSetCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(UserRole.ADMIN)),
):

    # Check if set exists already
    existing = (
        db.query(QuestionSet)
        .filter(
            QuestionSet.board == payload.board,
            QuestionSet.class_name == payload.class_name,
            QuestionSet.set == payload.set,
        )
        .first()
    )

    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Set '{payload.set}' already exists for board '{payload.board}' and class '{payload.class_name}'.",
        )

    # Create
    new_set = QuestionSet(
        board=payload.board,
        class_name=payload.class_name,
        set=payload.set,
        description=payload.description,
    )

    db.add(new_set)
    db.commit()
    db.refresh(new_set)

    return {"message": "Question set created successfully", "set_id": new_set.id}


@router.get("/set/")
def list_question_sets(
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(UserRole.ADMIN, UserRole.SELF_SIGNED_STUDENT)),
):

    query = (
        db.query(
            QuestionSet.id,
            QuestionSet.board,
            QuestionSet.class_name,
            QuestionSet.set,
            QuestionSet.created_at,
            func.count(QuestionSetBank.id).label("question_count"),
        )
        .outerjoin(QuestionSetBank, QuestionSet.id == QuestionSetBank.question_set_id)
        .group_by(QuestionSet.id)
    )

    # ------------------------ ROLE BASED FILTER ------------------------
    if current_user.role == UserRole.SELF_SIGNED_STUDENT:
        student = (
            db.query(SelfSignedStudent)
            .filter(SelfSignedStudent.user_id == current_user.id)
            .first()
        )

        if not student:
            raise HTTPException(status_code=404, detail="Student profile not found.")

        if not student.select_class:
            raise HTTPException(
                status_code=400, detail="Student has not selected a class yet."
            )

        # Filter: student only sees question sets of their class
        query = query.filter(QuestionSet.class_name == student.select_class)

    # Admin sees all sets → no filter applied

    # ------------------------ ORDER / FETCH ------------------------
    result = query.order_by(QuestionSet.created_at.desc()).all()

    response = [
        {
            "id": row.id,
            "name": f"{row.board} - Class {row.class_name} - Set {row.set.value}",
            "class_name": row.class_name,
            "set": row.set.value,
            "num_of_questions": row.question_count,
            "created_at": row.created_at,
        }
        for row in result
    ]

    return response


@router.get("/set/{set_id}/")
def get_question_set_details(
    set_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(
        require_roles(UserRole.ADMIN, UserRole.SELF_SIGNED_STUDENT, UserRole.STAFF)
    ),
):
    _ensure_admin_staff_permission(current_user, db, StaffPermissionType.EXAMS)
    # Fetch the set
    question_set = db.query(QuestionSet).filter(QuestionSet.id == set_id).first()

    if not question_set:
        raise HTTPException(status_code=404, detail="Question set not found")

    return {
        "id": question_set.id,
        "board": question_set.board,
        "class_name": question_set.class_name,
        "set": question_set.set.value,
        "description": question_set.description,
        "created_at": question_set.created_at,
        "updated_at": question_set.updated_at,
    }


@router.delete("/set/{set_id}/")
def delete_question_set(
    set_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(UserRole.ADMIN)),
):
    # 1️⃣ Fetch question set
    question_set = db.query(QuestionSet).filter(QuestionSet.id == set_id).first()

    if not question_set:
        raise HTTPException(status_code=404, detail="Question set not found")

    # 2️⃣ Delete related questions first (important)
    db.query(QuestionSetBank).filter(QuestionSetBank.question_set_id == set_id).delete(
        synchronize_session=False
    )

    # 3️⃣ Delete question set
    db.delete(question_set)
    db.commit()

    return {"message": "Question set deleted successfully", "set_id": set_id}


@router.post("/set/{set_id}/questions")
def add_questions_to_set(
    set_id: int,
    payload: BulkQuestionCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(UserRole.ADMIN, UserRole.SELF_SIGNED_STUDENT)),
):

    # Check if Set exists
    question_set = db.query(QuestionSet).filter(QuestionSet.id == set_id).first()
    if not question_set:
        raise HTTPException(status_code=404, detail="Question set not found")

    created_questions = []

    for item in payload.questions:
        new_question = QuestionSetBank(
            question_set_id=set_id,  # ✅ Correct field
            subject=item.subject_id,  # If you're using school_class_subject id, change this to item.subject_id
            year=item.year,
            question=item.question,
            probability_ratio=item.probability_ratio,
            no_of_teacher_verified=item.teacher_verified_count,
        )

        db.add(new_question)
        created_questions.append(new_question)

    db.commit()

    return {
        "message": f"{len(created_questions)} question(s) added successfully to set {set_id}",
        "added_count": len(created_questions),
    }


@router.get("/set/{set_id}/questions")
def get_questions_by_set(
    set_id: int,
    subject_name: Optional[str] = None,
    year: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(UserRole.ADMIN, UserRole.SELF_SIGNED_STUDENT)),
):
    # 1️⃣ Check if question set exists
    question_set = db.query(QuestionSet).filter(QuestionSet.id == set_id).first()

    if not question_set:
        raise HTTPException(status_code=404, detail="Question set not found")

    # 2️⃣ Base query
    query = (
        db.query(QuestionSetBank)
        .join(SchoolClassSubject)
        .options(joinedload(QuestionSetBank.school_class_subject))
        .filter(QuestionSetBank.question_set_id == set_id)
    )

    # 3️⃣ Apply filters
    if subject_name:
        query = query.filter(SchoolClassSubject.subject.ilike(f"%{subject_name}%"))

    if year:
        query = query.filter(QuestionSetBank.year == year)

    questions = query.all()

    # 4️⃣ Response formatting
    response = [
        {
            "id": q.id,
            "school_class_subject_id": q.subject,
            "subject": q.school_class_subject.subject,
            "class_name": q.school_class_subject.class_name,
            "year": q.year,
            "probability_ratio": q.probability_ratio,
            "no_of_teacher_verified": q.no_of_teacher_verified,
            "question": q.question,
            "created_at": q.created_at,
        }
        for q in questions
    ]

    return response


@router.put("/set/question/{question_id}/")
def update_question(
    question_id: int,
    payload: QuestionUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(UserRole.ADMIN)),
):
    # Fetch question
    question = (
        db.query(QuestionSetBank).filter(QuestionSetBank.id == question_id).first()
    )

    if not question:
        raise HTTPException(status_code=404, detail="Question not found")

    # Update only fields sent in request
    if payload.subject_id is not None:
        question.subject = payload.subject_id

    if payload.year is not None:
        question.year = payload.year

    if payload.probability_ratio is not None:
        question.probability_ratio = payload.probability_ratio

    if payload.no_of_teacher_verified is not None:
        question.no_of_teacher_verified = payload.no_of_teacher_verified

    if payload.question is not None:
        question.question = payload.question

    db.commit()
    db.refresh(question)

    return {
        "message": f"Question {question_id} updated successfully",
        "updated_question": question_id,
    }


@router.delete("/set/question/{question_id}/")
def delete_question(
    question_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(UserRole.ADMIN)),
):
    # Retrieve question
    question = (
        db.query(QuestionSetBank).filter(QuestionSetBank.id == question_id).first()
    )

    if not question:
        raise HTTPException(status_code=404, detail="Question not found")

    # Delete
    db.delete(question)
    db.commit()

    return {"message": f"Question {question_id} deleted successfully"}


@router.post(
    "/admin/recharge-plans/", response_model=RechargePlanResponse, status_code=201
)
def create_recharge_plan(
    payload: RechargePlanCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=403, detail="Only admin can create recharge plans"
        )

    # ✅ Check class exists
    school_class = (
        db.query(SchoolClassSubject)
        .filter(SchoolClassSubject.id == payload.class_id)
        .first()
    )

    if not school_class:
        raise HTTPException(status_code=404, detail="Class not found")

    # ✅ Prevent duplicate plan
    existing_plan = (
        db.query(RechargePlan)
        .filter(
            RechargePlan.class_id == payload.class_id,
            RechargePlan.duration == payload.duration,
            RechargePlan.is_active == True,
        )
        .first()
    )

    if existing_plan:
        raise HTTPException(
            status_code=400,
            detail="Recharge plan already exists for this class and duration",
        )

    validity_days = get_validity_days(payload.duration)

    plan = RechargePlan(
        class_id=payload.class_id,
        duration=payload.duration,
        amount=payload.amount,
        validity_days=validity_days,
    )

    db.add(plan)
    db.commit()
    db.refresh(plan)

    return plan


@router.get("/recharge-plans")
def get_recharge_plans(
    class_name: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

    query = db.query(RechargePlan).join(SchoolClassSubject)

    if current_user.role == UserRole.ADMIN:
        if class_name:
            query = query.filter(SchoolClassSubject.class_name == class_name)

        plans = query.order_by(
            case(
                (RechargePlan.duration == PlanDuration.MONTHLY, 1),
                (RechargePlan.duration == PlanDuration.QUARTERLY, 2),
                (RechargePlan.duration == PlanDuration.YEARLY, 3),
            )
        ).all()

        if not plans:
            raise HTTPException(404, "No recharge plans found")

        return plans

    if current_user.role == UserRole.SELF_SIGNED_STUDENT:
        student = (
            db.query(SelfSignedStudent)
            .filter(SelfSignedStudent.user_id == current_user.id)
            .first()
        )
        if not student or not student.select_class_id:
            raise HTTPException(400, "Student class not set")

        plans = (
            query.filter(
                RechargePlan.class_id == student.select_class_id,
                RechargePlan.is_active == True,
            )
            .order_by(
                case(
                    (RechargePlan.duration == PlanDuration.MONTHLY, 1),
                    (RechargePlan.duration == PlanDuration.QUARTERLY, 2),
                    (RechargePlan.duration == PlanDuration.YEARLY, 3),
                )
            )
            .all()
        )

        if not plans:
            raise HTTPException(404, "No recharge plans found for your class")

        return plans

    raise HTTPException(403, "Not authorized")


@router.post(
    "/student/purchase-plan/", response_model=StudentPurchaseResponse, status_code=201
)
def student_purchase_plan(
    payload: StudentPurchaseRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != UserRole.SELF_SIGNED_STUDENT:
        raise HTTPException(403, "Only students can purchase plans")

    student = (
        db.query(SelfSignedStudent)
        .filter(SelfSignedStudent.user_id == current_user.id)
        .first()
    )

    if not student:
        raise HTTPException(404, "Student profile not found")

    if not student.select_class_id:
        raise HTTPException(400, "Student has not selected a class")

    # ✅ Fetch plan using class_id
    plan = (
        db.query(RechargePlan)
        .filter(
            RechargePlan.class_id == student.select_class_id,
            RechargePlan.duration == payload.duration,
            RechargePlan.is_active == True,
        )
        .first()
    )

    if not plan:
        raise HTTPException(404, "Recharge plan not available")

    # Deactivate old subscription
    db.query(StudentSubscription).filter(
        StudentSubscription.student_id == student.id,
        StudentSubscription.is_current == True,
    ).update({"is_current": False})

    start_date = datetime.utcnow()
    end_date = start_date + timedelta(days=plan.validity_days)

    subscription = StudentSubscription(
        student_id=student.id,
        plan_id=plan.id,
        start_date=start_date,
        end_date=end_date,
        amount_paid=plan.amount,
        is_current=True,
    )

    db.add(subscription)
    db.flush()

    payment = Payment(
        student_id=student.id,
        subscription_id=subscription.id,
        amount=plan.amount,
        payment_status=PaymentStatus.PENDING,
    )

    db.add(payment)
    db.commit()

    db.refresh(subscription)
    db.refresh(payment)

    return {
        "subscription_id": subscription.id,
        "payment_id": payment.id,
        "amount": plan.amount,
        "status": "pending",
    }


@router.get("/admin/students/")
def admin_get_all_students(
    class_name: Optional[str] = None,
    school_name: Optional[str] = None,
    district: Optional[str] = None,
    status: Optional[StudentStatus] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 🔐 Admin only
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Only admin can view student list")

    query = db.query(SelfSignedStudent)

    # 🔎 Apply filters dynamically
    if class_name:
        query = query.filter(SelfSignedStudent.select_class == class_name)

    if school_name:
        query = query.filter(SelfSignedStudent.school_name.ilike(f"%{school_name}%"))

    if district:
        query = query.filter(SelfSignedStudent.district.ilike(f"%{district}%"))

    if status:
        query = query.filter(SelfSignedStudent.status == status)

    students = query.order_by(SelfSignedStudent.created_at.desc()).all()

    return [
        {
            "id": student.id,
            "full_name": f"{student.first_name} {student.last_name}",
            "select_class": student.select_class,
            "school_name": student.school_name,
            "school_location": student.school_location,
            "status": student.status,
            "created_at": student.created_at,
        }
        for student in students
    ]


@router.get("/admin/payments/analytics/")
def admin_payment_analytics(
    school_name: Optional[str] = None,
    district: Optional[str] = None,
    state: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    group_by: Optional[str] = "school",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 🔐 Admin only
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(403, "Only admin can view analytics")

    # Base query
    query = (
        db.query(func.sum(Payment.amount).label("total_amount"))
        .join(SelfSignedStudent, Payment.student_id == SelfSignedStudent.id)
        .filter(Payment.payment_status == PaymentStatus.SUCCESS)
    )

    # 📅 Date filter
    if start_date:
        query = query.filter(Payment.created_at >= start_date)

    if end_date:
        query = query.filter(Payment.created_at <= end_date)

    # 🏫 School filter
    if school_name:
        query = query.filter(SelfSignedStudent.school_name.ilike(f"%{school_name}%"))

    # 🌍 District filter
    if district:
        query = query.filter(SelfSignedStudent.district.ilike(f"%{district}%"))

    # 🗺 State filter
    if state:
        query = query.filter(SelfSignedStudent.state.ilike(f"%{state}%"))

    # 📊 Grouping logic
    if group_by == "school":
        query = query.add_columns(
            SelfSignedStudent.school_name.label("group_value")
        ).group_by(SelfSignedStudent.school_name)

    elif group_by == "district":
        query = query.add_columns(
            SelfSignedStudent.district.label("group_value")
        ).group_by(SelfSignedStudent.district)

    elif group_by == "state":
        query = query.add_columns(
            SelfSignedStudent.state.label("group_value")
        ).group_by(SelfSignedStudent.state)

    else:
        raise HTTPException(
            status_code=400, detail="group_by must be one of: school, district, state"
        )

    results = query.all()

    return [
        {"group_value": row.group_value, "total_amount": row.total_amount or 0}
        for row in results
    ]


@router.post("/payment-configurations/", status_code=status.HTTP_201_CREATED)
def create_payment_configuration(
    data: PaymentConfigurationCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(UserRole.ADMIN)),
):
    exists = (
        db.query(PaymentConfiguration)
        .filter(PaymentConfiguration.class_id == data.class_id)
        .first()
    )

    if exists:
        raise HTTPException(
            status_code=400,
            detail="Payment configuration already exists for this class",
        )

    config = PaymentConfiguration(**data.dict())
    db.add(config)
    db.commit()
    db.refresh(config)

    return {"detail": "Payment configuration created successfully"}


@router.put("/payment-configurations/{config_id}")
def update_payment_configuration(
    config_id: int,
    data: PaymentConfigurationUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(UserRole.ADMIN)),
):
    config = (
        db.query(PaymentConfiguration)
        .filter(PaymentConfiguration.id == config_id)
        .first()
    )

    if not config:
        raise HTTPException(status_code=404, detail="Configuration not found")

    for field, value in data.dict().items():
        setattr(config, field, value)

    db.commit()
    db.refresh(config)

    return {"detail": "Payment configuration updated successfully"}


@router.get(
    "/payment-configurations/", response_model=list[PaymentConfigurationResponse]
)
def get_all_payment_configurations(
    db: Session = Depends(get_db), current_user=Depends(require_roles(UserRole.ADMIN))
):
    return db.query(PaymentConfiguration).order_by(PaymentConfiguration.id.asc()).all()


@router.get(
    "/payment-configurations/{config_id}", response_model=PaymentConfigurationResponse
)
def get_payment_configuration_detail(
    config_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(UserRole.ADMIN)),
):
    config = (
        db.query(PaymentConfiguration)
        .filter(PaymentConfiguration.id == config_id)
        .first()
    )

    if not config:
        raise HTTPException(status_code=404, detail="Configuration not found")

    return config


# FAQ Management Endpoints


@router.post("/faqs/", response_model=FAQResponse, status_code=status.HTTP_201_CREATED)
def create_faq(
    faq_data: FAQCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Create a new FAQ. Only super admin can create FAQs.
    """

    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only super admin can create FAQs",
        )

    try:
        faq = FAQ(
            question=faq_data.question,
            answer=faq_data.answer,
            created_by=current_user.id,
            is_active=faq_data.is_active,
        )
        db.add(faq)
        db.commit()
        db.refresh(faq)
        return faq
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create FAQ: {str(e)}",
        )


@router.get("/faqs/", response_model=List[FAQResponse])
def get_all_faqs(
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get all FAQs. Admin and school can view all FAQs.
    """
    if current_user.role not in (UserRole.ADMIN, UserRole.SCHOOL):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin or school can view all FAQs",
        )

    query = db.query(FAQ)
    if is_active is not None:
        query = query.filter(FAQ.is_active == is_active)

    faqs = query.order_by(FAQ.created_at.desc()).all()
    return faqs


@router.put("/faqs/{faq_id}/", response_model=FAQResponse)
def update_faq(
    faq_id: int,
    faq_data: FAQUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Update an existing FAQ. Only super admin can update FAQs.
    """
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only super admin can update FAQs",
        )

    faq = db.query(FAQ).filter(FAQ.id == faq_id).first()
    if not faq:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="FAQ not found"
        )

    try:
        if faq_data.question is not None:
            faq.question = faq_data.question
        if faq_data.answer is not None:
            faq.answer = faq_data.answer
        if faq_data.is_active is not None:
            faq.is_active = faq_data.is_active
        faq.updated_at = func.now()

        db.commit()
        db.refresh(faq)
        return faq
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update FAQ: {str(e)}",
        )


@router.delete("/faqs/{faq_id}/", status_code=status.HTTP_204_NO_CONTENT)
def delete_faq(
    faq_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Delete an FAQ. Only super admin can delete FAQs.
    """
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only super admin can delete FAQs",
        )

    faq = db.query(FAQ).filter(FAQ.id == faq_id).first()
    if not faq:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="FAQ not found"
        )

    try:
        db.delete(faq)
        db.commit()
        return None
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete FAQ: {str(e)}",
        )


# ---------- Support Plus (admin) ----------
@router.get("/supportplus", response_model=List[SupportPlusResponse])
def admin_list_supportplus(
    school_id: Optional[str] = Query(None, description="Filter by school ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    """List all Support Plus records. Optionally filter by school_id."""
    q = db.query(SupportPlus).order_by(SupportPlus.created_at.desc())
    if school_id:
        q = q.filter(SupportPlus.school_id == school_id)
    rows = q.all()
    return [
        SupportPlusResponse(
            id=r.id,
            school_id=r.school_id,
            looking_for=r.looking_for,
            whatsapp_number=r.whatsapp_number,
            discussion_datetime=r.discussion_datetime,
            files=r.files,
            message=r.message,
            status=r.status.value if hasattr(r.status, "value") else r.status,
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
        for r in rows
    ]


@router.patch("/supportplus/{record_id}", response_model=SupportPlusResponse)
def admin_update_supportplus_status(
    record_id: int,
    data: SupportPlusStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    """Update status of a Support Plus record."""
    record = db.query(SupportPlus).filter(SupportPlus.id == record_id).first()
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Record not found."
        )
    status_map = {
        "pending": SupportPlusStatus.PENDING,
        "in_progress": SupportPlusStatus.IN_PROGRESS,
        "resolved": SupportPlusStatus.RESOLVED,
        "cancelled": SupportPlusStatus.CANCELLED,
    }
    record.status = status_map[data.status]
    try:
        db.commit()
        db.refresh(record)
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    return SupportPlusResponse(
        id=record.id,
        school_id=record.school_id,
        looking_for=record.looking_for,
        whatsapp_number=record.whatsapp_number,
        discussion_datetime=record.discussion_datetime,
        files=record.files,
        message=record.message,
        status=record.status.value,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


# ---------- Business Inquiry (admin sees all) ----------
@router.get("/business-inquiry", response_model=List[BusinessInquiryResponse])
def admin_list_business_inquiry(
    school_id: Optional[str] = Query(
        None, description="Filter by school ID (inquiries containing this school)"
    ),
    date_from: Optional[datetime] = Query(None, description="Filter from date (ISO)"),
    date_to: Optional[datetime] = Query(None, description="Filter to date (ISO)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    """List all business inquiries. Optionally filter by school_id or date range."""
    q = db.query(BusinessInquiry).order_by(BusinessInquiry.created_at.desc())
    if school_id:
        q = q.filter(BusinessInquiry.school_ids.contains([school_id]))
    if date_from is not None:
        q = q.filter(BusinessInquiry.created_at >= date_from)
    if date_to is not None:
        q = q.filter(BusinessInquiry.created_at <= date_to)
    rows = q.all()
    return [
        BusinessInquiryResponse(
            id=r.id,
            school_ids=r.school_ids,
            guardian_name=r.guardian_name,
            phone=r.phone,
            email=r.email,
            location=r.location,
            student_name=r.student_name,
            standard_in_academic=r.standard_in_academic,
            inquiry_for_class=r.inquiry_for_class,
            desire_to_know=r.desire_to_know,
            files=r.files,
            message=r.message,
            created_at=r.created_at,
        )
        for r in rows
    ]


# CREATE HOLIDAY
@router.post("/holidays", response_model=HolidayMasterResponse)
def create_holiday(
    name: str = Form(...),
    type: str = Form(...),
    date: date = Form(...),
    description: Optional[str] = Form(None),
    file: UploadFile = File(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    try:
        name = name.strip()
        type = type.strip()

        if len(name) < 2 or len(name) > 255:
            raise HTTPException(
                status_code=400, detail="Name must be between 2 and 255 characters"
            )

        if len(type) < 2 or len(type) > 100:
            raise HTTPException(
                status_code=400, detail="Type must be between 2 and 100 characters"
            )

        if description and len(description) > 500:
            raise HTTPException(status_code=400, detail="Description max length is 500")

        file_url = None
        if file and file.filename:
            file_url = upload_to_s3(file, "holidays")

        holiday = HolidayMaster(
            name=name,
            type=type,
            date=date,
            description=description,
            file=file_url,
        )

        db.add(holiday)
        db.commit()
        db.refresh(holiday)

        return holiday

    except HTTPException:
        raise

    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Database error occurred")

    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/holidays/", response_model=List[HolidayMasterResponse])
def get_all_holidays(
    is_deleted: Optional[bool] = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(UserRole.ADMIN, UserRole.STAFF, UserRole.SCHOOL)
    ),
):
    _ensure_admin_staff_permission(current_user, db, StaffPermissionType.HELP_DESK)
    try:
        holidays = (
            db.query(HolidayMaster)
            .filter(HolidayMaster.is_deleted.is_(is_deleted))
            .order_by(HolidayMaster.created_at.desc())
            .all()
        )

        return holidays

    except Exception:
        raise HTTPException(status_code=500, detail="Failed to fetch holidays")


@router.patch("/holidays/{id}", response_model=HolidayMasterResponse)
def update_holiday(
    id: int,
    name: Optional[str] = Form(None),
    type: Optional[str] = Form(None),
    date: Optional[date] = Form(None),
    description: Optional[str] = Form(None),
    file: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    try:
        holiday = (
            db.query(HolidayMaster)
            .filter(HolidayMaster.id == id, HolidayMaster.is_deleted.is_(False))
            .first()
        )

        if not holiday:
            raise HTTPException(status_code=404, detail="Holiday not found")

        if name:
            name = name.strip()
            if len(name) < 2 or len(name) > 255:
                raise HTTPException(
                    status_code=400, detail="Name must be between 2 and 255 characters"
                )
            holiday.name = name

        if type:
            type = type.strip()
            if len(type) < 2 or len(type) > 100:
                raise HTTPException(
                    status_code=400, detail="Type must be between 2 and 100 characters"
                )
            holiday.type = type

        if date:
            holiday.date = date

        if description:
            if len(description) > 500:
                raise HTTPException(
                    status_code=400, detail="Description max length is 500"
                )
            holiday.description = description

        if file and file.filename:
            holiday.file = upload_to_s3(file, "holidays")

        db.commit()
        db.refresh(holiday)

        return holiday

    except HTTPException:
        raise

    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Database error occurred")

    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/holidays/{id}")
def delete_holiday(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    try:
        holiday = (
            db.query(HolidayMaster)
            .filter(HolidayMaster.id == id, HolidayMaster.is_deleted.is_(False))
            .first()
        )

        if not holiday:
            raise HTTPException(status_code=404, detail="Holiday not found")

        holiday.is_deleted = True

        db.commit()

        return {"message": "Holiday deleted successfully"}

    except HTTPException:
        raise

    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Database error occurred")


@router.post("/subscription/create-order")
def create_order(
    plan_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != UserRole.SELF_SIGNED_STUDENT:
        raise HTTPException(status_code=403, detail="Only students allowed")

    student = current_user.self_signed_student_profile

    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    plan = db.query(RechargePlan).filter(
        RechargePlan.id == plan_id,
        RechargePlan.is_active == True
    ).first()

    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    # 🔥 Create Razorpay Order
    order_data = {
        "amount": plan.amount * 100,  # paise
        "currency": "INR",
        "payment_capture": 1
    }

    razorpay_order = razorpay_client.order.create(order_data)

    # 🔥 Create subscription (temporary)
    subscription = StudentSubscription(
        student_id=student.id,
        plan_id=plan.id,
        start_date=datetime.utcnow(),
        end_date=datetime.utcnow(),  # will update later
        amount_paid=plan.amount,
        is_current=False,
    )
    db.add(subscription)
    db.commit()
    db.refresh(subscription)

    # 🔥 Create payment entry
    payment = Payment(
        student_id=student.id,
        subscription_id=subscription.id,
        amount=plan.amount,
        payment_status=PaymentStatus.PENDING,
        gateway_order_id=razorpay_order["id"],
    )
    db.add(payment)
    db.commit()

    return {
        "order_id": razorpay_order["id"],
        "amount": plan.amount,
        "currency": "INR",
        "subscription_id": subscription.id
    }

@router.post("/subscription/verify-payment")
def verify_payment(
    payload: VerifyPaymentRequest,
    db: Session = Depends(get_db),
):
    print("API HIT")

    try:
        razorpay_client.utility.verify_payment_signature({
            "razorpay_order_id": payload.razorpay_order_id,
            "razorpay_payment_id": payload.razorpay_payment_id,
            "razorpay_signature": payload.razorpay_signature,
        })
    except Exception as e:
        print("SIGNATURE ERROR:", e)
        raise HTTPException(status_code=400, detail="Payment verification failed")

    payment = db.query(Payment).filter(
        Payment.gateway_order_id == payload.razorpay_order_id
    ).first()

    print("PAYMENT FOUND:", payment)

    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")

    if payment.payment_status == PaymentStatus.SUCCESS:
        return {"message": "Already verified"}

    payment.payment_status = PaymentStatus.SUCCESS
    payment.gateway_payment_id = payload.razorpay_payment_id

    subscription = payment.subscription
    plan = subscription.plan

    start_date = datetime.utcnow()
    end_date = start_date + timedelta(days=plan.validity_days)

    db.query(StudentSubscription).filter(
        StudentSubscription.student_id == subscription.student_id
    ).update({"is_current": False})

    subscription.start_date = start_date
    subscription.end_date = end_date
    subscription.is_current = True

    db.commit()

    return {"message": "Payment successful"}

@router.get("/payments/student")
def get_student_payment_details(
    student_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

    # ==================================================
    # ROLE HANDLING
    # ==================================================

    # ✅ STUDENT → auto fetch own id
    if current_user.role == UserRole.SELF_SIGNED_STUDENT:
        student = current_user.self_signed_student_profile

        if not student:
            raise HTTPException(status_code=404, detail="Student not found")

        student_id = student.id

    # ✅ ADMIN / SCHOOL → must pass student_id
    elif current_user.role in [UserRole.ADMIN, UserRole.SCHOOL]:

        if not student_id:
            raise HTTPException(
                status_code=400,
                detail="student_id is required",
            )

        student = db.query(SelfSignedStudent).filter(
            SelfSignedStudent.id == student_id
        ).first()

        if not student:
            raise HTTPException(status_code=404, detail="Student not found")

        # ✅ SCHOOL restriction
        if current_user.role == UserRole.SCHOOL:
            school = db.query(School).filter(
                School.user_id == current_user.id
            ).first()

            if not school:
                raise HTTPException(status_code=404, detail="School not found")

            is_valid = (
                db.query(StudentSubscription)
                .join(RechargePlan)
                .join(SchoolClassSubject)
                .filter(
                    StudentSubscription.student_id == student_id,
                    SchoolClassSubject.school_id == school.id,
                )
                .first()
            )

            if not is_valid:
                raise HTTPException(status_code=403, detail="Not allowed")

    else:
        raise HTTPException(status_code=403, detail="Not authorized")

    # ==================================================
    # FETCH PAYMENTS (DESC ORDER + OPTIMIZED)
    # ==================================================

    payments = (
        db.query(Payment)
        .join(StudentSubscription, Payment.subscription_id == StudentSubscription.id)
        .join(RechargePlan, StudentSubscription.plan_id == RechargePlan.id)
        .filter(StudentSubscription.student_id == student_id)
        .options(
            joinedload(Payment.subscription)  # only this is enough
        )
        .order_by(Payment.created_at.desc())  # ✅ latest first
        .all()
    )

    # ==================================================
    # BUILD RESPONSE
    # ==================================================

    response = []

    for payment in payments:
        subscription = payment.subscription

        # ✅ since we joined RechargePlan, fetch via join (no extra query)
        plan = (
            db.query(RechargePlan)
            .filter(RechargePlan.id == subscription.plan_id)
            .first()
        )

        response.append(
            {
                "payment_id": payment.id,
                "payment_status": payment.payment_status.value,
                "amount": payment.amount,

                "plan": {
                    "plan_id": plan.id,
                    "duration": plan.duration.value,
                    "amount": plan.amount,
                    "validity_days": plan.validity_days,
                },

                "subscription": {
                    "start_date": subscription.start_date,
                    "end_date": subscription.end_date,
                    "is_current": subscription.is_current,
                },

                "payment_gateway": {
                    "order_id": payment.gateway_order_id,
                    "payment_id": payment.gateway_payment_id,
                },

                "created_at": payment.created_at,
            }
        )

    return {
        "student": {
            "student_id": student.id,
            "name": f"{student.first_name} {student.last_name}",
        },
        "total_payments": len(response),
        "payments": response,
    }