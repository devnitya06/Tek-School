from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone

from app.db.session import get_db
from app.models.users import User, Otp
from app.models.students import SelfSignedStudent, StudentStatus
from app.models.teachers import SelfSignedTeacher, VerificationStatus, ProfileStatus
from app.schemas.users import UserRole
from app.schemas.selfsignedteachers import (
    SelfSignedTeacherProfileUpdate,
    SelfSignedTeacherProfileResponse,
    VerificationStatusResponse,
    SelfSignedTeacherStudentCreateRequest,
    SelfSignedTeacherStudentJoinRequest,
    SelfSignedTeacherStudentResponse,
    SelfSignedTeacherStudentUpdateRequest,
)
from app.utils.email_utility import generate_otp, send_dynamic_email
from app.utils.permission import require_roles
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

    return profile


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
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(UserRole.SELF_SIGNED_TEACHER)),
):
    teacher = db.query(SelfSignedTeacher).filter(SelfSignedTeacher.user_id == current_user.id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher profile not found")

    students = (
        db.query(SelfSignedStudent)
        .filter(SelfSignedStudent.self_signed_teacher_id == teacher.id)
        .all()
    )

    return [
        {
            "id": student.id,
            "first_name": student.first_name,
            "last_name": student.last_name,
            "email": student.email,
            "phone": student.phone,
            "status": student.status,
            "created_at": student.created_at,
        }
        for student in students
    ]


@router.post("/self-signed-teacher/students/create", status_code=status.HTTP_201_CREATED, response_model=SelfSignedTeacherStudentResponse)
def create_student_for_self_signed_teacher(
    student_data: SelfSignedTeacherStudentCreateRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(UserRole.SELF_SIGNED_TEACHER)),
):
    """
    Teacher-initiated student creation following School → Student creation flow.
    
    Creates a new Self Sign Student with TRIAL status (1 day expiry).
    Sends verification email to student.
    Student is linked to the teacher.
    """
    teacher = db.query(SelfSignedTeacher).filter(SelfSignedTeacher.user_id == current_user.id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher profile not found")

    _cleanup_existing_user(db, student_data.email)

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
            phone=student_data.phone,
            email=student_data.email,
            profile_image=profile_pic_url,
            select_board=student_data.select_board,
            select_medium=student_data.select_medium,
            select_class_id=student_data.select_class_id,
            school_name=student_data.school_name,
            school_location=student_data.school_location,
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
            status=StudentStatus.TRIAL,
            status_expiry_date=datetime.utcnow() + timedelta(days=1)
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
            "email": student_profile.email,
            "phone": student_profile.phone,
            "profile_image": profile_pic_url,
            "select_board": student_profile.select_board,
            "select_medium": student_profile.select_medium,
            "select_class_id": student_profile.select_class_id,
            "school_name": student_profile.school_name,
            "school_location": student_profile.school_location,
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
    if student.status in [StudentStatus.TRIAL, StudentStatus.INACTIVE]:
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


@router.put("/self-signed-teacher/students/{student_id}", response_model=SelfSignedTeacherStudentResponse)
def update_self_signed_teacher_student(
    student_id: int,
    update_data: SelfSignedTeacherStudentUpdateRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(UserRole.SELF_SIGNED_TEACHER)),
):
    """
    Update a Self Sign Student profile.
    
    Teacher can only update their own students.
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

    try:
        updated_fields = update_data.dict(exclude_unset=True)
        
        # Handle profile image upload
        if "profile_image" in updated_fields and updated_fields["profile_image"]:
            try:
                profile_pic_url = upload_base64_to_s3(
                    updated_fields["profile_image"], 
                    f"self_signed_students/{teacher.id}/profile"
                )
                updated_fields["profile_image"] = profile_pic_url
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"S3 Upload failed: {str(e)}")
        
        # Update phone and name in User table
        if "phone" in updated_fields:
            student.user.phone = updated_fields["phone"]
        
        if "first_name" in updated_fields or "last_name" in updated_fields:
            first_name = updated_fields.get("first_name", student.first_name)
            last_name = updated_fields.get("last_name", student.last_name)
            student.user.name = f"{first_name} {last_name}"
        
        # Update student profile fields
        for key, value in updated_fields.items():
            if key not in ["profile_image"]:  # profile_image already handled
                setattr(student, key, value)

        db.commit()
        db.refresh(student)

        # Log action
        log_action(
            db=db,
            current_user=current_user,
            action_type=ActionType.UPDATE,
            resource_type=ResourceType.STUDENT,
            resource_id=str(student.id),
            description=f"Updated self-signed student profile: {student.first_name} {student.last_name}",
            metadata={"student_id": student.id, "teacher_id": teacher.id, "fields_updated": list(updated_fields.keys())}
        )

        return student

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update student: {str(e)}")


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



# @router.post("/self-signed-teacher/join/", status_code=status.HTTP_201_CREATED)
# def join_self_signed_teacher_by_invite(
#     join_data: SelfSignedTeacherStudentJoinRequest,
#     db: Session = Depends(get_db),
# ):
#     teacher = db.query(SelfSignedTeacher).filter(SelfSignedTeacher.invite_code == join_data.invite_code).first()
#     if not teacher:
#         raise HTTPException(status_code=404, detail="Invite code is invalid")

#     _cleanup_existing_user(db, join_data.email)

#     user = User(
#         email=join_data.email,
#         phone=join_data.phone,
#         name=f"{join_data.first_name} {join_data.last_name}",
#         role=UserRole.SELF_SIGNED_STUDENT,
#     )
#     db.add(user)
#     db.flush()

#     student_profile = SelfSignedStudent(
#         user_id=user.id,
#         first_name=join_data.first_name,
#         last_name=join_data.last_name,
#         phone=join_data.phone,
#         email=join_data.email,
#         select_board=join_data.select_board,
#         select_medium=join_data.select_medium,
#         select_class_id=join_data.select_class_id,
#         school_name=join_data.school_name,
#         school_location=join_data.school_location,
#         self_signed_teacher_id=teacher.id,
#         status_expiry_date=datetime.utcnow() + timedelta(days=1),
#     )
#     db.add(student_profile)

#     otp = generate_otp()
#     otp_entry = Otp(user_id=user.id, otp=otp)
#     db.add(otp_entry)

#     send_dynamic_email(
#         context_key="otp_verify.html",
#         subject="Your OTP Code",
#         recipient_email=user.email,
#         context_data={"email": user.email, "OTP": otp},
#         db=db,
#     )

#     db.commit()
#     return {
#         "detail": "Signup initiated. OTP sent to your email.",
#         "student_id": student_profile.id,
#         "teacher_id": teacher.id,
#     }


# @router.get("/self-signed-teacher/invite-code/")
# def get_self_signed_teacher_invite_code(
#     db: Session = Depends(get_db),
#     current_user=Depends(require_roles(UserRole.SELF_SIGNED_TEACHER)),
# ):
#     profile = db.query(SelfSignedTeacher).filter(SelfSignedTeacher.user_id == current_user.id).first()
#     if not profile:
#         raise HTTPException(status_code=404, detail="Teacher profile not found")

#     return {"invite_code": profile.invite_code}