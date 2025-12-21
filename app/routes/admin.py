from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session,joinedload
from app.db.session import get_db
from app.models.admin import ( AccountConfiguration, CreditConfiguration,AdminExam,AdminExamStatus,AdminExamBank,
                            QuestionType,StudentAdminExamData,QuestionSetBank,QuestionSet,StudentExamStatus,RechargePlan)
from app.models.school import School,StudentExamData,SchoolBoard,SchoolMedium,SchoolType,HomeAssignment
from app.models.users import User
from app.models.teachers import Teacher,TeacherClassSectionSubject
from app.models.students import Student,StudentStatus,SelfSignedStudent
from app.models.staff import Staff
from app.schemas.admin import (
    ConfigurationCreateSchema,SchoolClassSubjectBase,ChapterCreate,ChapterUpdate,AdminExamCreate,
    AdminExamUpdate,ExamQuestionPayloadList,QuestionSetCreate,BulkQuestionCreate,QuestionUpdate,
    StudentExamSubmitRequest,RechargePlanCreate,RechargePlanResponse,RechargePlanListResponse,
    StudentPurchaseRequest,StudentPurchaseResponse
)
from app.services.students import update_admin_exam_class_ranks
from app.models.admin import ( CreditMaster,SchoolClassSubject,Chapter,ChapterVideo,ChapterImage,
                            ChapterPDF,ChapterQnA,PlanDuration,StudentSubscription,Payment,
                            PaymentStatus)
from sqlalchemy.exc import SQLAlchemyError
from app.utils.permission import require_roles
from app.schemas.users import UserRole
from sqlalchemy import func,cast, String,case
from collections import defaultdict
from app.core.dependencies import get_current_user
from typing import Optional
from app.services.pagination import PaginationParams
from datetime import datetime, timedelta
from app.utils.services import get_validity_days
router = APIRouter()
@router.post("/account-credit/configuration/")
def create_account_credit_config(
    config_data: ConfigurationCreateSchema,
    db: Session = Depends(get_db),
    current_user = Depends(require_roles(UserRole.ADMIN))
):
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin account is allowed to create configurations."
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
            detail=f"Database error occurred: {str(e)}"
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error occurred: {str(e)}"
        )


@router.get("/all-school/")
def get_all_school(
    school_name: Optional[str] = None,
    school_id: Optional[str] = None,
    status: Optional[bool] = None,  # True = active, False = inactive
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    pagination: PaginationParams = Depends(),
    db: Session = Depends(get_db),
    current_user = Depends(require_roles(UserRole.ADMIN))
):
    # Admin check
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=403,
            detail="Only admin account is allowed to view all schools."
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
            query
            .order_by(School.created_at.desc())
            .offset(pagination.offset())
            .limit(pagination.limit())
            .all()
        )

        if not schools:
            return pagination.format_response([], total_count=0)

        result = []

        for school in schools:

            # Count teachers
            teacher_count = db.query(func.count()).select_from(Teacher).filter(
                Teacher.school_id == school.id
            ).scalar()

            # Count students
            student_count = db.query(func.count()).select_from(Student).filter(
                Student.school_id == school.id
            ).scalar()

            # Count ACTIVE students
            active_student_count = db.query(func.count()).select_from(Student).filter(
                Student.school_id == school.id,
                Student.status == StudentStatus.ACTIVE
            ).scalar()

            # Count INACTIVE students
            inactive_student_count = db.query(func.count()).select_from(Student).filter(
                Student.school_id == school.id,
                Student.status == StudentStatus.INACTIVE
            ).scalar()

            # Related user
            user = db.query(User).filter(User.id == school.user_id).first()

            # Build result
            result.append({
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
            })

        return pagination.format_response(result, total_count=total_count)

    except SQLAlchemyError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Database error occurred: {str(e)}"
        )

@router.put("/school/{school_id}/verify/")
def verify_school(
    school_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(require_roles(UserRole.ADMIN))
):
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin account is allowed to verify schools."
        )

    try:
        school = db.query(School).filter(School.id == school_id).first()
        if not school:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="School not found."
            )
        user=db.query(User).filter(User.id == school.user_id).first()
        user.is_verified = True
        school.is_verified = True
        existing_credit = db.query(CreditMaster).filter(CreditMaster.school_id == school.id).first()
        if not existing_credit:
            credit_master = CreditMaster(
                school_id=school.id,
                earned_credit=100
            )
            db.add(credit_master)
        db.commit()
        return {"detail": "School verified successfully."}

    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error occurred: {str(e)}"
        )
@router.get("/school/{school_id}/")
def get_school_details(
    school_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(require_roles(UserRole.ADMIN))
):
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin account is allowed to view school details."
        )

    try:
        school = db.query(School).filter(School.id == school_id).first()
        if not school:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="School not found."
            )
        # Get user location from User table using user_id from school
        user = db.query(User).filter(User.id == school.user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Associated user not found."
            )
        credits = db.query(CreditMaster).filter(CreditMaster.school_id == school.id).first()
        if not school.is_verified:
            available_credit = 0
            earned_credit = 0
        else:
    # If school is verified, use credits from DB or 0 if no record exists
            available_credit = credits.available_credit if credits else 0
            earned_credit = credits.used_credit if credits else 0   
        teacher_count = db.query(func.count()).select_from(Teacher).filter(Teacher.school_id == school.id).scalar()
        student_count = db.query(func.count()).select_from(Student).filter(Student.school_id == school.id).scalar()

        return {
            "school_id": school.id,
            "school_name": school.school_name,
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
            "available_credit": available_credit,
            "earned_credit": earned_credit,
        }

    except SQLAlchemyError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error occurred: {str(e)}"
        )        
        
@router.get("/all-students/")
def get_all_students(
    student_id: int = None,
    student_name: str = None,
    school_name: str = None,
    status: str = None,
    pagination: PaginationParams = Depends(),
    db: Session = Depends(get_db),
    current_user = Depends(require_roles(UserRole.ADMIN))
):

    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=403,
            detail="Only admin account is allowed to view all students."
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
            (Student.first_name.ilike(f"%{student_name}%")) |
            (Student.last_name.ilike(f"%{student_name}%"))
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
    students = (
        query
        .offset(pagination.offset())
        .limit(pagination.limit())
        .all()
    )

    # Format student data
    items = []
    for student in students:
        items.append({
            "student_id": student.id,
            "name": f"{student.first_name} {student.last_name}",
            "class_name": student.classes.name if student.classes else "N/A",
            "school_name": student.school.school_name if student.school else "N/A",
            "status": student.status.value,
            "created_at": student.created_at,
        })

    # Return paginated response
    return pagination.format_response(items, total_count)

@router.get("/student/{student_id}/")
def get_student_details(
    student_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(require_roles(UserRole.ADMIN))
):
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin account is allowed to view student details."
        )

    try:
        student = db.query(Student).filter(Student.id == student_id).first()
        if not student:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Student not found."
            )
        
        user = db.query(User).filter(User.id == student.user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Associated user not found."
            )
        last_exam = ( db.query(StudentExamData).filter(StudentExamData.student_id == student.id).order_by(StudentExamData.submitted_at.desc()).first())

        return {
            "student_id": student.id,
            "name": f"{student.first_name} {student.last_name}",
            "profile_image": student.profile_image,
            "class_name": student.classes.name if student.classes else "N/A",
            "school_name": student.school.school_name if student.school else "N/A",
            # "location": student.school.location if student.school else "N/A",
            "block_division": student.school.block_division if student.school else "N/A",
            "district": student.school.district if student.school else "N/A",
            "state": student.school.state if student.school else "N/A",
            "location": user.location,
            "last_appeared_exam":last_exam.submitted_at if last_exam else None,
            "exam_type":last_exam.exam.exam_type if last_exam and last_exam.exam else None,
            "exam_result":last_exam.result if last_exam else None,
            "status": student.status,
            # "email": student.email,
            # "is_active": student.is_active,
            "created_at": student.created_at,
        }

    except SQLAlchemyError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error occurred: {str(e)}"
        )        

@router.get("/all-teachers/")
def get_all_teachers(
    teacher_id: str = None,
    teacher_name: str = None,
    school_name: str = None,
    status: str = None,   # active / inactive or whatever your enum is
    pagination: PaginationParams = Depends(),
    db: Session = Depends(get_db),
    current_user = Depends(require_roles(UserRole.ADMIN))
):

    # Only admin can access
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=403,
            detail="Only admin account is allowed to view all teachers."
        )

    # Base query (NO SCHOOL LIMIT)
    query = (
        db.query(Teacher)
        .options(joinedload(Teacher.school))
    )

    # Apply filters
    if teacher_id:
        query = query.filter(Teacher.id == teacher_id)

    if teacher_name:
        query = query.filter(
            (Teacher.first_name.ilike(f"%{teacher_name}%")) |
            (Teacher.last_name.ilike(f"%{teacher_name}%"))
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
    teachers = (
        query
        .offset(pagination.offset())
        .limit(pagination.limit())
        .all()
    )

    # Build response data
    items = []
    for teacher in teachers:
        items.append({
            "teacher_id": teacher.id,
            "name": f"{teacher.first_name} {teacher.last_name}",
            "phone": teacher.phone,
            "email": teacher.email,
            "school_name": teacher.school.school_name if teacher.school else "N/A",
            "status": teacher.status.value if hasattr(teacher, "status") else None,
            "created_at": teacher.created_at,
        })

    # Return paginated response
    return pagination.format_response(items, total_count)

@router.get("/teacher/{teacher_id}/")
def get_teacher_details(
    teacher_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(require_roles(UserRole.ADMIN))
):
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin account is allowed to view teacher details."
        )

    try:
        teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
        if not teacher:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Teacher not found."
            )
        
        user = db.query(User).filter(User.id == teacher.user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Associated user not found."
            )
        school= db.query(School).filter(School.id == teacher.school_id).first()
        if not school: 
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Associated school not found."
            )
        
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
            "teacher_id": teacher.id,
            "profile_image": teacher.profile_image,
            "name": f"{teacher.first_name} {teacher.last_name}",
            "phone": teacher.phone,
            "email": teacher.email,
            "school_name": school.school_name if school else "N/A",
            "location": user.location,
            "assignments": detailed_assignments,
            # "is_active": teacher.is_active,
            "created_at": teacher.created_at,
        }

    except SQLAlchemyError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error occurred: {str(e)}"
        )

@router.get("/class_subjects/")
def get_class_subjects(
    class_name: str = None,
    school_board: str = None,
    pagination: PaginationParams = Depends(),
    db: Session = Depends(get_db),
    current_user = Depends(require_roles(UserRole.ADMIN))
):
    # Access check
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=403,
            detail="Only admin account is allowed to view class subjects."
        )

    try:
        query = db.query(SchoolClassSubject)

        # 🔍 Apply Filters
        if class_name:
            query = query.filter(SchoolClassSubject.class_name.ilike(f"%{class_name}%"))

        if school_board:
            query = query.filter(cast(SchoolClassSubject.school_board, String).ilike(f"%{school_board}%"))

        # Count before pagination
        total_count = query.count()

        # Apply pagination
        subjects = (
            query
            .offset(pagination.offset())
            .limit(pagination.limit())
            .all()
        )

        result = []
        for obj in subjects:
            result.append({
                "class_id": obj.id,
                "school_board": obj.school_board,
                "school_medium": obj.school_medium,
                "class_name": obj.class_name,
                "subject": obj.subject,
                "created_at": obj.created_at,
            })

        return pagination.format_response(result, total_count)

    except SQLAlchemyError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Database error occurred: {str(e)}"
        )

@router.post("/class_subjects/")
def create_class_subjects(
    payload: SchoolClassSubjectBase,
    db: Session = Depends(get_db),
    current_user = Depends(require_roles(UserRole.ADMIN))
):
    # Access control
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin account is allowed to create class subjects."
        )

    try:
        # 🔍 Check duplicate (class_name + subject + board + medium combo)
        existing = db.query(SchoolClassSubject).filter(
            SchoolClassSubject.class_name == payload.class_name,
            SchoolClassSubject.subject == payload.subject,
            SchoolClassSubject.school_board == payload.school_board,
            SchoolClassSubject.school_medium == payload.school_medium
        ).first()

        if existing:
            raise HTTPException(
                status_code=400,
                detail="This subject already exists for the selected class, board and medium."
            )

        # Create record
        new_record = SchoolClassSubject(
            school_board=payload.school_board,
            school_medium=payload.school_medium,
            class_name=payload.class_name,
            subject=payload.subject
        )

        db.add(new_record)
        db.commit()
        db.refresh(new_record)

        return {
            "detail": "Class subject created successfully.",
            "class_subject_id": new_record.id
        }

    except SQLAlchemyError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error occurred: {str(e)}"
        )
@router.get("/classes/")
def get_all_classes(
    school_board: Optional[SchoolBoard] = None,
    school_medium: Optional[SchoolMedium] = None,
    pagination: PaginationParams = Depends(),
    db: Session = Depends(get_db),
    current_user = Depends(require_roles(UserRole.ADMIN,UserRole.SCHOOL,UserRole.TEACHER,UserRole.STUDENT))
):
    """Fetch all unique classes filtered by board & medium."""

    # 🔐 Access Control
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin account is allowed to view classes."
        )

    try:
        query = db.query(SchoolClassSubject.class_name).distinct()

        # 🔍 Apply filters if provided
        if school_board:
            query = query.filter(SchoolClassSubject.school_board == school_board)

        if school_medium:
            query = query.filter(SchoolClassSubject.school_medium == school_medium)

        total_count = query.count()

        # 📌 Apply pagination
        classes = (
            query
            .order_by(SchoolClassSubject.class_name.asc())
            .offset(pagination.offset())
            .limit(pagination.limit())
            .all()
        )

        # Convert list of tuples → plain list
        class_list = [c[0] for c in classes]

        return pagination.format_response(
            class_list,
            total_count
        )

    except SQLAlchemyError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error occurred: {str(e)}"
        )

@router.get("/subjects/")
def get_subjects_for_class(
    board: Optional[str] = None,
    medium: Optional[str] = None,
    class_name: Optional[str] = None,
    pagination: PaginationParams = Depends(),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    if current_user.role == UserRole.STUDENT:
        student = db.query(SelfSignedStudent).filter(SelfSignedStudent.user_id == current_user.id).first()

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
        query = (
            db.query(
                SchoolClassSubject.id.label("id"),
                SchoolClassSubject.subject.label("subject"),
                func.count(Chapter.id).label("chapter_count")
            )
            .outerjoin(Chapter, Chapter.school_class_subject_id == SchoolClassSubject.id)
        )

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

        return pagination.format_response([
            {
                "id": row.id,
                "subject": row.subject,
                "total_chapters": row.chapter_count
            }
            for row in results
        ], total_count)

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
    if current_user.role not in [UserRole.ADMIN, UserRole.SCHOOL, UserRole.TEACHER, UserRole.STUDENT]:
        raise HTTPException(status_code=403, detail="Access denied")

    # Check subject exists
    subject = db.query(SchoolClassSubject).filter(SchoolClassSubject.id == subject_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")

    # Main query: chapter + video count + task count
    chapters_query = (
        db.query(
            Chapter.id.label("chapter_id"),
            Chapter.title.label("chapter_title"),
            Chapter.created_at.label("created_at"),
            func.count(ChapterVideo.id).label("video_count"),
            func.count(HomeAssignment.id).label("task_count")
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
        "chapters": result
    }

@router.post("/class_subjects/{subject_id}/chapters/")
def add_chapter_to_subject(
    subject_id: int,
    chapter: ChapterCreate,
    db: Session = Depends(get_db),
    current_user = Depends(require_roles(UserRole.ADMIN))
):
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin account is allowed to add chapters."
        )

    try:
        # Check if subject exists
        subject = db.query(SchoolClassSubject).filter(SchoolClassSubject.id == subject_id).first()
        if not subject:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Class subject not found."
            )

        # Create Chapter
        new_chapter = Chapter(
            title=chapter.title,
            description=chapter.description,
            school_class_subject_id=subject.id
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
            db.add(ChapterQnA(question=q.question, answer=q.answer, chapter_id=new_chapter.id))

        db.commit()

        return {
            "detail": f"Chapter '{new_chapter.title}' added successfully to subject '{subject.subject}'.",
            "chapter_id": new_chapter.id
        }

    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error occurred: {str(e)}"
        )
@router.put("/chapters/{chapter_id}/")
def update_chapter(
    chapter_id: int,
    chapter_data: ChapterUpdate,
    db: Session = Depends(get_db),
    current_user = Depends(require_roles(UserRole.ADMIN))
):
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin account is allowed to update chapters."
        )

    try:
        chapter = db.query(Chapter).filter(Chapter.id == chapter_id).first()
        if not chapter:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chapter not found."
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

        db.commit()
        db.refresh(chapter)

        return {
            "detail": f"Chapter '{chapter.title}' updated successfully.",
            "chapter_id": chapter.id
        }

    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error occurred: {str(e)}"
        )
@router.get("/chapters/{chapter_id}/")
def get_chapter_details(
    chapter_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)  # allow all roles
):
    # ✅ Role check: only allow Admin, School, Teacher, Student
    if current_user.role not in [UserRole.ADMIN, UserRole.SCHOOL, UserRole.TEACHER, UserRole.STUDENT]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to view this chapter."
        )

    try:
        chapter = db.query(Chapter).filter(Chapter.id == chapter_id).first()
        if not chapter:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chapter not found."
            )

        return {
            "chapter_id": chapter.id,
            "title": chapter.title,
            "description": chapter.description,
            "subject_id": chapter.school_class_subject_id,
            "videos": [{"id": v.id, "url": v.url} for v in chapter.videos],
            "images": [{"id": i.id, "url": i.url} for i in chapter.images],
            "pdfs": [{"id": p.id, "url": p.url} for p in chapter.pdfs],
            "qnas": [{"id": q.id, "question": q.question, "answer": q.answer} for q in chapter.qnas],
            "created_at": chapter.created_at,
            "updated_at": chapter.updated_at
        }

    except SQLAlchemyError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error occurred: {str(e)}"
        )
@router.get("/classes-with-subjects/")
def get_classes_with_subject_names(
    db: Session = Depends(get_db),
    current_user = Depends(require_roles(UserRole.SCHOOL, UserRole.STAFF)),
):
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
        # Filter classes for this school's board and medium
        class_subjects = (
            db.query(SchoolClassSubject)
            .filter(
                SchoolClassSubject.school_board == school.school_board,
                SchoolClassSubject.school_medium == school.school_medium
            )
            .all()
        )

        if not class_subjects:
            return {
                "school_name": school.school_name,
                "school_board": school.school_board,
                "school_medium": school.school_medium,
                "classes": []
            }

        # Group subjects by class
        classes_dict = defaultdict(list)
        for cs in class_subjects:
            classes_dict[cs.class_name].append({
                "name": cs.subject,
                "school_class_subject_id": cs.id  # assuming id is the PK
            })

        # Format final structured response
        result = []
        for class_name, subjects in classes_dict.items():
            result.append({
                "class_name": class_name,
                "subjects": subjects
            })

        return {
            "school_name": school.school_name,
            "school_board": school.school_board,
            "school_medium": school.school_medium,
            "classes": result
        }

    except SQLAlchemyError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error occurred: {str(e)}"
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
        raise HTTPException(status_code=403, detail="Not authorized to access this resource.")

    # Fetch school credit
    credit = db.query(CreditMaster).filter(CreditMaster.school_id == school_id).first()
    if not credit:
        raise HTTPException(status_code=404, detail="Credit account not found for this school.")

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
    current_user = Depends(require_roles(UserRole.ADMIN))
):

    # 1️⃣ Verify school mapping exists
    scs = db.query(SchoolClassSubject).filter(
        SchoolClassSubject.id == payload.school_class_subject_id
    ).first()

    if not scs:
        raise HTTPException(
            status_code=404,
            detail="Invalid school_class_subject_id provided."
        )

    # 2️⃣ Optional duplicate prevention
    existing_exam = db.query(AdminExam).filter(
        AdminExam.name == payload.name,
        AdminExam.school_class_subject_id == payload.school_class_subject_id
    ).first()

    if existing_exam:
        raise HTTPException(
            status_code=400,
            detail="Exam with same name already exists for this class & subject."
        )

    try:
        # 3️⃣ Create Exam
        new_exam = AdminExam(
            name=payload.name,
            school_class_subject_id=payload.school_class_subject_id,
            class_name=scs.class_name,
            subject=scs.subject,
            exam_type=payload.exam_type,
            question_type=payload.question_type,
            passing_mark=payload.passing_mark,
            repeat=payload.repeat,
            duration=payload.duration,
            exam_validity=payload.exam_validity,
            description=payload.description,
            status=AdminExamStatus.ACTIVE
        )

        db.add(new_exam)
        db.commit()
        db.refresh(new_exam)

        return {
            "detail": "Exam created successfully.",
            "exam_id": new_exam.id
        }

    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Database error: {str(e)}"
        )

@router.get("/exams/")
def get_exams(
    db: Session = Depends(get_db),
    current_user = Depends(require_roles(UserRole.ADMIN, UserRole.STUDENT))
):

    # Base query
    exams_query = db.query(AdminExam)

    # If user is a student → filter exams by student's selected class
    if current_user.role == UserRole.STUDENT:
        student = db.query(SelfSignedStudent).filter(
            SelfSignedStudent.user_id == current_user.id
        ).first()

        if not student:
            raise HTTPException(status_code=404, detail="Student profile not found.")

        if not student.select_class:
            raise HTTPException(
                status_code=400,
                detail="Student has not selected a class yet."
            )

        # Filter only exams matching student's selected class
        exams_query = exams_query.filter(AdminExam.class_name == student.select_class)

    exams = exams_query.all()

    if not exams:
        return {
            "message": "No exams found.",
            "count": 0,
            "data": []
        }

    response = []

    for exam in exams:
        student_count = db.query(StudentAdminExamData).filter(
            StudentAdminExamData.exam_id == exam.id
        ).count()

        question_count = db.query(AdminExamBank).filter(
            AdminExamBank.exam_id == exam.id
        ).count()

        response.append({
            "exam_id": exam.id,
            "name": exam.name,
            "class_name": exam.class_name,
            "subject": exam.subject,
            "exam_type": exam.exam_type,
            "question_type": exam.question_type,
            "passing_mark": exam.passing_mark,
            "duration": exam.duration,
            "repeat_allowed": exam.repeat,
            "valid_until": exam.exam_validity,
            "status": exam.status,
            "no_of_questions": question_count,
            "no_of_students_attempted": student_count
        })

    return {
        "message": "Exam list retrieved successfully.",
        "count": len(response),
        "data": response
    }


@router.put("/exams/{exam_id}/")
def update_exam(
    exam_id: str,
    payload: AdminExamUpdate,
    db: Session = Depends(get_db),
    current_user = Depends(require_roles(UserRole.ADMIN,UserRole.STUDENT,UserRole.STAFF))
):

    # 1️⃣ Fetch the exam
    exam = db.query(AdminExam).filter(AdminExam.id == exam_id).first()

    if not exam:
        raise HTTPException(
            status_code=404,
            detail="Exam not found."
        )

    # 2️⃣ Update fields dynamically
    update_data = payload.dict(exclude_unset=True)

    for field, value in update_data.items():
        setattr(exam, field, value)

    try:
        db.commit()
        db.refresh(exam)

        return {
            "detail": "Exam updated successfully.",
            "exam_id": exam.id
        }

    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Database error: {str(e)}"
        )
@router.post("/add-questions/{exam_id}/")
async def add_questions(
    exam_id: str,
    payload: ExamQuestionPayloadList,
    db: Session = Depends(get_db),
    current_user = Depends(require_roles(UserRole.ADMIN))
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
                    detail=f"Unsupported exam question type: {q.que_type}"
                )

            # --- COMMON FIELDS ---
            db_entry = AdminExamBank(
                exam_id=exam_id,
                question=q.question,
                que_type=q.que_type,
                image=q.image
            )

            # --- SHORT TYPE (MCQ) ---
            if q.que_type == "short":
                if not (q.option_a and q.option_b and q.option_c and q.option_d and q.correct_option):
                    raise HTTPException(
                        status_code=400,
                        detail="Short questions require options and correct_option"
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
                        detail="Long questions require descriptive_answer and answer_keys"
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

        return {"message": "Questions added successfully", "count": len(questions_to_insert)}

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error processing questions: {str(e)}")

@router.get("/exams/{exam_id}/questions/")
def get_exam_questions(
    exam_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(require_roles(UserRole.ADMIN, UserRole.STUDENT))
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
            "image": q.image
        }

        if q.que_type == QuestionType.short:  # MCQ
            base["options"] = {
                "option_a": q.option_a,
                "option_b": q.option_b,
                "option_c": q.option_c,
                "option_d": q.option_d
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
    current_user = Depends(require_roles(UserRole.ADMIN, UserRole.STUDENT))
):
    # 1️⃣ Check if exam exists
    exam = db.query(AdminExam).filter(AdminExam.id == exam_id).first()
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found.")

    # 2️⃣ Count how many questions exist
    total_questions = (
        db.query(AdminExamBank)
        .filter(AdminExamBank.exam_id == exam_id)
        .count()
    )

    # 3️⃣ Count how many student entries exist (who appeared)
    total_students_appeared = (
        db.query(StudentAdminExamData)
        .filter(StudentAdminExamData.exam_id == exam_id)
        .count()
    )

    return {
        "exam_id": exam.id,
        "name": exam.name,
        "exam_type": exam.exam_type.value,
        "question_type": exam.question_type.value,
        "class_name": exam.class_name,
        "subject": exam.subject,
        "duration": exam.duration,
        "passing_mark": exam.passing_mark,
        "total_questions": total_questions,
        "attempts_allowed": exam.repeat,
        "total_students_appeared": total_students_appeared,
        "status": exam.status.value,
        "description": exam.description,
        "exam_validity": exam.exam_validity
    }
@router.post("/admin-exams/{exam_id}/submit")
def submit_admin_exam(
    exam_id: str,
    submission: StudentExamSubmitRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # 1️⃣ Role check
    if current_user.role != UserRole.STUDENT:
        raise HTTPException(
            status_code=403,
            detail="Only students can submit admin exams"
        )

    # 2️⃣ Student profile check
    student_profile = current_user.self_signed_student_profile
    if not student_profile:
        raise HTTPException(
            status_code=400,
            detail="Student profile not found"
        )

    # 3️⃣ Attempt number
    last_attempt = (
        db.query(StudentAdminExamData)
        .filter(
            StudentAdminExamData.student_id == student_profile.id,
            StudentAdminExamData.exam_id == exam_id
        )
        .order_by(StudentAdminExamData.attempt_no.desc())
        .first()
    )
    next_attempt_no = last_attempt.attempt_no + 1 if last_attempt else 1

    # 4️⃣ Fetch admin MCQs
    mcqs = (
        db.query(AdminExamBank)
        .filter(AdminExamBank.exam_id == exam_id)
        .all()
    )

    if not mcqs:
        raise HTTPException(
            status_code=404,
            detail="No questions found for this exam"
        )

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
        StudentExamStatus.pass_
        if result_percentage >= 40
        else StudentExamStatus.fail
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
        submitted_at=datetime.utcnow()
    )

    db.add(student_exam)
    db.commit()
    db.refresh(student_exam)

    # 7️⃣ Update class rank
    update_admin_exam_class_ranks(
        db=db,
        exam_id=exam_id,
        class_name=student_profile.select_class
    )

    return {
        "detail": "Admin exam submitted successfully",
        "exam_id": exam_id,
        "attempt_no": next_attempt_no,
        "result": result_percentage,
        "status": status_result
    }

@router.post("/set/")
def create_question_set(
    payload: QuestionSetCreate, 
    db: Session = Depends(get_db),
    current_user = Depends(require_roles(UserRole.ADMIN))
    ):

    # Check if set exists already
    existing = db.query(QuestionSet).filter(
        QuestionSet.board == payload.board,
        QuestionSet.class_name == payload.class_name,
        QuestionSet.set == payload.set
    ).first()

    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Set '{payload.set}' already exists for board '{payload.board}' and class '{payload.class_name}'."
        )

    # Create
    new_set = QuestionSet(
        board=payload.board,
        class_name=payload.class_name,
        set=payload.set,
        description=payload.description
    )

    db.add(new_set)
    db.commit()
    db.refresh(new_set)

    return {
        "message": "Question set created successfully",
        "set_id": new_set.id
    }

@router.get("/set/")
def list_question_sets(
    db: Session = Depends(get_db),
    current_user = Depends(require_roles(UserRole.ADMIN, UserRole.STUDENT))
):

    query = (
        db.query(
            QuestionSet.id,
            QuestionSet.board,
            QuestionSet.class_name,
            QuestionSet.set,
            QuestionSet.created_at,
            func.count(QuestionSetBank.id).label("question_count")
        )
        .outerjoin(QuestionSetBank, QuestionSet.id == QuestionSetBank.question_set_id)
        .group_by(QuestionSet.id)
    )

    # ------------------------ ROLE BASED FILTER ------------------------
    if current_user.role == UserRole.STUDENT:
        student = db.query(SelfSignedStudent).filter(
            SelfSignedStudent.user_id == current_user.id
        ).first()

        if not student:
            raise HTTPException(status_code=404, detail="Student profile not found.")

        if not student.select_class:
            raise HTTPException(
                status_code=400,
                detail="Student has not selected a class yet."
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
            "created_at": row.created_at
        }
        for row in result
    ]

    return response

@router.get("/set/{set_id}/")
def get_question_set_details(
    set_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(require_roles(UserRole.ADMIN,UserRole.STUDENT,UserRole.STAFF))
):
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
        "updated_at": question_set.updated_at
    }

@router.post("/set/{set_id}/questions")
def add_questions_to_set(
    set_id: int,
    payload: BulkQuestionCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(UserRole.ADMIN,UserRole.STUDENT))
):

    # Check if Set exists
    question_set = db.query(QuestionSet).filter(QuestionSet.id == set_id).first()
    if not question_set:
        raise HTTPException(status_code=404, detail="Question set not found")

    created_questions = []

    for item in payload.questions:
        new_question = QuestionSetBank(
            question_set_id=set_id,  # ✅ Correct field
            subject=item.subject_id,    # If you're using school_class_subject id, change this to item.subject_id
            year=item.year,
            question=item.question,
            probability_ratio=item.probability_ratio,
            no_of_teacher_verified=item.teacher_verified_count
        )
        
        db.add(new_question)
        created_questions.append(new_question)

    db.commit()

    return {
        "message": f"{len(created_questions)} question(s) added successfully to set {set_id}",
        "added_count": len(created_questions)
    }
@router.get("/set/{set_id}/questions")
def get_questions_by_set(
    set_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(UserRole.ADMIN,UserRole.STUDENT))
):
    # Check if the set exists
    question_set = db.query(QuestionSet).filter(QuestionSet.id == set_id).first()
    if not question_set:
        raise HTTPException(status_code=404, detail="Question set not found")

    # Fetch questions
    questions = db.query(QuestionSetBank).filter(QuestionSetBank.question_set_id == set_id).all()

    # Format response as list of dicts
    response = []
    for q in questions:
        response.append({
            "id": q.id,
            "school_class_subject_id": q.subject,  # FK column
            "subject": q.school_class_subject.subject if q.school_class_subject else "",
            "class_name": q.school_class_subject.class_name if q.school_class_subject else None,
            "year": q.year,
            "probability_ratio": q.probability_ratio,
            "no_of_teacher_verified": q.no_of_teacher_verified,
            "question": q.question,
            "created_at": q.created_at
        })

    return response
@router.put("/set/question/{question_id}/")
def update_question(
    question_id: int,
    payload: QuestionUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(UserRole.ADMIN))
):
    # Fetch question
    question = db.query(QuestionSetBank).filter(QuestionSetBank.id == question_id).first()

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

    return {"message": f"Question {question_id} updated successfully", "updated_question": question_id}

@router.delete("/set/question/{question_id}/")
def delete_question(
    question_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(UserRole.ADMIN))
):
    # Retrieve question
    question = db.query(QuestionSetBank).filter(QuestionSetBank.id == question_id).first()

    if not question:
        raise HTTPException(status_code=404, detail="Question not found")

    # Delete
    db.delete(question)
    db.commit()

    return {"message": f"Question {question_id} deleted successfully"}


@router.post(
    "/admin/recharge-plans/",
    response_model=RechargePlanResponse,
    status_code=201
)
def create_recharge_plan(
    payload: RechargePlanCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # 🔐 Admin check
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=403,
            detail="Only admin can create recharge plans"
        )

    # 🔁 Prevent duplicate plan for same class & duration
    existing_plan = db.query(RechargePlan).filter(
        RechargePlan.class_name == payload.class_name,
        RechargePlan.duration == payload.duration,
        RechargePlan.is_active == True
    ).first()

    if existing_plan:
        raise HTTPException(
            status_code=400,
            detail="Recharge plan already exists for this class and duration"
        )

    validity_days = get_validity_days(payload.duration)

    plan = RechargePlan(
        class_name=payload.class_name,
        duration=payload.duration,
        amount=payload.amount,
        validity_days=validity_days
    )

    db.add(plan)
    db.commit()
    db.refresh(plan)

    return plan

@router.get(
    "/recharge-plans/",
    response_model=list[RechargePlanListResponse]
)
def get_recharge_plans(
    class_name: str = Query(..., description="Student class (eg: 10)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    plans = db.query(RechargePlan).filter(
        RechargePlan.class_name == class_name,
        RechargePlan.is_active == True
    ).order_by(
        case(
            (RechargePlan.duration == PlanDuration.MONTHLY, 1),
            (RechargePlan.duration == PlanDuration.QUARTERLY, 2),
            (RechargePlan.duration == PlanDuration.YEARLY, 3),
        )
    ).all()

    if not plans:
        raise HTTPException(
            status_code=404,
            detail="No recharge plans found for this class"
        )

    return plans

@router.post(
    "/student/purchase-plan/",
    response_model=StudentPurchaseResponse,
    status_code=201
)
def student_purchase_plan(
    payload: StudentPurchaseRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # 🔐 Student only
    if current_user.role != UserRole.STUDENT:
        raise HTTPException(
            status_code=403,
            detail="Only students can purchase plans"
        )

    # 1️⃣ Fetch student profile
    student = db.query(SelfSignedStudent).filter(
        SelfSignedStudent.user_id == current_user.id
    ).first()

    if not student:
        raise HTTPException(404, "Student profile not found")

    if not student.select_class:
        raise HTTPException(400, "Student has not selected a class")

    # 2️⃣ Find recharge plan based on class + duration
    plan = db.query(RechargePlan).filter(
        RechargePlan.class_name == student.select_class,
        RechargePlan.duration == payload.duration,
        RechargePlan.is_active == True
    ).first()

    if not plan:
        raise HTTPException(
            status_code=404,
            detail="Recharge plan not available for selected duration"
        )

    # 3️⃣ Deactivate old subscriptions
    db.query(StudentSubscription).filter(
        StudentSubscription.student_id == student.id,
        StudentSubscription.is_current == True
    ).update({"is_current": False})

    # 4️⃣ Create subscription
    start_date = datetime.utcnow()
    end_date = start_date + timedelta(days=plan.validity_days)

    subscription = StudentSubscription(
        student_id=student.id,
        plan_id=plan.id,
        start_date=start_date,
        end_date=end_date,
        amount_paid=plan.amount,
        is_current=True
    )

    db.add(subscription)
    db.flush()  # to get subscription.id

    # 5️⃣ Create payment entry
    payment = Payment(
        student_id=student.id,
        subscription_id=subscription.id,
        amount=plan.amount,
        payment_status=PaymentStatus.PENDING
    )

    db.add(payment)
    db.commit()

    db.refresh(subscription)
    db.refresh(payment)

    return {
        "subscription_id": subscription.id,
        "payment_id": payment.id,
        "amount": plan.amount,
        "status": "pending"
    }


