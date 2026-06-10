from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from app.db.session import get_db
from app.models.users import User, Otp
from app.models.students import SelfSignedStudent, StudentStatus
from app.models.teachers import (
    SelfSignedTeacher,
    VerificationStatus,
    ProfileStatus,
    SelfSignedTeacherTeachingConfiguration,
)
from app.models.admin import SchoolClassSubject, StudentAdminExamData
from app.schemas.users import UserRole
from app.schemas.selfsignedteachers import (
    SelfSignedTeacherProfileUpdate,
    SelfSignedTeacherProfileResponse,
    VerificationStatusResponse,
    SelfSignedTeacherStudentCreateRequest,
    SelfSignedTeacherStudentJoinRequest,
    SelfSignedTeacherStudentResponse,
    TeachingConfigurationCreateRequest,
    TeachingConfigurationUpdateRequest,
    TeachingConfigurationResponse,
    TeachingConfigurationDetailResponse,
)
from app.utils.email_utility import send_dynamic_email
from app.utils.permission import require_roles, require_self_signed_teacher_active
from app.utils.s3 import upload_to_s3, upload_base64_to_s3
from app.core.security import create_verification_token
from app.utils.staff_logging import log_action
from app.models.staff import ActionType, ResourceType

router = APIRouter()


def _cleanup_existing_user(db: Session, email: str):
    existing_user = db.query(User).filter(User.email == email).first()
    if not existing_user:
        return

    verified_otp = (
        db.query(Otp)
        .filter(Otp.user_id == existing_user.id, Otp.is_verified)
        .first()
    )

    if verified_otp:
        raise HTTPException(status_code=400, detail="Email already exists")

    db.query(Otp).filter(Otp.user_id == existing_user.id).delete()
    db.delete(existing_user)


def _get_pin_location(pin_code: str) -> dict:
    """No postal lookup available for self-signed teachers.

    Institution pin code and address fields are provided manually from the frontend.
    This helper intentionally does not attempt to resolve a postal region.
    """
    return {"division": None, "district": None, "state": None}


def _should_mark_profile_submitted(profile: SelfSignedTeacher) -> bool:
    return all(
        [
            profile.email,
            profile.phone,
            profile.qualification,
            profile.university,
            profile.institution_name,
            profile.designation,
            profile.institution_pin_code,
            profile.joining_date,
            profile.official_id_card,
        ]
    )


@router.get(
    "/self-signed-teacher/profile/",
    response_model=SelfSignedTeacherProfileResponse,
)
def get_self_signed_teacher_profile(
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(UserRole.SELF_SIGNED_TEACHER)),
):
    profile = db.query(SelfSignedTeacher).filter(SelfSignedTeacher.user_id == current_user.id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Teacher profile not found")

    # Merge profile with role from User model
    profile_data = {
        "id": profile.id,
        "user_id": profile.user_id,
        "first_name": profile.first_name,
        "last_name": profile.last_name,
        "gender": profile.gender,
        "dob": profile.dob,
        "phone": profile.phone,
        "email": profile.email,
        "qualification": profile.qualification,
        "university": profile.university,
        "institution_name": profile.institution_name,
        "designation": profile.designation,
        "institution_pin_code": profile.institution_pin_code,
        "division": profile.division,
        "district": profile.district,
        "state": profile.state,
        "landmark": profile.landmark,
        "joining_date": profile.joining_date,
        "official_id_card": profile.official_id_card,
        "profile_status": profile.profile_status,
        "verification_status": profile.verification_status,
        "rejection_reason": profile.rejection_reason,
        "blocked_reason": profile.blocked_reason,
        "verified_by": profile.verified_by,
        "verified_at": profile.verified_at,
        "profile_completed": current_user.profile_completed,
        "created_at": profile.created_at,
        "updated_at": profile.updated_at,
        "role": current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role),
    }
    return profile_data


@router.put("/self-signed-teacher/profile/")
def update_self_signed_teacher_profile(
    update_data: SelfSignedTeacherProfileUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(UserRole.SELF_SIGNED_TEACHER)),
):
    profile = db.query(SelfSignedTeacher).filter(SelfSignedTeacher.user_id == current_user.id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Teacher profile not found")

    updated_fields = update_data.dict(exclude_unset=True)
    for key, value in updated_fields.items():
        if key == "email":
            current_user.email = value
            profile.email = value
            current_user.is_verified = False
        elif key == "phone":
            current_user.phone = value
        elif key == "institution_pin_code":
            location = _get_pin_location(value)
            profile.division = location.get("division")
            profile.district = location.get("district")
            profile.state = location.get("state")
            setattr(profile, key, value)
            continue
        setattr(profile, key, value)

    if _should_mark_profile_submitted(profile):
        profile.profile_status = ProfileStatus.PROFILE_SUBMITTED
        current_user.profile_completed = True

    db.commit()
    db.refresh(profile)
    db.refresh(current_user)

    return {"detail": "Profile updated successfully."}


@router.post("/self-signed-teacher/verify/")
def verify_self_signed_teacher(
    official_id_card: UploadFile = File(...),
    joining_date: str = Form(...),
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(UserRole.SELF_SIGNED_TEACHER)),
):
    profile = db.query(SelfSignedTeacher).filter(SelfSignedTeacher.user_id == current_user.id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Teacher profile not found")

    try:
        uploaded_url = upload_to_s3(official_id_card, f"self_signed_teachers/{profile.id}/official_id_card")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload ID card: {str(e)}")

    profile.official_id_card = uploaded_url
    profile.joining_date = joining_date
    if _should_mark_profile_submitted(profile):
        profile.profile_status = ProfileStatus.PROFILE_SUBMITTED
        current_user.profile_completed = True

    db.commit()
    db.refresh(profile)

    return {"detail": "Teacher verified successfully.", "official_id_card": uploaded_url, "joining_date": joining_date}


@router.get("/self-signed-teacher/verification-status/", response_model=VerificationStatusResponse)
def get_self_signed_teacher_verification_status(
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(UserRole.SELF_SIGNED_TEACHER)),
):
    profile = db.query(SelfSignedTeacher).filter(SelfSignedTeacher.user_id == current_user.id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Teacher profile not found")

    return {
        "verification_status": VerificationStatus(current_user.verification_status),
        "profile_status": profile.profile_status,
        "profile_completed": current_user.profile_completed,
        "rejection_reason": profile.rejection_reason,
        "blocked_reason": profile.blocked_reason,
        "verified_by": profile.verified_by,
        "verified_at": profile.verified_at,
    }


@router.get("/self-signed-teacher/students/")
def list_self_signed_teacher_students(
    student_type: Optional[str] = Query(None, description="internal|external"),
    name: Optional[str] = Query(None, description="Student name search"),
    board: Optional[str] = Query(None, description="Board filter"),
    class_id: Optional[int] = Query(None, description="Class id filter"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(UserRole.SELF_SIGNED_TEACHER)),
):
    teacher = db.query(SelfSignedTeacher).filter(SelfSignedTeacher.user_id == current_user.id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher profile not found")

    query = db.query(SelfSignedStudent).filter(SelfSignedStudent.self_signed_teacher_id == teacher.id)

    if student_type:
        query = query.filter(SelfSignedStudent.student_type == student_type.lower())

    if board:
        query = query.filter(SelfSignedStudent.select_board == board)

    if class_id:
        query = query.filter(SelfSignedStudent.select_class_id == class_id)

    if name:
        like_pattern = f"%{name}%"
        query = query.filter(
            (SelfSignedStudent.first_name.ilike(like_pattern)) | (SelfSignedStudent.last_name.ilike(like_pattern))
        )

    students = query.order_by(SelfSignedStudent.created_at.desc()).offset(offset).limit(limit).all()

    results = []
    for student in students:
        exams_count = (
            db.query(func.count(StudentAdminExamData.id))
            .filter(StudentAdminExamData.student_id == student.id)
            .scalar()
        ) or 0

        latest_rank_row = (
            db.query(StudentAdminExamData.class_rank)
            .filter(StudentAdminExamData.student_id == student.id, StudentAdminExamData.class_rank.is_not(None))
            .order_by(StudentAdminExamData.submitted_at.desc())
            .first()
        )
        global_rank = latest_rank_row[0] if latest_rank_row else None

        results.append({
            "id": student.id,
            "first_name": student.first_name,
            "last_name": student.last_name,
            "student_type": student.student_type,
            "board": student.select_board,
            "class_id": student.select_class_id,
            "exams_appeared": exams_count,
            "global_rank": global_rank,
            "profile_status": student.status,
            "created_at": student.created_at,
        })

    return results


def _get_teacher_profile(db: Session, user_id: int) -> SelfSignedTeacher:
    teacher = db.query(SelfSignedTeacher).filter(SelfSignedTeacher.user_id == user_id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher profile not found")
    return teacher


def _get_class_group(db: Session, class_id: int) -> SchoolClassSubject:
    class_group = db.query(SchoolClassSubject).filter(SchoolClassSubject.id == class_id).first()
    if not class_group:
        raise HTTPException(status_code=400, detail="Selected class is invalid")
    return class_group


def _find_matching_self_signed_teacher(db: Session, board_id: Optional[str], class_id: Optional[int]) -> Optional[int]:
    """Find a teacher whose active teaching configuration matches board+class.

    Returns the teacher id or None.
    """
    if not board_id or not class_id:
        return None

    config = (
        db.query(SelfSignedTeacherTeachingConfiguration)
        .filter(
            SelfSignedTeacherTeachingConfiguration.board_id == board_id,
            SelfSignedTeacherTeachingConfiguration.class_id == class_id,
            SelfSignedTeacherTeachingConfiguration.is_active,
        )
        .order_by(SelfSignedTeacherTeachingConfiguration.created_at.asc())
        .first()
    )
    if not config:
        return None
    return config.self_signed_teacher_id


def _validate_subject_ids(db: Session, class_group: SchoolClassSubject, subject_ids: List[int]) -> None:
    if not subject_ids:
        raise HTTPException(status_code=400, detail="subject_ids is required")

    subject_rows = db.query(SchoolClassSubject).filter(SchoolClassSubject.id.in_(subject_ids)).all()
    if len(subject_rows) != len(subject_ids):
        raise HTTPException(status_code=400, detail="One or more selected subjects are invalid")

    for subject_row in subject_rows:
        if (
            subject_row.school_board != class_group.school_board
            or subject_row.school_medium != class_group.school_medium
            or subject_row.class_name != class_group.class_name
        ):
            raise HTTPException(
                status_code=400,
                detail="All selected subjects must belong to the selected board and class group.",
            )


def _assert_no_duplicate_configuration(
    db: Session,
    teacher_id: int,
    board_id: str,
    class_id: int,
    subject_ids: List[int],
    exclude_configuration_id: int | None = None,
) -> None:
    query = db.query(SelfSignedTeacherTeachingConfiguration).filter(
        SelfSignedTeacherTeachingConfiguration.self_signed_teacher_id == teacher_id,
        SelfSignedTeacherTeachingConfiguration.board_id == board_id,
        SelfSignedTeacherTeachingConfiguration.class_id == class_id,
    )
    if exclude_configuration_id is not None:
        query = query.filter(SelfSignedTeacherTeachingConfiguration.id != exclude_configuration_id)

    for existing in query.all():
        if set(existing.subject_ids or []) == set(subject_ids):
            raise HTTPException(
                status_code=400,
                detail="Duplicate teaching configuration exists for this teacher.",
            )


def _merge_existing_teacher_configuration(
    db: Session,
    teacher_id: int,
    board_id: str,
    class_id: int,
    subject_ids: List[int],
    is_active: bool,
) -> tuple[SelfSignedTeacherTeachingConfiguration | None, bool]:
    configs = (
        db.query(SelfSignedTeacherTeachingConfiguration)
        .filter(
            SelfSignedTeacherTeachingConfiguration.self_signed_teacher_id == teacher_id,
            SelfSignedTeacherTeachingConfiguration.board_id == board_id,
            SelfSignedTeacherTeachingConfiguration.class_id == class_id,
        )
        .all()
    )
    if not configs:
        return None, False

    original_subject_ids = set()
    for config in configs:
        original_subject_ids.update(config.subject_ids or [])

    merged_subject_ids = original_subject_ids | set(subject_ids)
    base_config = configs[0]

    changed = (
        merged_subject_ids != original_subject_ids
        or len(configs) > 1
        or base_config.is_active != is_active
    )

    if changed:
        base_config.subject_ids = sorted(merged_subject_ids)
        base_config.is_active = is_active
        for duplicate_config in configs[1:]:
            db.delete(duplicate_config)
        db.commit()
        db.refresh(base_config)

    return base_config, changed


def _get_teacher_configuration(db: Session, teacher_id: int, configuration_id: int) -> SelfSignedTeacherTeachingConfiguration:
    configuration = (
        db.query(SelfSignedTeacherTeachingConfiguration)
        .filter(
            SelfSignedTeacherTeachingConfiguration.id == configuration_id,
            SelfSignedTeacherTeachingConfiguration.self_signed_teacher_id == teacher_id,
        )
        .first()
    )
    if not configuration:
        raise HTTPException(status_code=404, detail="Teaching configuration not found")
    return configuration


@router.post(
    "/teaching-configurations",
    status_code=status.HTTP_201_CREATED,
    response_model=TeachingConfigurationResponse,
)
def create_teaching_configuration(
    payload: TeachingConfigurationCreateRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_self_signed_teacher_active()),
):
    teacher = _get_teacher_profile(db, current_user.id)
    class_group = _get_class_group(db, payload.class_id)

    if class_group.school_board != payload.board_id:
        raise HTTPException(
            status_code=400,
            detail="Selected board does not match the selected class group.",
        )

    _validate_subject_ids(db, class_group, payload.subject_ids)

    existing_config, changed = _merge_existing_teacher_configuration(
        db,
        teacher.id,
        payload.board_id,
        payload.class_id,
        payload.subject_ids,
        payload.is_active,
    )

    if existing_config:
        if not changed:
            raise HTTPException(
                status_code=400,
                detail="Duplicate teaching configuration exists for this teacher.",
            )
        return existing_config

    configuration = SelfSignedTeacherTeachingConfiguration(
        self_signed_teacher_id=teacher.id,
        board_id=payload.board_id,
        class_id=payload.class_id,
        subject_ids=payload.subject_ids,
        is_active=payload.is_active,
    )
    db.add(configuration)
    db.commit()
    db.refresh(configuration)

    return configuration


@router.get(
    "/teaching-configurations",
    response_model=List[TeachingConfigurationDetailResponse],
)
def list_teaching_configurations(
    db: Session = Depends(get_db),
    current_user=Depends(require_self_signed_teacher_active()),
):
    teacher = _get_teacher_profile(db, current_user.id)
    configurations = (
        db.query(SelfSignedTeacherTeachingConfiguration)
        .filter(
            SelfSignedTeacherTeachingConfiguration.self_signed_teacher_id == teacher.id
        )
        .all()
    )
    results = []
    for configuration in configurations:
        class_group = db.query(SchoolClassSubject).filter(SchoolClassSubject.id == configuration.class_id).first()
        subject_rows = []
        if configuration.subject_ids:
            subject_rows = (
                db.query(SchoolClassSubject)
                .filter(SchoolClassSubject.id.in_(configuration.subject_ids))
                .all()
            )

        subject_details = [
            {"id": subject.id, "subject_name": subject.subject}
            for subject in subject_rows
        ]

        results.append({
            "id": configuration.id,
            "board_id": configuration.board_id,
            "class_id": configuration.class_id,
            "is_active": configuration.is_active,
            "created_at": configuration.created_at,
            "updated_at": configuration.updated_at,
            "class_name": class_group.class_name if class_group else None,
            "subject_details": subject_details,
        })

    return results


@router.get(
    "/teaching-configurations/{configuration_id}",
    response_model=TeachingConfigurationDetailResponse,
)
def get_teaching_configuration(
    configuration_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_self_signed_teacher_active()),
):
    teacher = _get_teacher_profile(db, current_user.id)
    configuration = _get_teacher_configuration(db, teacher.id, configuration_id)

    class_group = db.query(SchoolClassSubject).filter(SchoolClassSubject.id == configuration.class_id).first()
    subject_rows = []
    if configuration.subject_ids:
        subject_rows = (
            db.query(SchoolClassSubject)
            .filter(SchoolClassSubject.id.in_(configuration.subject_ids))
            .all()
        )

    subject_details = [
        {"id": subject.id, "subject_name": subject.subject}
        for subject in subject_rows
    ]

    return {
        "id": configuration.id,
        "board_id": configuration.board_id,
        "class_id": configuration.class_id,
        "subject_ids": configuration.subject_ids,
        "is_active": configuration.is_active,
        "created_at": configuration.created_at,
        "updated_at": configuration.updated_at,
        "class_name": class_group.class_name if class_group else None,
        "subject_details": subject_details,
    }


@router.put(
    "/teaching-configurations/{configuration_id}",
    response_model=TeachingConfigurationResponse,
)
def update_teaching_configuration(
    configuration_id: int,
    payload: TeachingConfigurationUpdateRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_self_signed_teacher_active()),
):
    teacher = _get_teacher_profile(db, current_user.id)
    configuration = _get_teacher_configuration(db, teacher.id, configuration_id)

    update_data = payload.dict(exclude_unset=True)
    board_id = update_data.get("board_id", configuration.board_id)
    class_id = update_data.get("class_id", configuration.class_id)
    subject_ids = update_data.get("subject_ids", configuration.subject_ids)

    class_group = _get_class_group(db, class_id)
    if class_group.school_board != board_id:
        raise HTTPException(
            status_code=400,
            detail="Selected board does not match the selected class group.",
        )

    _validate_subject_ids(db, class_group, subject_ids)
    _assert_no_duplicate_configuration(
        db,
        teacher.id,
        board_id,
        class_id,
        subject_ids,
        exclude_configuration_id=configuration.id,
    )

    configuration.board_id = board_id
    configuration.class_id = class_id
    configuration.subject_ids = subject_ids
    if "is_active" in update_data:
        configuration.is_active = update_data["is_active"]

    db.commit()
    db.refresh(configuration)
    return configuration


@router.patch(
    "/teaching-configurations/{configuration_id}/activate",
    response_model=TeachingConfigurationResponse,
)
def activate_teaching_configuration(
    configuration_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_self_signed_teacher_active()),
):
    teacher = _get_teacher_profile(db, current_user.id)
    configuration = _get_teacher_configuration(db, teacher.id, configuration_id)
    configuration.is_active = True
    db.commit()
    db.refresh(configuration)
    return configuration


@router.patch(
    "/teaching-configurations/{configuration_id}/deactivate",
    response_model=TeachingConfigurationResponse,
)
def deactivate_teaching_configuration(
    configuration_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_self_signed_teacher_active()),
):
    teacher = _get_teacher_profile(db, current_user.id)
    configuration = _get_teacher_configuration(db, teacher.id, configuration_id)
    configuration.is_active = False
    db.commit()
    db.refresh(configuration)
    return configuration


@router.delete("/teaching-configurations/{configuration_id}")
def delete_teaching_configuration(
    configuration_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_self_signed_teacher_active()),
):
    teacher = _get_teacher_profile(db, current_user.id)
    configuration = _get_teacher_configuration(db, teacher.id, configuration_id)

    student_count = (
        db.query(SelfSignedStudent)
        .filter(
            SelfSignedStudent.self_signed_teacher_id == teacher.id,
            SelfSignedStudent.select_board == configuration.board_id,
            SelfSignedStudent.select_class_id == configuration.class_id,
        )
        .count()
    )
    if student_count > 0:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete configuration while students exist for the selected board and class.",
        )

    db.delete(configuration)
    db.commit()
    return {"detail": "Teaching configuration deleted successfully."}


@router.post("/self-signed-teacher/students/create", status_code=status.HTTP_201_CREATED, response_model=SelfSignedTeacherStudentResponse)
def create_student_for_self_signed_teacher(
    student_data: SelfSignedTeacherStudentCreateRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_self_signed_teacher_active()),
):
    """
    Teacher-initiated student creation following School → Student creation flow.

    Creates a new Self Sign Student with PENDING status.
    Sends verification email with account setup link to student.
    Student is linked to the teacher.
    """
    teacher = db.query(SelfSignedTeacher).filter(SelfSignedTeacher.user_id == current_user.id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher profile not found")

    # Prevent duplicates by email and phone
    _cleanup_existing_user(db, student_data.email)
    existing_phone_user = db.query(User).filter(User.phone == student_data.phone).first()
    if existing_phone_user:
        raise HTTPException(status_code=400, detail="Phone number already exists.")

    class_group = _get_class_group(db, student_data.select_class_id)
    if class_group.school_board.value != student_data.select_board:
        raise HTTPException(
            status_code=400,
            detail="Selected board does not match the selected class group.",
        )

    try:
        # ✅ Upload student profile image (if provided)
        profile_pic_url = None
        if student_data.profile_image:
            try:
                profile_pic_url = upload_base64_to_s3(
                    student_data.profile_image, 
                    f"self_signed_students/{teacher.id}/profile"
                )
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"S3 Upload failed: {str(e)}")

        # ✅ Create User for the student
        user = User(
            name=f"{student_data.first_name} {student_data.last_name}",
            email=student_data.email,
            phone=student_data.phone,
            role=UserRole.SELF_SIGNED_STUDENT
        )
        db.add(user)
        db.flush()  # ensures user.id is available

        # ✅ Create SelfSignedStudent profile with TRIAL status (1 day expiry)
        student_profile = SelfSignedStudent(
            user_id=user.id,
            first_name=student_data.first_name,
            last_name=student_data.last_name,
            gender=student_data.gender,
            dob=student_data.dob,
            student_type=student_data.student_type.value,
            phone=student_data.phone,
            email=student_data.email,
            profile_image=profile_pic_url,
            select_board=student_data.select_board,
            select_medium=student_data.select_medium,
            select_class_id=student_data.select_class_id,
            school_name=student_data.school_name,
            school_location=student_data.school_location,
            roll_number=student_data.roll_number,
            previous_school_name=(student_data.previous_school_name or student_data.school_name),
            previous_class_marks_obtained=student_data.previous_class_marks_obtained,
            previous_class_overall_percentage=student_data.previous_class_overall_percentage,
            previous_class_final_grade=student_data.previous_class_final_grade,
            pin=student_data.pin,
            division=student_data.division,
            district=student_data.district,
            state=student_data.state,
            plot=student_data.plot,
            parent_name=student_data.parent_name,
            relation=student_data.relation,
            parent_phone=student_data.parent_phone,
            parent_email=student_data.parent_email,
            occupation=student_data.occupation,
            self_signed_teacher_id=teacher.id,
            status=StudentStatus.PENDING,
            status_expiry_date=None,
        )
        db.add(student_profile)
        db.flush()  # ensures student_profile.id is available

        # ✅ Send verification email (following School Student pattern)
        email_sent = False
        email_error = None
        try:
            token = create_verification_token(user.id)
            verification_link = f"https://testapi.vidyawings.com/users/verify-account?token={token}"

            send_dynamic_email(
                context_key="account_verification.html",
                subject="Student Account Verification",
                recipient_email=user.email,
                context_data={
                    "name": f"{student_data.first_name} {student_data.last_name}",
                    "verification_link": verification_link,
                },
                db=db
            )
            email_sent = True
        except Exception as email_exception:
            # Log email error but don't fail student creation
            email_error = str(email_exception)
            print(f"Warning: Failed to send verification email to {user.email}: {email_error}")

        db.commit()
        db.refresh(user)
        db.refresh(student_profile)

        # Log action
        log_action(
            db=db,
            current_user=current_user,
            action_type=ActionType.CREATE,
            resource_type=ResourceType.STUDENT,
            resource_id=str(student_profile.id),
            description=f"Created self-signed student: {student_data.first_name} {student_data.last_name}",
            metadata={"student_id": student_profile.id, "teacher_id": teacher.id}
        )

        response = {
            "detail": "Student account created successfully." + (" Verification email sent." if email_sent else " Note: Verification email could not be sent."),
            "id": student_profile.id,
            "user_id": user.id,
            "first_name": student_profile.first_name,
            "last_name": student_profile.last_name,
            "gender": student_profile.gender,
            "student_type": student_profile.student_type,
            "email": student_profile.email,
            "phone": student_profile.phone,
            "profile_image": profile_pic_url,
            "select_board": student_profile.select_board,
            "select_medium": student_profile.select_medium,
            "select_class_id": student_profile.select_class_id,
            "school_name": student_profile.school_name,
            "school_location": student_profile.school_location,
            "dob": student_profile.dob,
            "roll_number": student_profile.roll_number,
            "previous_school_name": student_profile.previous_school_name,
            "previous_class_marks_obtained": student_profile.previous_class_marks_obtained,
            "previous_class_overall_percentage": student_profile.previous_class_overall_percentage,
            "previous_class_final_grade": student_profile.previous_class_final_grade,
            "pin": student_profile.pin,
            "division": student_profile.division,
            "district": student_profile.district,
            "state": student_profile.state,
            "plot": student_profile.plot,
            "parent_name": student_profile.parent_name,
            "relation": student_profile.relation,
            "parent_phone": student_profile.parent_phone,
            "parent_email": student_profile.parent_email,
            "occupation": student_profile.occupation,
            "status": student_profile.status,
            "status_expiry_date": student_profile.status_expiry_date,
            "created_at": student_profile.created_at,
            "email_sent": email_sent,
        }
        
        if not email_sent and email_error:
            response["email_error"] = email_error
        
        return response

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create student: {str(e)}")


@router.post("/self-signed-teacher/students/{student_id}/activate", status_code=status.HTTP_200_OK)
def activate_self_signed_teacher_student(
    student_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(UserRole.SELF_SIGNED_TEACHER)),
):
    """
    Activate a Self Sign Student to ACTIVE status (90 days expiry).
    
    Teacher can only activate their own students.
    Following School Student activation pattern.
    """
    teacher = db.query(SelfSignedTeacher).filter(SelfSignedTeacher.user_id == current_user.id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher profile not found")

    student = db.query(SelfSignedStudent).filter(
        SelfSignedStudent.id == student_id,
        SelfSignedStudent.self_signed_teacher_id == teacher.id
    ).first()
    
    if not student:
        raise HTTPException(status_code=404, detail="Student not found or not your student")

    now = datetime.now(timezone.utc)
    if student.status in [StudentStatus.PENDING, StudentStatus.TRIAL, StudentStatus.INACTIVE]:
        student.status = StudentStatus.ACTIVE
        student.status_expiry_date = now + timedelta(days=90)
    elif student.status == StudentStatus.ACTIVE:
        # Renewal: extend expiry by 90 days
        student.status_expiry_date = (student.status_expiry_date or now) + timedelta(days=90)

    db.commit()
    db.refresh(student)

    # Log action
    log_action(
        db=db,
        current_user=current_user,
        action_type=ActionType.UPDATE,
        resource_type=ResourceType.STUDENT,
        resource_id=str(student.id),
        description=f"Activated self-signed student: {student.first_name} {student.last_name}",
        metadata={"student_id": student.id, "teacher_id": teacher.id, "new_status": student.status}
    )

    return {
        "detail": f"Student activated successfully. New status: {student.status}",
        "student_id": student.id,
        "status": student.status,
        "status_expiry_date": student.status_expiry_date
    }


@router.get("/self-signed-teacher/students/{student_id}", response_model=SelfSignedTeacherStudentResponse)
def get_self_signed_teacher_student(
    student_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(UserRole.SELF_SIGNED_TEACHER)),
):
    """
    Retrieve a specific Self Sign Student details.
    
    Teacher can only view their own students.
    """
    teacher = db.query(SelfSignedTeacher).filter(SelfSignedTeacher.user_id == current_user.id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher profile not found")

    student = db.query(SelfSignedStudent).filter(
        SelfSignedStudent.id == student_id,
        SelfSignedStudent.self_signed_teacher_id == teacher.id
    ).first()
    
    if not student:
        raise HTTPException(status_code=404, detail="Student not found or not your student")

    return student


@router.post("/self-signed-teacher/students/{student_id}/deactivate", status_code=status.HTTP_200_OK)
def deactivate_self_signed_teacher_student(
    student_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(UserRole.SELF_SIGNED_TEACHER)),
):
    """
    Deactivate a Self Sign Student (set to INACTIVE status).
    
    Teacher can only deactivate their own students.
    """
    teacher = db.query(SelfSignedTeacher).filter(SelfSignedTeacher.user_id == current_user.id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher profile not found")

    student = db.query(SelfSignedStudent).filter(
        SelfSignedStudent.id == student_id,
        SelfSignedStudent.self_signed_teacher_id == teacher.id
    ).first()
    
    if not student:
        raise HTTPException(status_code=404, detail="Student not found or not your student")

    student.status = StudentStatus.INACTIVE
    db.commit()
    db.refresh(student)

    # Log action
    log_action(
        db=db,
        current_user=current_user,
        action_type=ActionType.UPDATE,
        resource_type=ResourceType.STUDENT,
        resource_id=str(student.id),
        description=f"Deactivated self-signed student: {student.first_name} {student.last_name}",
        metadata={"student_id": student.id, "teacher_id": teacher.id, "new_status": StudentStatus.INACTIVE}
    )

    return {
        "detail": "Student deactivated successfully.",
        "student_id": student.id,
        "status": student.status
    }


@router.get("/dashboard/student-summary")
def get_self_signed_teacher_student_summary(
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(UserRole.SELF_SIGNED_TEACHER)),
):
    teacher = db.query(SelfSignedTeacher).filter(SelfSignedTeacher.user_id == current_user.id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher profile not found")

    total_students = db.query(func.count(SelfSignedStudent.id)).filter(SelfSignedStudent.self_signed_teacher_id == teacher.id).scalar() or 0
    total_active = db.query(func.count(SelfSignedStudent.id)).filter(SelfSignedStudent.self_signed_teacher_id == teacher.id, SelfSignedStudent.status == StudentStatus.ACTIVE).scalar() or 0
    total_internal = db.query(func.count(SelfSignedStudent.id)).filter(
        SelfSignedStudent.self_signed_teacher_id == teacher.id,
        SelfSignedStudent.student_type == "internal",
    ).scalar() or 0
    total_external = db.query(func.count(SelfSignedStudent.id)).filter(
        SelfSignedStudent.self_signed_teacher_id == teacher.id,
        SelfSignedStudent.student_type == "external",
    ).scalar() or 0

    # Status counts
    status_counts_rows = (
        db.query(SelfSignedStudent.status, func.count(SelfSignedStudent.id))
        .filter(SelfSignedStudent.self_signed_teacher_id == teacher.id)
        .group_by(SelfSignedStudent.status)
        .all()
    )
    status_counts = {row[0]: row[1] for row in status_counts_rows}

    return {
        "total_students": total_students,
        "total_active_students": total_active,
        "total_internal_students": total_internal,
        "total_external_students": total_external,
        "student_status_counts": status_counts,
    }



@router.post("/self-signed-teacher/join/", status_code=status.HTTP_201_CREATED)
def join_self_signed_teacher_by_invite(
    join_data: SelfSignedTeacherStudentJoinRequest,
    db: Session = Depends(get_db),
):
    """Public join for students. If `invite_code` is provided the student is linked to that teacher.
    Otherwise the system will try to auto-map the student to a teacher based on active teaching configurations
    matching `select_board` + `select_class_id`.
    """
    # Basic duplicate checks
    existing_email = db.query(User).filter(User.email == join_data.email).first()
    if existing_email:
        raise HTTPException(status_code=400, detail="Email already exists")
    if join_data.phone:
        existing_phone = db.query(User).filter(User.phone == join_data.phone).first()
        if existing_phone:
            raise HTTPException(status_code=400, detail="Phone already exists")

    teacher = None
    if hasattr(join_data, "invite_code") and getattr(join_data, "invite_code"):
        teacher = db.query(SelfSignedTeacher).filter(SelfSignedTeacher.invite_code == join_data.invite_code).first()
        if not teacher:
            raise HTTPException(status_code=404, detail="Invite code is invalid")

    # Create user + profile
    user = User(
        email=join_data.email,
        phone=join_data.phone,
        name=f"{join_data.first_name} {join_data.last_name}",
        role=UserRole.SELF_SIGNED_STUDENT,
    )
    db.add(user)
    db.flush()

    # Try auto-mapping if no invite_code-provided teacher
    mapped_teacher_id = None
    if not teacher:
        mapped_teacher_id = _find_matching_self_signed_teacher(db, join_data.select_board, join_data.select_class_id)
        if mapped_teacher_id:
            teacher = db.query(SelfSignedTeacher).filter(SelfSignedTeacher.id == mapped_teacher_id).first()

    student_profile = SelfSignedStudent(
        user_id=user.id,
        first_name=join_data.first_name,
        last_name=join_data.last_name,
        phone=join_data.phone,
        email=join_data.email,
        select_board=join_data.select_board,
        select_medium=join_data.select_medium,
        select_class_id=join_data.select_class_id,
        school_name=join_data.school_name,
        school_location=join_data.school_location,
        self_signed_teacher_id=(teacher.id if teacher else None),
        status=StudentStatus.PENDING,
        status_expiry_date=None,
    )
    db.add(student_profile)

    # Send verification email (non-blocking)
    try:
        token = create_verification_token(user.id)
        verification_link = f"https://testapi.vidyawings.com/users/verify-account?token={token}"
        send_dynamic_email(
            context_key="account_verification.html",
            subject="Student Account Verification",
            recipient_email=user.email,
            context_data={"name": f"{join_data.first_name} {join_data.last_name}", "verification_link": verification_link},
            db=db,
        )
    except Exception:
        pass

    db.commit()
    return {
        "detail": "Signup initiated. Verification email sent if delivery succeeded.",
        "student_id": student_profile.id,
        "mapped_teacher_id": student_profile.self_signed_teacher_id,
    }


# @router.get("/self-signed-teacher/invite-code/")
# def get_self_signed_teacher_invite_code(
#     db: Session = Depends(get_db),
#     current_user=Depends(require_roles(UserRole.SELF_SIGNED_TEACHER)),
# ):
#     profile = db.query(SelfSignedTeacher).filter(SelfSignedTeacher.user_id == current_user.id).first()
#     if not profile:
#         raise HTTPException(status_code=404, detail="Teacher profile not found")

#     return {"invite_code": profile.invite_code}