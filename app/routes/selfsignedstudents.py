from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session,joinedload
from app.db.session import get_db
from app.models.admin import StudentAdminExamData,SchoolClassSubject,AdminExam,ExamType
from app.models.school import SchoolBoard,SchoolMedium,SchoolType
from app.schemas.students import SelfSignedStudentUpdate
from app.models.students import SelfSignedStudent
from app.core.dependencies import get_current_user
from app.models.users import User
from app.models.users import UserRole
from app.utils.permission import require_roles
router = APIRouter()
@router.get("/state-board-medium-type/", status_code=status.HTTP_200_OK)
def get_selfsigned_student_filters():
    try:
        boards = list(SchoolBoard)
        mediums = list(SchoolMedium)
        types = list(SchoolType)

        return {
            "boards": [b.value for b in boards],
            "mediums": [m.value for m in mediums],
            "types": [t.value for t in types]
        }
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.put("/profile/", status_code=status.HTTP_200_OK)
def update_self_signed_student_profile(
    update_data: SelfSignedStudentUpdate,
    db: Session = Depends(get_db),
    current_user = Depends(require_roles(UserRole.SELF_SIGNED_STUDENT))
):
    try:
        # Fetch student profile using user email
        profile = db.query(SelfSignedStudent).filter(
            SelfSignedStudent.email == current_user.email
        ).first()

        if not profile:
            raise HTTPException(status_code=404, detail="Student profile not found")

        update_fields = update_data.dict(exclude_unset=True)

        # Update profile and sync user table fields if needed
        for key, value in update_fields.items():
            setattr(profile, key, value)

            # Sync phone & email to User table
            if key == "phone":
                current_user.phone = value
            elif key == "email":
                current_user.email = value

        db.commit()
        db.refresh(profile)
        db.refresh(current_user)

        return {
            "message": "Profile updated successfully."
        }

    except HTTPException:
        raise  # re-raise FastAPI errors

    except Exception as e:
        db.rollback()  # undo any partial updates
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update profile: {str(e)}"
        )
@router.get("/profile/")
def get_self_signed_student_profile(
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(UserRole.SELF_SIGNED_STUDENT))
):
    try:
        profile = db.query(SelfSignedStudent).filter(
            SelfSignedStudent.user_id == current_user.id
        ).first()

        if not profile:
            raise HTTPException(status_code=404, detail="Student profile not found")

        # ✅ Get class details using select_class_id
        class_details = None
        if profile.select_class_id:
            class_details = db.query(SchoolClassSubject).filter(
                SchoolClassSubject.id == profile.select_class_id
            ).first()

        # ✅ Get latest exam rank
        latest_exam_rank = (
            db.query(StudentAdminExamData)
            .filter(StudentAdminExamData.student_id == profile.id)
            .order_by(StudentAdminExamData.submitted_at.desc())
            .first()
        )

        latest_rank = (
            latest_exam_rank.class_rank
            if latest_exam_rank
            else None
        )

        return {
            "id": current_user.id,
            "role": current_user.role,
            "profile_image": profile.profile_image,
            "first_name": profile.first_name,
            "last_name": profile.last_name,
            "email": current_user.email,
            "phone": current_user.phone,

            # ✅ Now coming from SchoolClassSubject table
            "board": class_details.school_board.value if class_details else None,
            "class": class_details.class_name if class_details else None,
            "medium": class_details.school_medium.value if class_details else None,

            "pin": profile.pin,
            "division": profile.division,
            "district": profile.district,
            "state": profile.state,
            "plot": profile.plot,
            "school_name": profile.school_name,
            "school_location": profile.school_location,
            "status": profile.status,
            "status_expiry_date": profile.status_expiry_date,

            "parent_name": profile.parent_name,
            "relation": profile.relation,
            "parent_phone": profile.parent_phone,
            "parent_email": profile.parent_email,
            "occupation": profile.occupation,

            "created_at": current_user.created_at,
            "class_rank": latest_rank,
        }

    except HTTPException:
        raise
    except Exception as e:
        print("Error fetching student profile:", e)
        raise HTTPException(
            status_code=500,
            detail="Something went wrong while fetching the profile."
        )

@router.get("/exam-summary")
def get_student_exam_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # ✅ Only self signed students allowed
    if current_user.role != UserRole.SELF_SIGNED_STUDENT:
        raise HTTPException(
            status_code=403,
            detail="Only self signed students can access this."
        )

    student = db.query(SelfSignedStudent).filter(
        SelfSignedStudent.user_id == current_user.id
    ).first()

    if not student:
        raise HTTPException(status_code=404, detail="Student profile not found.")

    # ✅ Get all exams attempted by student
    student_exam_data = (
        db.query(StudentAdminExamData)
        .join(AdminExam, StudentAdminExamData.exam_id == AdminExam.id)
        .filter(StudentAdminExamData.student_id == student.id)
        .all()
    )

    mock_tests_given = 0
    rank_tests_given = 0
    rank_test_details = []

    for exam_data in student_exam_data:
        if exam_data.exam.exam_type == ExamType.mock:
            mock_tests_given += 1

        elif exam_data.exam.exam_type == ExamType.rank:
            rank_tests_given += 1

            rank_test_details.append({
                "exam_id": exam_data.exam.id,
                "exam_name": exam_data.exam.name,
                "class_rank": exam_data.class_rank,
                "result": exam_data.result
            })

    return {
        "student_id": student.id,
        "mock_tests_given": mock_tests_given,
        "rank_tests_given": rank_tests_given,
        "rank_test_details": rank_test_details
    }