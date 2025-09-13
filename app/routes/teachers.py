from fastapi import APIRouter, Depends, HTTPException, status
from app.core.dependencies import get_current_user
from app.models.users import User, Otp
from app.models.teachers import Teacher,TeacherClassSectionSubject
from app.models.school import School,Attendance,Class,Section,Subject,Exam
from app.schemas.users import UserRole
from app.schemas.teachers import TeacherCreateRequest,TeacherResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.utils.email_utility import generate_otp
from datetime import datetime, timedelta
from typing import List
from sqlalchemy import func
from app.core.security import create_verification_token
from app.utils.email_utility import send_dynamic_email
router = APIRouter()


@router.post("/create-teacher/", status_code=status.HTTP_201_CREATED)
def create_teacher(
    data: TeacherCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != UserRole.SCHOOL:
        raise HTTPException(status_code=403, detail="Only schools can create teachers.")
    
    if db.query(User).filter(User.email == data.email).first():
        raise HTTPException(status_code=400, detail="Email already exists.")

    school = db.query(School).filter(School.user_id == current_user.id).first()
    if not school:
        raise HTTPException(status_code=400, detail="School profile not found.")

    try:
        # No need to use 'with db.begin()' here
        user = User(
            name=f"{data.first_name} {data.last_name}",
            email=data.email,
            phone=current_user.phone,
            location=current_user.location,
            website=current_user.website,
            role=UserRole.TEACHER
        )
        db.add(user)
        db.flush()  # This assigns user.id

        teacher = Teacher(
            first_name=data.first_name,
            last_name=data.last_name,
            highest_qualification=data.highest_qualification,
            university=data.university,
            phone=data.phone,
            email=data.email,
            teacher_in_classes=data.teacher_in_classes,
            subjects=data.subjects,
            start_duty=data.start_duty,
            end_duty=data.end_duty,
            teacher_type=data.teacher_type,
            present_in=data.present_in,
            school_id=school.id,
            user_id=user.id
        )
        db.add(teacher)
        db.flush()  # Assigns teacher.id

        assignments = [
            TeacherClassSectionSubject(
                teacher_id=teacher.id,
                class_id=item.class_id,
                section_id=item.section_id,
                subject_id=item.subject_id,
                school_id=school.id,
            )
            for item in data.assignments
        ]
        db.bulk_save_objects(assignments)

        db.commit()
        token = create_verification_token(user.id)
        verification_link = f"http://127.0.0.1:8000/users/verify-account?token={token}"
        send_dynamic_email(
            context_key="account_verification.html",
            subject="Teacher Account Verification",
            recipient_email=user.email,
            context_data={
                "name": f"{data.first_name} {data.last_name}",
                "verification_link": verification_link,
            },
            db=db
        )
        return {
            "detail": "Teacher account created. Verification email sent.",
            "teacher_id": teacher.id,
            "user_id": user.id,
        }

    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/all-teacher/")
def get_all_teachers_for_school(
    limit: int = 10,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != UserRole.SCHOOL:
        raise HTTPException(status_code=403, detail="Only schools can access this resource.")

    school = db.query(School).filter(School.user_id == current_user.id).first()
    if not school:
        raise HTTPException(status_code=404, detail="School profile not found.")
    # Subquery to get attendance count
    attendance_subq = (
        db.query(
            Attendance.teachers_id,
            func.count(Attendance.id).label("attendance_count")
        )
        .group_by(Attendance.teachers_id)
        .subquery()
    )
    # Subquery for exam count
    exam_subq = (
        db.query(
            Exam.created_by.label("teacher_id"),
            func.count(Exam.id).label("exam_count")
        )
        .group_by(Exam.created_by)
        .subquery()
    )
    teachers_query = (
        db.query(
            Teacher,
            attendance_subq.c.attendance_count,
            exam_subq.c.exam_count
        )
        .outerjoin(attendance_subq, Teacher.id == attendance_subq.c.teachers_id)
        .outerjoin(exam_subq, Teacher.id == exam_subq.c.teacher_id)
        .filter(Teacher.school_id == school.id)
        .offset(offset)
        .limit(limit)
        .all()
    )

    return [
        {
            "sl_no": index + 1 + offset,
            "teacher_id": teacher.id,
            "teacher_name": f"{teacher.first_name} {teacher.last_name}",
            "email": teacher.email,
            "status": "active" if teacher.is_active else "inactive",
            "classes":len(teacher.teacher_in_classes) if teacher.teacher_in_classes else 0,
            "subjects": len(teacher.subjects),
            "attendance_count": attendance_count or 0,
            "exam_count": exam_count or 0
        }
        for index, (teacher,attendance_count,exam_count) in enumerate(teachers_query)
    ]
    
@router.get("/teacher/profile")
def get_teacher_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != UserRole.TEACHER:
        raise HTTPException(status_code=403, detail="Only teachers can access their profile.")

    teacher = db.query(Teacher).filter(Teacher.user_id == current_user.id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher profile not found.")

    assignments = (
        db.query(TeacherClassSectionSubject)
        .filter(TeacherClassSectionSubject.teacher_id == teacher.id)
        .all()
    )

    # Build detailed assignment info
    detailed_assignments = []
    for a in assignments:
        detailed_assignments.append({
            "class_id": a.class_id,
            "class_name": a.class_.name if a.class_ else None,
            "section_id": a.section_id,
            "section_name": a.section.name if a.section else None,
            "subject_id": a.subject_id,
            "subject_name": a.subject.name if a.subject else None,
        })

    return {
        "id": teacher.id,
        "name": f"{teacher.first_name} {teacher.last_name}",
        "email": teacher.email,
        "phone": teacher.phone,
        "created_at": teacher.created_at,
        "assignments": detailed_assignments,
        "status": "active" if teacher.is_active else "inactive"
    }    

@router.get("/teacher/{teacher_id}")
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

    assignments = (
        db.query(TeacherClassSectionSubject)
        .filter(TeacherClassSectionSubject.teacher_id == teacher.id)
        .all()
    )

    # Build detailed assignment info
    detailed_assignments = []
    for a in assignments:
        detailed_assignments.append({
            "class_id": a.class_id,
            "class_name": a.class_.name if a.class_ else None,
            "section_id": a.section_id,
            "section_name": a.section.name if a.section else None,
            "subject_id": a.subject_id,
            "subject_name": a.subject.name if a.subject else None,
        })

    return {
        "id": teacher.id,
        "name": f"{teacher.first_name} {teacher.last_name}",
        "email": teacher.email,
        "phone": teacher.phone,
        "status": "active" if teacher.is_active else "inactive",
        "created_at": teacher.created_at,
        "assignments": detailed_assignments
    }

@router.put("/teacher/{teacher_id}/inactive")
def inactive_teacher(
    teacher_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Only school users can perform this action
    if current_user.role != UserRole.SCHOOL:
        raise HTTPException(status_code=403, detail="Only schools can perform this action.")

    # Get current user's school profile
    school = db.query(School).filter(School.user_id == current_user.id).first()
    if not school:
        raise HTTPException(status_code=404, detail="School profile not found.")

    # Fetch teacher by ID within the same school
    teacher = db.query(Teacher).filter(
        Teacher.id == teacher_id,
        Teacher.school_id == school.id
    ).first()

    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher not found or doesn't belong to your school.")

    # Mark teacher as inactive
    teacher.is_active = False
    db.commit()
    db.refresh(teacher)

    return {
        "detail": "Teacher has been marked as inactive successfully.",
        "teacher_id": teacher.id,
        "status": "inactive"
    }


@router.get("/classes")
def get_teacher_classes(
    current_user: User = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    if current_user.role != UserRole.TEACHER:
        raise HTTPException(status_code=403, detail="Only teachers can access this resource.")

    teacher = db.query(Teacher).filter(Teacher.user_id == current_user.id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher not found")

    # Sirf assigned classes nikalna
    assignments = db.query(TeacherClassSectionSubject).filter(
        TeacherClassSectionSubject.teacher_id == teacher.id
    ).all()

    class_ids = {a.class_id for a in assignments}
    classes = db.query(Class).filter(Class.id.in_(class_ids)).all()

    return [{"id": c.id, "name": c.name} for c in classes]

@router.get("/sections")
def get_teacher_sections(
    current_user: User = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    if current_user.role != UserRole.TEACHER:
        raise HTTPException(status_code=403, detail="Only teachers can access this resource.")

    teacher = db.query(Teacher).filter(Teacher.user_id == current_user.id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher not found")

    assignments = db.query(TeacherClassSectionSubject).filter(
        TeacherClassSectionSubject.teacher_id == teacher.id
    ).all()

    section_ids = {a.section_id for a in assignments}
    sections = db.query(Section).filter(Section.id.in_(section_ids)).all()

    return [{"id": s.id, "name": s.name} for s in sections]

@router.get("/subjects")
def get_teacher_subjects(
    current_user: User = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    if current_user.role != UserRole.TEACHER:
        raise HTTPException(status_code=403, detail="Only teachers can access this resource.")

    teacher = db.query(Teacher).filter(Teacher.user_id == current_user.id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher not found")

    assignments = db.query(TeacherClassSectionSubject).filter(
        TeacherClassSectionSubject.teacher_id == teacher.id
    ).all()

    subject_ids = {a.subject_id for a in assignments}
    subjects = db.query(Subject).filter(Subject.id.in_(subject_ids)).all()

    return [{"id": sub.id, "name": sub.name} for sub in subjects]