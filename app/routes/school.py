from fastapi import APIRouter, Depends, HTTPException,status
from app.models.users import User
from app.models.teachers import Teacher
from app.models.school import School
from app.schemas.users import UserRole
from app.schemas.school import SchoolProfileOut,SchoolProfileUpdate,ClassOut,ClassInput
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.core.dependencies import get_current_user
router = APIRouter()
@router.patch("/school-profile", response_model=SchoolProfileOut)
async def update_school_profile(
    profile_data: SchoolProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Verify user is a school
    if current_user.role != UserRole.SCHOOL:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only school users can update school profiles"
        )
    
    # Get profile (should always exist after signup)
    profile = db.query(School).filter(
        School.user_id == current_user.id
    ).first()
    
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="School profile not found"
        )
    
    # Update fields
    update_data = profile_data.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(profile, field, value)
    
    # Sync critical fields with User table
    if 'school_name' in update_data:
        current_user.name = update_data['school_name']
    if 'school_email' in update_data:
        current_user.email = update_data['school_email']
    if 'school_phone' in update_data:
        current_user.phone = update_data['school_phone']
    
    db.add(profile)
    db.add(current_user)
    db.commit()
    db.refresh(profile)
    
    return profile

@router.get("/school", response_model=SchoolProfileOut)
async def get_school_profile(
    current_user: User = Depends(get_current_user)
):
    if current_user.role != UserRole.SCHOOL:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only school users can view school profiles"
        )    
    if not current_user.school_profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="School profile not found"
        )
    
    # Convert SQLAlchemy model to dict with proper field mapping
    school = current_user.school_profile
    profile_data = {
        "id": school.id,
        "user_id": school.user_id,
        "school_name": school.school_name,
        "school_type": school.school_type.value if school.school_type else None,
        "school_medium": school.school_medium.value if school.school_medium else None,
        "school_board": school.school_board.value if school.school_board else None,
        "establishment_year": school.establishment_year,
        "pin_code": school.pin_code,
        "block_division": school.block_division,
        "district": school.district,
        "state": school.state,
        "country": school.country,
        "school_email": school.school_email,
        "school_phone": school.school_phone,
        "school_alt_phone": school.school_alt_phone,
        "school_website": school.school_website,
        "principal_name": school.principal_name,
        "principal_designation": school.principal_designation,
        "principal_email": school.principal_email,
        "principal_phone": school.principal_phone
    }
    
    # Manually validate against the schema
    return SchoolProfileOut(**profile_data)

@router.post("/create-class/")
def create_class(
    data: ClassInput,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)):
    
    if current_user.role != UserRole.SCHOOL:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only school users can create classes"
        )
    created_classes = []

    # Ensure all subjects exist or create them
    def get_or_create_subject(name):
        subject = db.query(Subject).filter_by(name=name).first()
        if not subject:
            subject = Subject(name=name)
            db.add(subject)
            db.commit()
            db.refresh(subject)
        return subject

    def get_or_create_curriculum(name):
        ec = db.query(ExtraCurriculum).filter_by(name=name).first()
        if not ec:
            ec = ExtraCurriculum(name=name)
            db.add(ec)
            db.commit()
            db.refresh(ec)
        return ec

    mandatory_subjects = [get_or_create_subject(name) for name in data.mandatory_subjects]
    optional_subjects = [get_or_create_subject(name) for name in data.optional_subjects]
    extra_curriculums = [get_or_create_curriculum(name) for name in data.extra_curriculums]

    # Get teacher objects
    teachers = db.query(Teacher).filter(Teacher.id.in_(data.teacher_ids)).all()
    if len(teachers) != len(data.teacher_ids):
        raise HTTPException(status_code=400, detail="One or more teacher IDs are invalid.")

    for section in data.sections:
        new_class = Class(
            class_name=data.class_name,
            section=section,
            start_time=data.start_time,
            end_time=data.end_time,
            mandatory_subjects=mandatory_subjects,
            optional_subjects=optional_subjects,
            extra_curriculums=extra_curriculums,
            assigned_teachers=teachers
        )
        db.add(new_class)
        created_classes.append(new_class)

    db.commit()
    return {"message": "Classes created", "count": len(created_classes)}

# @router.post("/add-class", response_model=ClassOut)
# def create_class(
#     class_data: ClassCreate,
#     current_user: User = Depends(get_current_user),
#     db: Session = Depends(get_db)):
    
#     if current_user.role != UserRole.SCHOOL:
#         raise HTTPException(
#             status_code=status.HTTP_403_FORBIDDEN,
#             detail="Only school users can create classes"
#         )
#     # Validate and fetch related entities
#     mandatory_subjects = db.query(Subject).filter(Subject.id.in_(class_data.mandatory_subject_ids)).all()
#     optional_subjects = db.query(Subject).filter(Subject.id.in_(class_data.optional_subject_ids)).all()
#     extras = db.query(ExtraCurriculum).filter(ExtraCurriculum.id.in_(class_data.extra_curriculum_ids)).all()
#     teachers = db.query(Teacher).filter(Teacher.id.in_(class_data.teacher_ids)).all()

#     # Create class object
#     new_class = Class(
#         class_name=class_data.class_name,
#         section=class_data.section,
#         start_time=class_data.start_time,
#         end_time=class_data.end_time,
#         mandatory_subjects=mandatory_subjects,
#         optional_subjects=optional_subjects,
#         extra_curriculums=extras,
#         assigned_teachers=teachers
#     )

#     db.add(new_class)
#     db.commit()
#     db.refresh(new_class)
#     return new_class