from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session,joinedload
from app.db.session import get_db
from app.models.admin import AccountConfiguration, CreditConfiguration
from app.models.school import School
from app.models.users import User
from app.models.teachers import Teacher
from app.models.students import Student
from app.schemas.admin import (
    ConfigurationCreateSchema,SchoolClassSubjectBase,ChapterCreate,ChapterUpdate
)
from app.models.admin import CreditMaster,SchoolClassSubject,Chapter,ChapterVideo,ChapterImage,ChapterPDF,ChapterQnA
from sqlalchemy.exc import SQLAlchemyError
from app.utils.permission import require_roles
from app.schemas.users import UserRole
from sqlalchemy import func
from collections import defaultdict
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
    db: Session = Depends(get_db),
    current_user = Depends(require_roles(UserRole.ADMIN))
):
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin account is allowed to view all schools."
        )

    try:
        schools = db.query(School).all()
        if not schools:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No schools found."
            )

        result = []
        for school in schools:
            teacher_count = db.query(func.count()).select_from(Teacher).filter(Teacher.school_id == school.id).scalar()
            student_count = db.query(func.count()).select_from(Student).filter(Student.school_id == school.id).scalar()
            student_count = db.query(func.count()).select_from(Student).filter(Student.school_id == school.id).scalar()
            # active_student_count = db.query(func.count()).select_from(Student).filter(Student.school_id == school.id, Student.is_active == True).scalar()
            # inactive_student_count = db.query(func.count()).select_from(Student).filter(Student.school_id == school.id, Student.is_active == False).scalar()
            user = db.query(User).filter(User.id == school.user_id).first()
            if not user:
                raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Associated user not found."
                )

            result.append({
                "school_id": school.id,
                "school_name": school.school_name,
                "location": user.location,
                "no_of_teachers": teacher_count,
                "no_of_students": student_count,
                "active_students": student_count,
                # "inactive_students": inactive_student_count,
                "created_at": school.created_at,
                "is_active": school.is_active,
                "is_verified": school.is_verified,
                "principal_name": school.principal_name,
            })

        return result

    except SQLAlchemyError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
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
        if not credits:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Credit information not found for this school."
            )    

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
            "available_credit": credits.available_credit,
            "earned_credit": credits.used_credit,
        }

    except SQLAlchemyError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error occurred: {str(e)}"
        )        
        
@router.get("/all-students/")
def get_all_students(
    limit: int = 10,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user = Depends(require_roles(UserRole.ADMIN))
):
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin account is allowed to view all students."
        )

    try:
        students = db.query(Student).options(joinedload(Student.school),joinedload(Student.classes)).offset(offset).limit(limit).all()
        if not students:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No students found."
            )

        result = []
        for student in students:
            result.append({
                "student_id": student.id,
                "name": f"{student.first_name} {student.last_name}",
                "class_name": student.classes.name if student.classes else "N/A",
                "school_name": student.school.school_name if student.school else "N/A",
                # "location": student.school.location if student.school else "N/A",
                # "email": student.email,
                # "is_active": student.is_active,
                "created_at": student.created_at,
            })

        return result

    except SQLAlchemyError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error occurred: {str(e)}"
        )
@router.get("/student/{student_id}/")
def get_student_details(
    student_id: str,
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

        return {
            "student_id": student.id,
            "name": f"{student.first_name} {student.last_name}",
            "class_name": student.classes.name if student.classes else "N/A",
            "school_name": student.school.school_name if student.school else "N/A",
            # "location": student.school.location if student.school else "N/A",
            "block_division": student.school.block_division if student.school else "N/A",
            "district": student.school.district if student.school else "N/A",
            "state": student.school.state if student.school else "N/A",
            "location": user.location,
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
    limit: int = 10,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user = Depends(require_roles(UserRole.ADMIN))
):
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin account is allowed to view all teachers."
        )

    try:
        teachers = db.query(Teacher).options(joinedload(Teacher.school)).offset(offset).limit(limit).all()
        if not teachers:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No teachers found."
            )

        result = []
        for teacher in teachers:
            school = db.query(School).filter(School.id == teacher.school_id).first()
            result.append({
                "teacher_id": teacher.id,
                "name": f"{teacher.first_name} {teacher.last_name}",
                "phone": teacher.phone,
                "school_name": school.school_name if school else "N/A",
                # "school_name": teacher.school.school_name if teacher.school else "N/A",
                "email": teacher.email,
                # "is_active": teacher.is_active,
                "created_at": teacher.created_at,
            })

        return result

    except SQLAlchemyError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error occurred: {str(e)}"
        )
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

        return {
            "teacher_id": teacher.id,
            "name": f"{teacher.first_name} {teacher.last_name}",
            "phone": teacher.phone,
            "email": teacher.email,
            "school_name": school.school_name if school else "N/A",
            "location": user.location,
            # "is_active": teacher.is_active,
            "created_at": teacher.created_at,
        }

    except SQLAlchemyError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error occurred: {str(e)}"
        )

@router.post("/class_subjects/")
def add_class_subject(
    class_subject: SchoolClassSubjectBase,
    db: Session = Depends(get_db),
    current_user = Depends(require_roles(UserRole.ADMIN))
):
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin account is allowed to add class subjects."
        )

    try:
        # ✅ Create SchoolClassSubject directly
        new_class_subject = SchoolClassSubject(
            school_board=class_subject.school_board,
            school_medium=class_subject.school_medium,
            class_name=class_subject.class_name,
            subject=class_subject.subject
        )

        db.add(new_class_subject)
        db.commit()
        db.refresh(new_class_subject)
        return {
            "detail": "Class subject added successfully.",
            "class_subject_id": new_class_subject.id
        }

    except SQLAlchemyError as e:
        db.rollback()  # Important: rollback on error
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error occurred: {str(e)}"
        )

@router.get("/class_subjects/")
def list_class_subjects(
    db: Session = Depends(get_db),
    current_user = Depends(require_roles(UserRole.ADMIN))
):
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin account is allowed to view class subjects."
        )

    try:
        class_subjects = db.query(SchoolClassSubject).all()
        return [
            {
                "id": cs.id,
                "school_board": cs.school_board,
                "school_medium": cs.school_medium,
                "class_name": cs.class_name,
                "subject": cs.subject,
                "created_at": cs.created_at,
                "updated_at": cs.updated_at,
            }
            for cs in class_subjects
        ]

    except SQLAlchemyError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error occurred: {str(e)}"
        )
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
    current_user = Depends(require_roles(UserRole.ADMIN))
):
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin account is allowed to view chapters."
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
    current_user = Depends(require_roles(UserRole.SCHOOL)),
):
    # Ensure only school role can access
    if current_user.role != UserRole.SCHOOL:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only school accounts can access this resource."
        )

    # Get current school info
    school = db.query(School).filter(School.user_id == current_user.id).first()
    if not school:
        raise HTTPException(status_code=404, detail="School profile not found.")

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
            key = cs.class_name
            classes_dict[key].append(cs.subject)

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
    current_user: User = Depends(require_roles(UserRole.SCHOOL)),
):
    # Only school users allowed
    if current_user.role != UserRole.SCHOOL:
        raise HTTPException(status_code=403, detail="Only schools can access this resource.")

    # Fetch school credit
    credit = db.query(CreditMaster).filter(CreditMaster.school_id == current_user.school_profile.id).first()
    if not credit:
        raise HTTPException(status_code=404, detail="Credit account not found for this school.")

    # Calculate available credit (just in case)
    credit.calculate_available_credit()

    return {
        "school_id": current_user.school_profile.id,
        "available_credit": credit.available_credit,
        "self_added_credit": credit.self_added_credit or 0,
        "earned_credit": credit.earned_credit or 0,
        "used_credit": credit.used_credit or 0,
        "transfer_credit": credit.transfer_credit or 0,
        "last_updated": credit.updated_at,
    }