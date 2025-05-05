from fastapi import APIRouter, Depends, HTTPException, status
from app.core.dependencies import get_current_user
from app.models.users import User, Otp
from app.models.teachers import Teacher
from app.models.school import School
from app.schemas.users import UserRole
from app.schemas.teachers import TeacherCreateRequest,TeacherResponse
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.utils.email_utility import generate_otp
from datetime import datetime, timedelta
from typing import List

router = APIRouter()

@router.post("/create-teacher/")
def create_teacher(
    data: TeacherCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != UserRole.SCHOOL:
        raise HTTPException(status_code=403, detail="Only schools can create teachers.")
    
    # Ensure email doesn't already exist
    existing = db.query(User).filter(User.email == data.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already exists.")
    
    # Get the school profile for the current user
    school = db.query(School).filter(School.user_id == current_user.id).first()
    if not school:
        raise HTTPException(status_code=400, detail="School profile not found.")

    # Step 1: Create User for the teacher
    user = User(
        name=current_user.name,
        location=current_user.location,
        phone=current_user.phone,
        website=current_user.website,
        email=data.email,
        role=UserRole.TEACHER
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # Step 2: Create Teacher profile with reference to new user
    teacher = Teacher(
        **data.dict(exclude={"email"}),
        email=data.email,
        school_id=school.id,
        user_id=user.id
    )
    db.add(teacher)
    db.commit()
    db.refresh(teacher)

    # Step 3: Generate and save OTP for user
    otp = generate_otp()
    otp_entry = Otp(
        user_id=user.id,
        otp=otp
    )
    db.add(otp_entry)
    db.commit()

    # Step 4: Send OTP (email utility)
    # send_otp_email(user.email, otp)

    return {"message": "OTP sent to teacher's email for verification"}

@router.get("/all-teacher/",response_model=List[TeacherResponse])
def get_all_teachers_for_school(
    limit: int = 10,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != UserRole.SCHOOL:
        raise HTTPException(status_code=403, detail="Only schools can access this resource.")
    # print("my school id😊",current_user.school_profile.id)

    school = db.query(School).filter(School.user_id == current_user.id).first()
    if not school:
        raise HTTPException(status_code=404, detail="School profile not found.")

    teachers = (
        db.query(Teacher)
        .filter(Teacher.school_id == school.id)
        .offset(offset)
        .limit(limit)
        .all()
    )
    return teachers

@router.get("/teacher/{teacher_id}", response_model=TeacherResponse)
def get_teacher_by_id(
    teacher_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != UserRole.SCHOOL:
        raise HTTPException(status_code=403, detail="Only schools can access this resource.")

    school = db.query(School).filter(School.user_id == current_user.id).first()
    if not school:
        raise HTTPException(status_code=404, detail="School profile not found.")

    teacher = db.query(Teacher).filter(
        Teacher.id == teacher_id,
        Teacher.school_id == school.id
    ).first()

    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher not found or doesn't belong to your school.")

    return teacher


