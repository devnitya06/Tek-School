from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session,joinedload
from app.db.session import get_db
from app.models.admin import StudentAdminExamData
from app.models.school import SchoolBoard,SchoolMedium,SchoolType
from app.schemas.students import SelfSignedStudentUpdate
from app.models.students import SelfSignedStudent
from app.core.dependencies import get_current_user
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
    current_user = Depends(require_roles(UserRole.STUDENT))
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
    current_user=Depends(require_roles(UserRole.STUDENT))
):
    try:
        # Ensure user is a student (additional check for safety)
        if current_user.role != "student":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only students can view this profile."
            )

        # Fetch student details mapped to user record
        profile = db.query(SelfSignedStudent).filter(
            SelfSignedStudent.user_id == current_user.id
        ).first()

        if not profile:
            raise HTTPException(status_code=404, detail="Student profile not found")
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
            "board": profile.select_board,
            "class": profile.select_class,
            "medium": profile.select_medium,
            "pin": profile.pin,
            "division": profile.division,
            "district": profile.district,
            "state": profile.state,
            "plot": profile.plot,
            "school_name": profile.school_name,
            "school_location": profile.school_location,
            "status": profile.status,
            "status_expiry_date": profile.status_expiry_date,
            "parenrt_name": profile.parent_name,
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