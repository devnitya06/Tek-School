from fastapi import APIRouter, Depends, HTTPException, status,Query
from app.core.dependencies import get_current_user
from app.models.users import User, Otp
from app.models.teachers import Teacher,TeacherClassSectionSubject
from app.models.school import School,Attendance,Class,Section,Subject,Exam,class_subjects
from app.models.staff import Staff
from app.schemas.users import UserRole
from app.schemas.teachers import TeacherCreateRequest,TeacherResponse,TeacherUpdateRequest
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.utils.email_utility import generate_otp
from datetime import datetime, timedelta
from typing import List
from sqlalchemy import func
from app.core.security import create_verification_token
from app.utils.email_utility import send_dynamic_email
from app.utils.s3 import upload_base64_to_s3
from app.services.pagination import PaginationParams
from app.utils.staff_logging import log_action
from app.models.staff import ActionType, ResourceType
from app.models.admin import Chapter
router = APIRouter()


@router.post("/create-teacher/", status_code=status.HTTP_201_CREATED)
def create_teacher(
    data: TeacherCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # ✅ Allow both school and staff users
    if current_user.role not in [UserRole.SCHOOL, UserRole.STAFF]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only school and staff users can create teachers."
        )
    
    if db.query(User).filter(User.email == data.email).first():
        raise HTTPException(status_code=400, detail="Email already exists.")

    # ✅ Get school based on user role
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
            raise HTTPException(status_code=404, detail="School not found for this staff member.")

    try:
        # Upload teacher profile image if provided
        profile_pic_url = None
        if data.profile_image:
            try:
                profile_pic_url = upload_base64_to_s3(data.profile_image, f"schools/{school.id}/teachers/profile")
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"S3 Upload failed: {str(e)}")

        # Create User
        user = User(
            name=f"{data.first_name} {data.last_name}",
            email=data.email,
            phone=data.phone,
            location=current_user.location,
            website=current_user.website,
            role=UserRole.TEACHER
        )
        db.add(user)
        db.flush()  # assigns user.id

        # Create Teacher
        teacher = Teacher(
            first_name=data.first_name,
            last_name=data.last_name,
            highest_qualification=data.highest_qualification,
            university=data.university,
            phone=data.phone,
            email=data.email,
            start_duty=data.start_duty,
            end_duty=data.end_duty,
            teacher_type=data.teacher_type,
            present_in=data.present_in,
            school_id=school.id,
            user_id=user.id,
            profile_image=profile_pic_url 
        )
        db.add(teacher)
        db.flush()  # assigns teacher.id

        # Teacher assignments
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
        db.refresh(user)
        db.refresh(teacher)

        # Send verification email
        token = create_verification_token(user.id)
        verification_link = f"https://tek-school.learningmust.com/users/verify-account?token={token}"
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

        # Log action
        log_action(
            db=db,
            current_user=current_user,
            action_type=ActionType.CREATE,
            resource_type=ResourceType.TEACHER,
            resource_id=teacher.id,
            description=f"Created teacher: {data.first_name} {data.last_name}",
            metadata={"teacher_id": teacher.id, "email": data.email}
        )

        return {
            "detail": "Teacher account created. Verification email sent.",
            "teacher_id": teacher.id,
        }

    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@router.get("/all-teacher/")
def get_all_teachers_for_school(
    pagination: PaginationParams = Depends(),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
    teacher_name: str | None = Query(None, description="Filter by teacher name"),
    teacher_id: str | None = Query(None, description="Filter by teacher ID"),
    class_name: str | None = Query(None, description="Filter by class name"),
    section_name: str | None = Query(None, description="Filter by section name"),
    subject_name: str | None = Query(None, description="Filter by subject name"),
):
    # ✅ Allow both school and staff users
    if current_user.role not in [UserRole.SCHOOL, UserRole.STAFF]:
        raise HTTPException(status_code=403, detail="Only schools and staff can access this resource.")

    # ✅ Get school based on user role
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
            raise HTTPException(status_code=404, detail="School not found for this staff member.")

    # --- Subqueries ---
    attendance_subq = (
        db.query(
            Attendance.teachers_id,
            func.count(Attendance.id).label("attendance_count")
        )
        .group_by(Attendance.teachers_id)
        .subquery()
    )

    exam_subq = (
        db.query(
            Exam.created_by.label("teacher_id"),
            func.count(Exam.id).label("exam_count")
        )
        .group_by(Exam.created_by)
        .subquery()
    )

    assignment_subq = (
        db.query(
            TeacherClassSectionSubject.teacher_id,
            func.count(func.distinct(TeacherClassSectionSubject.class_id)).label("class_count"),
            func.count(func.distinct(TeacherClassSectionSubject.subject_id)).label("subject_count")
        )
        .group_by(TeacherClassSectionSubject.teacher_id)
        .subquery()
    )

    # --- Base Query ---
    base_query = (
        db.query(
            Teacher,
            attendance_subq.c.attendance_count,
            exam_subq.c.exam_count,
            assignment_subq.c.class_count,
            assignment_subq.c.subject_count,
        )
        .outerjoin(attendance_subq, Teacher.id == attendance_subq.c.teachers_id)
        .outerjoin(exam_subq, Teacher.id == exam_subq.c.teacher_id)
        .outerjoin(assignment_subq, Teacher.id == assignment_subq.c.teacher_id)
        .filter(Teacher.school_id == school.id)
    )

    # --- Apply Filters ---
    if teacher_id is not None:
        base_query = base_query.filter(Teacher.id == teacher_id)

    if teacher_name:
        base_query = base_query.filter(
            func.concat(Teacher.first_name, " ", Teacher.last_name).ilike(f"%{teacher_name}%")
        )

    if class_name or section_name or subject_name:
        base_query = (
            base_query.join(
                TeacherClassSectionSubject,
                Teacher.id == TeacherClassSectionSubject.teacher_id
            )
            .join(Class, TeacherClassSectionSubject.class_id == Class.id)
            .join(Section, TeacherClassSectionSubject.section_id == Section.id)
            .join(Subject, TeacherClassSectionSubject.subject_id == Subject.id)
        )

        if class_name:
            base_query = base_query.filter(Class.name.ilike(f"%{class_name}%"))

        if section_name:
            base_query = base_query.filter(Section.name.ilike(f"%{section_name}%"))

        if subject_name:
            base_query = base_query.filter(Subject.name.ilike(f"%{subject_name}%"))

    # --- Count & Pagination ---
    total_count = base_query.count()
    teachers = base_query.offset(pagination.offset()).limit(pagination.limit()).all()

    # --- Format Response ---
    data = [
        {
            "sl_no": index + 1 + pagination.offset(),
            "teacher_id": teacher.id,
            "teacher_name": f"{teacher.first_name} {teacher.last_name}",
            "email": teacher.email,
            "status": "active" if teacher.is_active else "inactive",
            "attendance_count": attendance_count or 0,
            "exam_count": exam_count or 0,
            "class_count": class_count or 0,
            "subject_count": subject_count or 0,
        }
        for index, (teacher, attendance_count, exam_count, class_count, subject_count) in enumerate(teachers)
    ]

    # --- Return Paginated Response ---
    return pagination.format_response(data, total_count)

    
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
        "school_id": teacher.school_id,
        "school_name": teacher.school.school_name if teacher.school else None,
        "profile_image": teacher.profile_image,
        "name": f"{teacher.first_name} {teacher.last_name}",
        "email": teacher.email,
        "phone": teacher.phone,
        "present_in": teacher.present_in,
        "teacher_type": teacher.teacher_type,
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
    # ✅ Allow both school and staff users
    if current_user.role not in [UserRole.SCHOOL, UserRole.STAFF]:
        raise HTTPException(status_code=403, detail="Only schools and staff can access this resource.")

    # ✅ Get school based on user role
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
            raise HTTPException(status_code=404, detail="School not found for this staff member.")

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
        "profile_image": teacher.profile_image,
        "name": f"{teacher.first_name} {teacher.last_name}",
        "first_name": teacher.first_name,
        "last_name": teacher.last_name,
        "email": teacher.email,
        "phone": teacher.phone,
        "highest_qualification": teacher.highest_qualification,
        "start_duty": teacher.start_duty,
        "end_duty": teacher.end_duty,
        "status": "active" if teacher.is_active else "inactive",
        "present_in": teacher.present_in,
        "teacher_type": teacher.teacher_type,
        "highest_qualification": teacher.highest_qualification,
        "university": teacher.university,
        "created_at": teacher.created_at,
        "assignments": detailed_assignments
    }

@router.patch("/teacher/{teacher_id}")
def update_teacher_profile(
    teacher_id: str,
    data: TeacherUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Partially update teacher profile (school and staff users).
    Fields not provided in request remain unchanged.
    """

    # ✅ Allow both school and staff users
    if current_user.role not in [UserRole.SCHOOL, UserRole.STAFF]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only school and staff users can update teacher profiles."
        )

    # ✅ Get school based on user role
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
            raise HTTPException(status_code=404, detail="School not found for this staff member.")

    # Fetch teacher under this school
    teacher = db.query(Teacher).filter(
        Teacher.id == teacher_id,
        Teacher.school_id == school.id
    ).first()
    if not teacher:
        raise HTTPException(
            status_code=404,
            detail="Teacher not found or doesn't belong to your school."
        )

    try:
        # Handle profile image upload if provided
        if data.profile_image:
            try:
                teacher.profile_image = upload_base64_to_s3(
                    data.profile_image,
                    f"schools/{school.id}/teachers/profile"
                )
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"S3 Upload failed: {str(e)}")

        # Update only provided fields (excluding profile_image and assignments)
        update_fields = data.model_dump(exclude_unset=True, exclude={"profile_image", "assignments"})
        for field, value in update_fields.items():
            setattr(teacher, field, value)

        # Handle assignments if provided
        if data.assignments is not None:
            # Delete existing assignments
            db.query(TeacherClassSectionSubject).filter(
                TeacherClassSectionSubject.teacher_id == teacher.id
            ).delete()
            # Add new assignments
            new_assignments = [
                TeacherClassSectionSubject(
                    teacher_id=teacher.id,
                    class_id=item.class_id,
                    section_id=item.section_id,
                    subject_id=item.subject_id,
                    school_id=school.id
                )
                for item in data.assignments
            ]
            db.bulk_save_objects(new_assignments)

        db.commit()
        db.refresh(teacher)

        # Log action
        log_action(
            db=db,
            current_user=current_user,
            action_type=ActionType.UPDATE,
            resource_type=ResourceType.TEACHER,
            resource_id=teacher.id,
            description=f"Updated teacher: {teacher.first_name} {teacher.last_name}",
            metadata={"teacher_id": teacher.id, "updated_fields": list(update_fields.keys())}
        )

        return {
            "detail": "Teacher profile updated successfully."
        }

    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


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

    # Get teacher
    teacher = db.query(Teacher).filter(Teacher.user_id == current_user.id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher not found")

    # Get assigned subject IDs
    assignments = db.query(TeacherClassSectionSubject).filter(
        TeacherClassSectionSubject.teacher_id == teacher.id
    ).all()

    subject_ids = {a.subject_id for a in assignments}
    if not subject_ids:
        return []

    # Query subjects + school_class_subject_id + chapter count
    results = db.query(
        Subject.id.label("subject_id"),
        Subject.name.label("subject_name"),
        class_subjects.c.school_class_subject_id,
        func.count(Chapter.id).label("chapter_count")
    ).join(
        class_subjects, class_subjects.c.subject_id == Subject.id
    ).outerjoin(
        Chapter, Chapter.school_class_subject_id == class_subjects.c.school_class_subject_id
    ).filter(
        Subject.id.in_(subject_ids)
    ).group_by(
        Subject.id,
        Subject.name,
        class_subjects.c.school_class_subject_id
    ).all()

    return [
        {
            "id": r.subject_id,
            "name": r.subject_name,
            "school_class_subject_id": r.school_class_subject_id,
            "chapter_count": r.chapter_count
        }
        for r in results
    ]
