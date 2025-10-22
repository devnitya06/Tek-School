from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException,status,UploadFile,File,Query,Form
from app.models.users import User
from app.models.teachers import Teacher,TeacherClassSectionSubject
from app.models.students import Student
from app.models.school import School,Class,Section,Subject,ExtraCurricularActivity,WeekDay,class_extra_curricular,class_section,class_subjects,class_optional_subjects,Transport,PickupStop,DropStop,Attendance,Timetable,TimetableDay,TimetablePeriod,SchoolMarginConfiguration,TransactionHistory,Exam,McqBank,ExamStatusEnum,ExamStatus,StudentExamData,LeaveRequest,LeaveStatus
from app.models.admin import AccountConfiguration, CreditConfiguration, CreditMaster
from app.schemas.users import UserRole
from app.schemas.school import ClassWithSubjectCreate,ClassInput,TransportCreate,TransportResponse,StopResponse,AttendanceCreate,PeriodCreate,TimetableCreate,CreateSchoolCredit,TransferSchoolCredit,CreatePaymentRequest,PaymentVerificationRequest,ExamCreateRequest,ExamUpdateRequest,ExamListResponse,McqCreate,McqBulkCreate,McqResponse,ExamPublishResponse,ExamStatusUpdateRequest,StudentExamSubmitRequest,TimetableUpdate,LeaveCreate,LeaveResponse,LeaveStatusUpdate,ExamDetailResponse
from sqlalchemy.orm import Session,joinedload
from sqlalchemy import delete, insert,extract
from app.db.session import get_db
from app.core.dependencies import get_current_user
from app.utils.permission import require_roles
from typing import List,Optional
from app.utils.s3 import upload_to_s3
from calendar import month_name
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from app.utils.razorpay_client import razorpay_client
import hmac
import hashlib
import time
from app.utils.services import is_time_overlap, create_mcq,get_mcqs_by_exam,delete_mcq,evaluate_exam    
from app.core.config import settings
from app.services.students import update_class_ranks
from app.services.pagination import PaginationParams
from enum import Enum
from app.utils.s3 import upload_base64_to_s3
router = APIRouter()

def timer():
    return time.perf_counter()
@router.patch("/school-profile")
async def update_school_profile(
    school_name: Optional[str] = Form(None),
    school_type: Optional[str] = Form(None),
    school_medium: Optional[str] = Form(None),
    school_board: Optional[str] = Form(None),
    establishment_year: Optional[int] = Form(None),

    pin_code: Optional[str] = Form(None),
    block_division: Optional[str] = Form(None),
    district: Optional[str] = Form(None),
    state: Optional[str] = Form(None),
    country: Optional[str] = Form(None),

    school_email: Optional[str] = Form(None),
    school_phone: Optional[str] = Form(None),
    school_alt_phone: Optional[str] = Form(None),
    school_website: Optional[str] = Form(None),

    principal_name: Optional[str] = Form(None),
    principal_designation: Optional[str] = Form(None),
    principal_email: Optional[str] = Form(None),
    principal_phone: Optional[str] = Form(None),

    profile_pic: Optional[UploadFile] = File(None),
    banner_pic: Optional[UploadFile] = File(None),

    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    # Ensure school is found for current user
    school = db.query(School).filter(School.user_id == current_user.id).first()
    if not school:
        raise HTTPException(status_code=404, detail="School profile not found")

    # Update only if data is provided
    if school_name is not None:
        school.school_name = school_name
    if school_type is not None:
        school.school_type = school_type
    if school_medium is not None:
        school.school_medium = school_medium
    if school_board is not None:
        school.school_board = school_board
    if establishment_year is not None:
        school.establishment_year = establishment_year

    if pin_code is not None:
        school.pin_code = pin_code
    if block_division is not None:
        school.block_division = block_division
    if district is not None:
        school.district = district
    if state is not None:
        school.state = state
    if country is not None:
        school.country = country

    if school_email is not None:
        school.school_email = school_email
    if school_phone is not None:
        school.school_phone = school_phone
    if school_alt_phone is not None:
        school.school_alt_phone = school_alt_phone
    if school_website is not None:
        school.school_website = school_website

    if principal_name is not None:
        school.principal_name = principal_name
    if principal_designation is not None:
        school.principal_designation = principal_designation
    if principal_email is not None:
        school.principal_email = principal_email
    if principal_phone is not None:
        school.principal_phone = principal_phone

    # Handle profile image upload
    if profile_pic:
        try:
            url= upload_to_s3(profile_pic, f"schools/{current_user.id}/profile")
            school.profile_pic_url = url
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    # Handle banner image upload
    if banner_pic:
        try:
            url = upload_to_s3(banner_pic, f"schools/{current_user.id}/banner")
            school.banner_pic_url = url
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    try:
        db.commit()
        db.refresh(school)
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e.__cause__)}")

    return {"detail": "School profile updated successfully"}


@router.get("/school")
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
    school = current_user.school_profile
    return {
        "id": school.id,
        "user_id": school.user_id,
        "school_name": school.school_name,
        "school_type": (
            school.school_type.value if school.school_type else None
        ),
        "school_medium": (
            school.school_medium.value if school.school_medium else None
        ),
        "school_board": (
            school.school_board.value if school.school_board else None
        ),
        "school_logo": school.profile_pic_url,
        "school_banner": school.banner_pic_url,
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
        "principal_phone": school.principal_phone,
        "created_at": school.created_at,
    }

@router.post("/create-class-with-subjects/")
def create_class(
    class_data: ClassWithSubjectCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)):
    
    if current_user.role != UserRole.SCHOOL:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only school users can create classes"
        )
        
    # Get the school associated with the current user
    school = db.query(School).filter(School.user_id == current_user.id).first()
    if not school:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="School not found for this user"
        )    
    # Check if class with same name already exists in this school
    existing_class = db.query(Class).filter(
        Class.name == class_data.class_name,
        Class.school_id == school.id
    ).first()
    
    if existing_class:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Class '{class_data.class_name}' already exists in this school"
        )
    
    # Create the new class
    new_class = Class(
        name=class_data.class_name,
        school_id=school.id
    )
    db.add(new_class)
    db.commit()
    db.refresh(new_class)
    
    # Process sections
    for section_name in class_data.sections:
        section = db.query(Section).filter(
            Section.name == section_name,
            Section.school_id == school.id
        ).first()
        
        if not section:
            section = Section(name=section_name, school_id=school.id)
            db.add(section)
            db.commit()
            db.refresh(section)
        
        # Associate section with class
        db.execute(
            class_section.insert().values(
                class_id=new_class.id,
                section_id=section.id,
                school_id=school.id
            )
        )
    
    # Process subjects
    for subject_name in class_data.subjects:
        subject = db.query(Subject).filter(
            Subject.name == subject_name,
            Subject.school_id == school.id
        ).first()
        
        if not subject:
            subject = Subject(name=subject_name, school_id=school.id)
            db.add(subject)
            db.commit()
            db.refresh(subject)
        
        # Associate subject with class
        db.execute(
            class_subjects.insert().values(
                class_id=new_class.id,
                subject_id=subject.id,
                school_id=school.id
            )
        )
    
    
    # Process extracurricular activities
    for activity_name in class_data.extra_curriculums:
        activity = db.query(ExtraCurricularActivity).filter(
            ExtraCurricularActivity.name == activity_name,
            ExtraCurricularActivity.school_id == school.id
        ).first()
        
        if not activity:
            activity = ExtraCurricularActivity(name=activity_name, school_id=school.id)
            db.add(activity)
            db.commit()
            db.refresh(activity)
        
        db.execute(
            class_extra_curricular.insert().values(
                class_id=new_class.id,
                activity_id=activity.id,
                school_id=school.id
            )
        )
    
    db.commit()
    
    return {
        "detail": "Class created successfully with all associated data",
        "class_id": new_class.id,
        "class_name": new_class.name
    }

@router.put("/classes/{class_id}/section/{section_id}/update")
def update_class_section_fields(
    class_id: int,
    section_id: int,
    data: ClassInput,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Fetch class
    class_obj = db.query(Class).filter(Class.id == class_id).first()
    if not class_obj:
        raise HTTPException(status_code=404, detail="Class not found")
    # Ensure the class belongs to the current user's school
    if class_obj.school_id != current_user.school_profile.id:
        raise HTTPException(status_code=403, detail="Not authorized to update this class")

    # Ensure the section is linked to the class and belongs to the same school
    section_obj = db.query(Section).filter(
        Section.id == section_id,
        Section.school_id == current_user.school_profile.id
    ).first()
    if not section_obj or section_obj not in class_obj.sections:
        raise HTTPException(status_code=404, detail="Section not found or not linked to this class")

    # Update start and end time
    if data.start_time:
        class_obj.start_time = data.start_time
    if data.end_time:
        class_obj.end_time = data.end_time

    # Update assigned teachers
    if data.assigned_teacher_ids:
        class_obj.assigned_teachers = db.query(Teacher).filter(
            Teacher.id.in_(data.assigned_teacher_ids),
            Teacher.school_id == current_user.school_profile.id
        ).all()

    # Update extra curricular activities
    if data.extra_activity_ids:
        class_obj.extra_curricular_activities = db.query(ExtraCurricularActivity).filter(
            ExtraCurricularActivity.id.in_(data.extra_activity_ids),
            ExtraCurricularActivity.school_id == current_user.school_profile.id
        ).all()

    # ✅ Update mandatory subjects
    if data.mandatory_subject_ids is not None:
        db.execute(class_subjects.delete().where(class_subjects.c.class_id == class_id))
        # Insert new ones
        for subject_id in data.mandatory_subject_ids:
            db.execute(class_subjects.insert().values(
                class_id=class_id,
                subject_id=subject_id
            ))

    # ✅ Update optional subjects (new many-to-many table)
    if data.optional_subject_ids is not None:
        # First clear old optional subjects
        db.execute(delete(class_optional_subjects).where(class_optional_subjects.class_id == class_id))
        # Insert new ones
        for subject_id in data.optional_subject_ids:
            db.execute(insert(class_optional_subjects).values(
                            class_id=class_id,
                            subject_id=subject_id
                        ))


    db.commit()
    db.refresh(class_obj)
    return {"detail": "Class section details updated successfully"}

@router.get("/school-classes/")
def get_school_classes(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role not in [UserRole.SCHOOL, UserRole.TEACHER]:
        raise HTTPException(status_code=403, detail="Only school and teacher users can access this resource.")

    if current_user.role == UserRole.SCHOOL:
        # Get the school associated with the current user
        school = db.query(School).filter(School.user_id == current_user.id).first()
        if not school:
            raise HTTPException(status_code=404, detail="School not found for this user.")

    elif current_user.role == UserRole.TEACHER:
        # Get teacher record
        teacher = db.query(Teacher).filter(Teacher.user_id == current_user.id).first()
        if not teacher:
            raise HTTPException(status_code=404, detail="Teacher not found for this user.")

        # Use the school_id from teacher
        school = db.query(School).filter(School.id == teacher.school_id).first()
        if not school:
            raise HTTPException(status_code=404, detail="School not found for this teacher.")

    # Common query for both roles
    classes = db.query(Class).filter(Class.school_id == school.id).all()

    if not classes:
        raise HTTPException(status_code=404, detail="No classes found for this school.")

    return [
        {
            "class_id": class_.id,
            "class_name": class_.name,
        }
        for class_ in classes
    ]


@router.get("/classes/")
def get_classes(
    limit: int = 10,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Allow both SCHOOL and TEACHER
    if current_user.role not in [UserRole.SCHOOL, UserRole.TEACHER]:
        raise HTTPException(status_code=403, detail="Only school and teacher users can access this resource.")

    # Get the school_id based on role
    if current_user.role == UserRole.SCHOOL:
        school = db.query(School).filter(School.user_id == current_user.id).first()
        if not school:
            raise HTTPException(status_code=404, detail="School not found for this user.")
        school_id = school.id

    elif current_user.role == UserRole.TEACHER:
        teacher = db.query(Teacher).filter(Teacher.user_id == current_user.id).first()
        if not teacher:
            raise HTTPException(status_code=404, detail="Teacher profile not found.")
        school_id = teacher.school_id

    # Query classes of this school
    classes = (
        db.query(Class)
        .options(joinedload(Class.sections))
        .options(joinedload(Class.subjects))
        .filter(Class.school_id == school_id)
        .offset(offset)
        .limit(limit)
        .all()
    )

    response = []
    sl_no = offset + 1

    for class_ in classes:
        for section in class_.sections:
            student_count = db.query(func.count(Student.id)).filter(
                Student.class_id == class_.id,
                Student.section_id == section.id,
                Student.school_id == school_id
            ).scalar()

            teacher_assignments = (
                db.query(Teacher)
                .join(TeacherClassSectionSubject)
                .filter(
                    TeacherClassSectionSubject.class_id == class_.id,
                    TeacherClassSectionSubject.section_id == section.id,
                    TeacherClassSectionSubject.school_id == school_id
                )
                .all()
            )

            teacher_names = [f"{teacher.first_name}" for teacher in teacher_assignments]

            # exam count for this class + section
            exam_count = (
                db.query(func.count(Exam.id))
                .join(Exam.sections)   # join exam_sections association
                .filter(
                    Exam.class_id == class_.id,
                    Section.id == section.id,
                    Exam.school_id == school_id
                )
                .scalar()
            )

            response.append({
                "sl_no": sl_no,
                "class_id": class_.id,
                "class_name": class_.name,
                "section_name": section.name,
                "subjects": [subject.name for subject in class_.subjects],
                "teachers": teacher_names,
                "students": student_count,
                "exams":exam_count,
                "start_time": class_.start_time.strftime("%H:%M") if class_.start_time else None,
                "end_time": class_.end_time.strftime("%H:%M") if class_.end_time else None,
            })
            sl_no += 1

    return response


@router.get("/time-table/")
def get_time_table(
    limit: int = 10,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    response = []

    # ---------- School User ----------
    if current_user.role == UserRole.SCHOOL:
        school = db.query(School).filter(School.user_id == current_user.id).first()
        if not school:
            raise HTTPException(status_code=404, detail="School not found for this user.")

        timetables = (
            db.query(Timetable)
            .options(joinedload(Timetable.days))
            .filter(Timetable.school_id == school.id)
            .offset(offset)
            .limit(limit)
            .all()
        )

        for timetable in timetables:
            class_ = db.query(Class).filter(Class.id == timetable.class_id).first()
            section = db.query(Section).filter(Section.id == timetable.section_id).first()

            student_count = db.query(func.count(Student.id)).filter(
                Student.class_id == class_.id,
                Student.section_id == section.id,
                Student.school_id == school.id
            ).scalar()

            teacher_assignments = db.query(TeacherClassSectionSubject).filter(
                TeacherClassSectionSubject.class_id == class_.id,
                TeacherClassSectionSubject.section_id == section.id,
                TeacherClassSectionSubject.school_id == school.id
            ).all()

            response.append({
                "timetable_id": timetable.id,
                "class_id": class_.id,
                "class_name": class_.name,
                "section_id": section.id,
                "section_name": section.name,
                "students": student_count,
                "teachers": len(teacher_assignments),
                "is_published": timetable.is_published,
                "published_at": timetable.published_at,
                "days_count": len(timetable.days)
            })

    # ---------- Teacher User ----------
    elif current_user.role == UserRole.TEACHER:
        teacher = db.query(Teacher).filter(Teacher.user_id == current_user.id).first()
        if not teacher:
            raise HTTPException(status_code=404, detail="Teacher profile not found.")

        assignments = db.query(TeacherClassSectionSubject).filter(
            TeacherClassSectionSubject.teacher_id == teacher.id,
            TeacherClassSectionSubject.school_id == teacher.school_id
        ).all()

        if not assignments:
            raise HTTPException(status_code=404, detail="No class-section assignments found for this teacher.")

        for assignment in assignments:
            timetable = (
                db.query(Timetable)
                .options(joinedload(Timetable.days))
                .filter(
                    Timetable.class_id == assignment.class_id,
                    Timetable.section_id == assignment.section_id,
                    Timetable.school_id == assignment.school_id,
                    Timetable.is_published == True  # ✅ Only published
                )
                .first()
            )

            if timetable:
                class_ = db.query(Class).filter(Class.id == timetable.class_id).first()
                section = db.query(Section).filter(Section.id == timetable.section_id).first()

                student_count = db.query(func.count(Student.id)).filter(
                    Student.class_id == class_.id,
                    Student.section_id == section.id,
                    Student.school_id == teacher.school_id
                ).scalar()

                response.append({
                    "timetable_id": timetable.id,
                    "class_id": class_.id,
                    "class_name": class_.name,
                    "section_id": section.id,
                    "section_name": section.name,
                    "students": student_count,
                    "is_published": timetable.is_published,
                    "published_at": timetable.published_at,
                    "days_count": len(timetable.days)
                })

    else:
        raise HTTPException(status_code=403, detail="Only school or teacher users can access this resource.")

    if not response:
        raise HTTPException(status_code=404, detail="No timetables found.")

    return response


@router.put("/time-table/{timetable_id}/publish")
def publish_timetable(
    timetable_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role != UserRole.SCHOOL:
        raise HTTPException(status_code=403, detail="Only school users can access this resource.")

    # Get the school associated with the current user
    school = db.query(School).filter(School.user_id == current_user.id).first()
    if not school:
        raise HTTPException(status_code=404, detail="School not found for this user.")

    # Fetch the timetable
    timetable = db.query(Timetable).filter(
        Timetable.id == timetable_id,
        Timetable.school_id == school.id
    ).first()

    if not timetable:
        raise HTTPException(status_code=404, detail="Timetable not found.")

    # Publish timetable (set timetable-level flag)
    timetable.is_published = True
    timetable.published_at = func.now()

    # Also mark all days as published
    for day in timetable.days:
        day.is_published = True
        day.published_at = func.now()

    try:
        db.commit()
        db.refresh(timetable)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to publish timetable: {str(e)}")

    return {
        "detail": "Timetable published successfully"
    }

          
@router.get("/timetable/{timetable_id}/periods/")
@router.get("/timetable/{timetable_id}/periods/")
def get_timetable_periods(
    timetable_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.SCHOOL, UserRole.TEACHER))
):
    # If school user → verify school ownership
    if current_user.role == UserRole.SCHOOL:
        school = db.query(School).filter(School.user_id == current_user.id).first()
        if not school:
            raise HTTPException(status_code=404, detail="School not found for this user.")

        timetable = db.query(Timetable).filter(
            Timetable.id == timetable_id,
            Timetable.school_id == school.id
        ).first()

        if not timetable:
            raise HTTPException(status_code=404, detail="Timetable not found for this school.")

    # If teacher user → only allow published timetable
    elif current_user.role == UserRole.TEACHER:
        timetable = db.query(Timetable).filter(
            Timetable.id == timetable_id,
            Timetable.is_published == True   # ✅ only published ones
        ).first()

        if not timetable:
            raise HTTPException(status_code=404, detail="Published timetable not found.")

    # Fetch timetable days + periods
    timetable_days = (
        db.query(TimetableDay)
        .options(
            joinedload(TimetableDay.periods)
            .joinedload(TimetablePeriod.subject),
            joinedload(TimetableDay.periods)
            .joinedload(TimetablePeriod.teacher)
        )
        .filter(TimetableDay.timetable_id == timetable.id)
        .order_by(TimetableDay.day)
        .all()
    )

    if not timetable_days:
        raise HTTPException(status_code=404, detail="No days found for this timetable.")

    # Build response
    response = []
    for day in timetable_days:
        day_data = {
            "day": day.day.name,
            "periods": []
        }

        for period in sorted(day.periods, key=lambda p: p.start_time):
            day_data["periods"].append({
                "id": period.id,
                "day_id": period.day_id,
                "start_time": period.start_time.strftime("%H:%M"),
                "end_time": period.end_time.strftime("%H:%M"),
                "subject_name": period.subject.name if period.subject else None,
                "teacher_name": f"{period.teacher.first_name} {period.teacher.last_name}" if period.teacher else None
            })

        response.append(day_data)

    return response

@router.get("/student/timetable/periods/")
def get_student_timetable_periods(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Ensure only student role can access
    if current_user.role != UserRole.STUDENT:
        raise HTTPException(
            status_code=403,
            detail="Only students can access their timetable."
        )

    # Get student profile
    student = db.query(Student).filter(Student.user_id == current_user.id).first()
    if not student:
        raise HTTPException(
            status_code=404,
            detail="Student profile not found."
        )

    # Extract school_id, class_id, section_id from student profile
    school_id = student.school_id
    class_id = student.class_id
    section_id = student.section_id

    # Fetch timetable for that class + section + school
    timetable = db.query(Timetable).filter(
        Timetable.class_id == class_id,
        Timetable.section_id == section_id,
        Timetable.school_id == school_id
    ).first()

    if not timetable:
        raise HTTPException(
            status_code=404,
            detail="Timetable not found for your class and section."
        )

    # Fetch timetable days + periods
    timetable_days = (
        db.query(TimetableDay)
        .options(
            joinedload(TimetableDay.periods)
            .joinedload(TimetablePeriod.subject),
            joinedload(TimetableDay.periods)
            .joinedload(TimetablePeriod.teacher)
        )
        .filter(TimetableDay.timetable_id == timetable.id)
        .order_by(TimetableDay.day)
        .all()
    )

    if not timetable_days:
        raise HTTPException(
            status_code=404,
            detail="No days found for this timetable."
        )

    # Build response
    response = []
    for day in timetable_days:
        day_data = {
            "day": day.day.name,  # e.g., "MONDAY"
            "periods": []
        }

        for period in sorted(day.periods, key=lambda p: p.start_time):
            day_data["periods"].append({
                "id": period.id,
                "day_id": period.day_id,
                "start_time": period.start_time.strftime("%H:%M"),
                "end_time": period.end_time.strftime("%H:%M"),
                "subject_name": period.subject.name if period.subject else None,
                "teacher_name": f"{period.teacher.first_name} {period.teacher.last_name}" if period.teacher else None
            })

        response.append(day_data)

    return response

@router.get("/sections/")
def get_sections(
    class_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role not in [UserRole.SCHOOL, UserRole.TEACHER]:
        raise HTTPException(status_code=403, detail="Only school or teacher users can access this resource.")
    # Get school for SCHOOL users
    if current_user.role == UserRole.SCHOOL:
        school = db.query(School).filter(School.user_id == current_user.id).first()
        if not school:
            raise HTTPException(status_code=404, detail="School not found for this user.")
        school_id = school.id

    # Get school for TEACHER users
    elif current_user.role == UserRole.TEACHER:
        school = db.query(School).join(School.teachers).filter(User.id == current_user.id).first()
        if not school:
            raise HTTPException(status_code=404, detail="School not found for this teacher.")
        school_id = school.id


    section_query = db.query(Section).join(
        class_section, class_section.c.section_id == Section.id
    ).filter(
        class_section.c.class_id == class_id,
        Section.school_id == school.id
    )
    if sections := section_query.all():
        return [
            {
                "section_id": section.id,
                "section_name": section.name
            }
            for section in sections
        ]
    else:
        raise HTTPException(status_code=404, detail="No sections found for this class.")
    
@router.get("/subjects/")
def get_subjects(
    class_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role != UserRole.SCHOOL:
        raise HTTPException(status_code=403, detail="Only school users can access this resource.")
    
    # Get the school associated with the current user
    school = db.query(School).filter(School.user_id == current_user.id).first()
    if not school:
        raise HTTPException(status_code=404, detail="School not found for this user.")

    subjects = db.query(Subject).join(
        class_subjects, class_subjects.c.subject_id == Subject.id
    ).filter(
        class_subjects.c.class_id == class_id,
        Subject.school_id == school.id
    ).all()
    if not subjects:
        raise HTTPException(status_code=404, detail="No subjects found for this class.")
    return [
        {
            "subject_id": subject.id,
            "subject_name": subject.name
        }
        for subject in subjects
    ]    
@router.post("/transports/")
def create_transport(
    data: TransportCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.role != UserRole.SCHOOL:
        raise HTTPException(status_code=403, detail="Only schools can create transport records.")

    # Get school profile
    school = db.query(School).filter(School.id == current_user.school_profile.id).first()
    if not school:
        raise HTTPException(status_code=400, detail="School profile not found.")

    # Check for duplicate vehicle
    existing = db.query(Transport).filter(
        Transport.vechicle_number == data.vehicle_number,
        Transport.school_id == school.id
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Transport with this vehicle number already exists.")

    transport = Transport(
        vechicle_number=data.vehicle_number,
        vechicle_name=data.vehicle_name,
        driver_name=data.driver_name,
        phone_no=data.phone_no,
        duty_start_time=data.duty_start_time,
        duty_end_time=data.duty_end_time,
        school_id=school.id)
    db.add(transport)
    db.flush()
    # Add pickup stops
    for stop in data.pickup_stops:
        pickup = PickupStop(
            stop_name=stop.stop_name,
            stop_time=stop.stop_time,
            transport_id=transport.id
        )
        db.add(pickup)
    for stop in data.drop_stops:
        drop = DropStop(
            stop_name=stop.stop_name,
            stop_time=stop.stop_time,
            transport_id=transport.id
        )
        db.add(drop)
    db.commit()
    db.refresh(transport)        

    return {"detail": "Transport created successfully", "transport_id": transport.id}

@router.get("/transport/{driver_id}", response_model=TransportResponse)
def get_transport_detail(
    driver_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(require_roles(UserRole.SCHOOL, UserRole.TEACHER)),
):
    # Determine school_id
    if current_user.role == UserRole.SCHOOL:
        school_id = current_user.school_profile.id
    else:
        school_id = current_user.teacher_profile.school_id

    # Query transport by driver_id & school_id
    transport = db.query(Transport).filter(
        Transport.id == driver_id,
        Transport.school_id == school_id
    ).first()

    if not transport:
        raise HTTPException(
            status_code=404,
            detail="Transport with this vehicle number not found for your school."
        )

    # Return transport details
    return TransportResponse(
        driver_id=transport.id,
        vehicle_number=transport.vechicle_number,
        vehicle_name=transport.vechicle_name,
        driver_name=transport.driver_name,
        phone_no=transport.phone_no,
        duty_start_time=transport.duty_start_time.strftime("%H:%M"),
        duty_end_time=transport.duty_end_time.strftime("%H:%M"),
        school_id=transport.school_id,
        pickup_stops=[
            StopResponse(stop_name=s.stop_name, stop_time=s.stop_time.strftime("%H:%M"))
            for s in transport.pickup_stops
        ],
        drop_stops=[
            StopResponse(stop_name=s.stop_name, stop_time=s.stop_time.strftime("%H:%M"))
            for s in transport.drop_stops
        ],
    )

@router.get("/transports/")
def get_transports(
    pagination: PaginationParams = Depends(),
    db: Session = Depends(get_db),
    current_user = Depends(require_roles(UserRole.SCHOOL, UserRole.TEACHER))
):
    school_id = current_user.school_profile.id if current_user.role == UserRole.SCHOOL else current_user.teacher_profile.school_id

    query = db.query(Transport).filter(Transport.school_id == school_id)
    total_count = query.count()

    transports = query.offset(pagination.offset()).limit(pagination.limit()).all()

    data = [
        {
            "driver_id": t.id,
            "vehicle_number": t.vechicle_number,
            "vehicle_name": t.vechicle_name,
            "driver_name": t.driver_name,
            "phone_no": t.phone_no,
            "duty_start_time": t.duty_start_time.strftime("%H:%M"),
            "duty_end_time": t.duty_end_time.strftime("%H:%M"),
            "school_id": t.school_id,
        }
        for t in transports
    ]

    return pagination.format_response(data, total_count)
@router.get("/school-dashboard/")
def get_school_dashboard(
    db: Session = Depends(get_db),
    current_user = Depends(require_roles(UserRole.SCHOOL, UserRole.TEACHER))
):
    if current_user.role == UserRole.SCHOOL:
        school_id = current_user.school_profile.id
    else:
        school_id = current_user.teacher_profile.school_id

    # Get school by school_id (not user_id, for TEACHER this fails)
    school = db.query(School).filter(School.id == school_id).first()

    if not school:
        raise HTTPException(status_code=404, detail="School not found.")

    # Count entities based on same school_id
    student_count = db.query(Student).filter(Student.school_id == school_id).count()
    teacher_count = db.query(Teacher).filter(Teacher.school_id == school_id).count()
    class_count = db.query(Class).filter(Class.school_id == school_id).count()
    transport_count = db.query(Transport).filter(Transport.school_id == school_id).count()
    exam_count=db.query(Exam).filter(Exam.school_id==school_id).count()

    return {
        "school_name": school.school_name,
        "student_count": student_count,
        "teacher_count": teacher_count,
        "class_count": class_count,
        "exam_count": exam_count,
        "transport_count": transport_count,
    }
    
@router.post("/attendance/", status_code=201)
def create_attendance(
    data: AttendanceCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(UserRole.SCHOOL, UserRole.TEACHER)),
):
    start = timer()
    try:
        # Teacher Attendance
        if data.teachers_id:
            if current_user.role == UserRole.SCHOOL:
                teacher = db.query(Teacher).filter(
                    Teacher.id == data.teachers_id,
                    Teacher.school_id == current_user.school_profile.id
                ).first()
                if not teacher:
                    raise HTTPException(status_code=404, detail="Teacher not found or not in your school.")
            
            elif current_user.role == UserRole.TEACHER:
                if current_user.teacher_profile.id != data.teachers_id:
                    raise HTTPException(status_code=403, detail="Teachers can only mark their own attendance.")

            existing = db.query(Attendance).filter_by(
                teachers_id=data.teachers_id,
                date=data.date
            ).first()
            if existing:
                raise HTTPException(status_code=400, detail="Attendance already recorded for this teacher on this date.")

            is_verified = False  # must be verified later by school

        # Student Attendance
        elif data.student_id:
            school_id = (
                current_user.school_profile.id if current_user.role == UserRole.SCHOOL
                else current_user.teacher_profile.school_id if current_user.role == UserRole.TEACHER
                else None
            )
            if not school_id:
                raise HTTPException(status_code=403, detail="Unauthorized user.")

            student = db.query(Student).filter(
                Student.id == data.student_id,
                Student.school_id == school_id
            ).first()
            if not student:
                raise HTTPException(status_code=404, detail="Student not found or not in your school.")

            existing = db.query(Attendance).filter_by(
                student_id=data.student_id,
                date=data.date
            ).first()
            if existing:
                raise HTTPException(status_code=400, detail="Attendance already recorded for this student on this date.")

            is_verified = True  # student attendance does not need verification

        attendance = Attendance(
            student_id=data.student_id,
            teachers_id=data.teachers_id,
            date=data.date,
            status=data.status,
            is_verified=is_verified
        )
        db.add(attendance)
        db.commit()
        db.refresh(attendance)

        end = timer()
        return {
            "detail": "Attendance recorded successfully",
            "id": attendance.id,
            "time_taken": round(end - start, 4)
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")
    
@router.post("/attendance/teacher-attendance/verify/{attendance_id}") 
def verify_teacher_attendance(
    attendance_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(UserRole.SCHOOL)),
):
    attendance = db.query(Attendance).filter(
        Attendance.id == attendance_id,
        Attendance.teachers_id.isnot(None)
    ).first()

    if not attendance:
        raise HTTPException(status_code=404, detail="Teacher attendance not found.")

    if attendance.is_verified:
        raise HTTPException(status_code=400, detail="Attendance already verified.")

    attendance.is_verified = True
    db.commit()
    db.refresh(attendance)

    return {"detail": "Teacher attendance verified successfully."}   
@router.get("/student/{student_id}/month/{year}/{month}")
def get_student_attendance_monthwise(student_id: int, year: int, month: int, db: Session = Depends(get_db)):
    import calendar
    from datetime import date, datetime

    today = datetime.today().date()
    days_in_month = calendar.monthrange(year, month)[1]

    # End date should be min(last day of month, today)
    end_day = days_in_month if (year, month) < (today.year, today.month) else min(today.day, days_in_month)

    start_date = date(year, month, 1)
    end_date = date(year, month, end_day)

    records = db.query(Attendance).filter(
        Attendance.student_id == student_id,
        Attendance.date.between(start_date, end_date)
    ).all()

    record_map = {r.date: r.status for r in records}

    status_list = [
        record_map.get(date(year, month, day), "A")
        for day in range(1, end_day + 1)
    ]

    return {
        "student_id": student_id,
        "month": f"{year}-{month:02}",
        "attendance": status_list
    }
@router.get("/teacher/{teacher_id}/month/{year}/{month}")
def get_teacher_attendance_monthwise(
    teacher_id: str,  # string to allow codes like "TCH-116102"
    year: int,
    month: int,
    db: Session = Depends(get_db)
):
    import calendar
    from datetime import date, datetime

    today = datetime.today().date()
    days_in_month = calendar.monthrange(year, month)[1]

    # End date should be min(last day of month, today)
    end_day = days_in_month if (year, month) < (today.year, today.month) else min(today.day, days_in_month)

    start_date = date(year, month, 1)
    end_date = date(year, month, end_day)

    # Fetch attendance records
    records = db.query(Attendance).filter(
        Attendance.teachers_id == teacher_id,
        Attendance.date.between(start_date, end_date)
    ).all()

    record_map = {r.date: r.status for r in records}

    # Build day-wise status list
    status_list = [
        record_map.get(date(year, month, day), "A")  # default "A" if no record
        for day in range(1, end_day + 1)
    ]

    return {
        "teacher_id": teacher_id,
        "month": f"{year}-{month:02}",
        "attendance": status_list
    }
@router.post("/create-time-table/")
def create_timetable(
    data: TimetableCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role != "school":
        raise HTTPException(status_code=403, detail="Only schools can create timetables.")
    
    school = db.query(School).filter(School.id == current_user.school_profile.id).first()
    if not school:
        raise HTTPException(status_code=400, detail="School profile not found.")

    # ✅ Get or create the timetable for this class + section
    timetable = db.query(Timetable).filter_by(
        school_id=school.id,
        class_id=data.class_id,
        section_id=data.section_id
    ).first()

    if not timetable:
        timetable = Timetable(
            school_id=school.id,
            class_id=data.class_id,
            section_id=data.section_id
        )
        db.add(timetable)
        db.flush()  # assign timetable.id

    # ✅ Check if the day already exists
    timetable_day = db.query(TimetableDay).filter_by(
        timetable_id=timetable.id,
        day=data.day
    ).first()

    if not timetable_day:
        timetable_day = TimetableDay(
            timetable_id=timetable.id,
            day=data.day
        )
        db.add(timetable_day)
        db.flush()  # assign timetable_day.id

    # ✅ Validate overlaps inside the same request
    for i, new_period in enumerate(data.periods):
        for j, compare_period in enumerate(data.periods):
            if i != j and is_time_overlap(
                new_period.start_time, new_period.end_time,
                compare_period.start_time, compare_period.end_time
            ):
                raise HTTPException(
                    status_code=400,
                    detail=f"Conflict: {new_period.start_time}–{new_period.end_time} overlaps with {compare_period.start_time}–{compare_period.end_time}"
                )

    # ✅ Validate teacher assignments and add periods
    for period in data.periods:
        teacher_assignment = db.query(TeacherClassSectionSubject).filter_by(
            school_id=school.id,
            class_id=data.class_id,
            section_id=data.section_id,
            subject_id=period.subject_id,
            teacher_id=period.teacher_id
        ).first()

        if not teacher_assignment:
            raise HTTPException(
                status_code=400,
                detail=f"Teacher {period.teacher_id} is not assigned to Class {data.class_id}, "
                       f"Section {data.section_id}, Subject {period.subject_id}"
            )

        period_entry = TimetablePeriod(
            day_id=timetable_day.id,
            subject_id=period.subject_id,
            teacher_id=period.teacher_id,
            start_time=period.start_time,
            end_time=period.end_time
        )
        db.add(period_entry)

    db.commit()
    return {"detail": f"Timetable for Class {data.class_id} Section {data.section_id} updated/created for {data.day} successfully."}



@router.put("/timetable/{timetable_id}")
def update_timetable(
    timetable_id: int,
    data: TimetableUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role != "school":
        raise HTTPException(status_code=403, detail="Only schools can update timetables.")

    school = current_user.school_profile
    if not school:
        raise HTTPException(status_code=400, detail="School profile not found.")

    # ✅ Get the base timetable (one per class + section)
    timetable = db.query(Timetable).filter_by(
        id=timetable_id,
        school_id=school.id
    ).first()

    if not timetable:
        raise HTTPException(status_code=404, detail="Timetable not found.")

    # ✅ Find or create the day
    day = db.query(TimetableDay).filter_by(
        timetable_id=timetable.id,
        day=data.day
    ).first()

    if not day:
        day = TimetableDay(
            timetable_id=timetable.id,
            day=data.day
        )
        db.add(day)
        db.flush()  # assign day.id

    # ✅ Get existing periods for that day
    existing_periods = db.query(TimetablePeriod).filter_by(day_id=day.id).all()

    for new_period in data.periods:
        # 🔹 Validate teacher assignment
        teacher_assignment = db.query(TeacherClassSectionSubject).filter_by(
            school_id=school.id,
            class_id=timetable.class_id,
            section_id=timetable.section_id,
            subject_id=new_period.subject_id,
            teacher_id=new_period.teacher_id
        ).first()

        if not teacher_assignment:
            raise HTTPException(
                status_code=400,
                detail=f"Teacher {new_period.teacher_id} is not assigned to "
                       f"Class {timetable.class_id}, Section {timetable.section_id}, "
                       f"Subject {new_period.subject_id}"
            )

        # 🔹 Check conflicts with existing periods
        for existing in existing_periods:
            if is_time_overlap(
                new_period.start_time, new_period.end_time,
                existing.start_time, existing.end_time
            ):
                raise HTTPException(
                    status_code=400,
                    detail=f"Conflict with existing period {existing.start_time}-{existing.end_time}"
                )

        # 🔹 Add new period (NO school_id here)
        db.add(TimetablePeriod(
            day_id=day.id,
            subject_id=new_period.subject_id,
            teacher_id=new_period.teacher_id,
            start_time=new_period.start_time,
            end_time=new_period.end_time
        ))

    db.commit()
    db.refresh(day)

    return {"detail": f"Timetable updated for {day.day}"}

@router.get("/account-credit/configuration/")
def get_account_credit_configuration(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role != UserRole.SCHOOL:
        raise HTTPException(status_code=403, detail="Only school users can access this resource.")

    # Get the school associated with the current user
    school = db.query(School).filter(School.user_id == current_user.id).first()
    if not school:
        raise HTTPException(status_code=404, detail="School not found for this user.")

    if configs := db.query(CreditConfiguration).all():
        return [
            {
            "id": config.id,
            "standard_name": config.standard_name,
            "monthly_credit": config.monthly_credit,
            "margin_up_to": config.margin_up_to
            }
            for config in configs
        ]
    else:
        raise HTTPException(status_code=404, detail="Credit configuration not found for this school.") 
    
@router.post("/school-credit/configuration/")
def create_school_credit_configuration(
    data: CreateSchoolCredit,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role != UserRole.SCHOOL:
        raise HTTPException(status_code=403, detail="Only school users can create credit configurations.")

    try:
        # Get the school associated with the current user
        school = db.query(School).filter(School.user_id == current_user.id).first()
        if not school:
            raise HTTPException(status_code=404, detail="School not found for this user.")

        # Ensure class_id belongs to the same school
        class_obj = db.query(Class).filter(
            Class.id == data.class_id,
            Class.school_id == school.id
        ).first()

        if not class_obj:
            raise HTTPException(
                status_code=400,
                detail=f"Class ID {data.class_id} does not exist for your school."
            )

        # Get the admin's credit configuration
        admin_credit_config = db.query(CreditConfiguration).filter(
            CreditConfiguration.id == data.credit_configuration_id
        ).first()

        if not admin_credit_config:
            raise HTTPException(status_code=404, detail="Credit configuration not found.")

        # Check if requested margin is within admin limit
        if data.margin_value > admin_credit_config.margin_up_to:
            raise HTTPException(
                status_code=400,
                detail=f"Margin value cannot exceed admin's allowed limit of {admin_credit_config.margin_up_to}."
            )

        # Check if configuration already exists for this class and credit config
        existing_config = db.query(SchoolMarginConfiguration).filter(
            SchoolMarginConfiguration.class_id == data.class_id,
            SchoolMarginConfiguration.school_id == school.id,
            SchoolMarginConfiguration.credit_configuration_id == data.credit_configuration_id
        ).first()

        if existing_config:
            raise HTTPException(
                status_code=400,
                detail="Credit configuration for this class already exists for your school."
            )

        # Create new configuration
        new_config = SchoolMarginConfiguration(
            class_id=data.class_id,
            margin_value=data.margin_value,
            credit_configuration_id=data.credit_configuration_id,
            school_id=school.id
        )

        db.add(new_config)
        db.commit()
        db.refresh(new_config)

        return {
            "detail": f"Credit configuration created successfully for {admin_credit_config.standard_name}"
        }

    except IntegrityError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Integrity error: {str(e.orig)}")

    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")

@router.post("/create-payment-order")
def create_payment_order(
    data: CreatePaymentRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role != UserRole.SCHOOL:
        raise HTTPException(status_code=403, detail="Only school users can create payment orders.")

    # Get school
    school = db.query(School).filter(School.user_id == current_user.id).first()
    if not school:
        raise HTTPException(status_code=404, detail="School not found for this user.")

    amount_in_paise = int(data.amount * 100)

    # Create Razorpay order
    payment_order = razorpay_client.order.create({
        "amount": amount_in_paise,
        "currency": "INR",
        "payment_capture": 1
    })

    # Save transaction history with status PENDING
    transaction = TransactionHistory(
        school_id=school.id,
        amount=data.amount,
        transaction_id="",
        order_id=payment_order["id"],
        status="PENDING"
    )
    db.add(transaction)
    db.commit()
    db.refresh(transaction)

    return {
        "order_id": payment_order["id"],
        "amount": data.amount,
        "currency": "INR",
        "transaction_db_id": transaction.id 
    }  
@router.post("/verify-payment")
def verify_payment(
    data: PaymentVerificationRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role != UserRole.SCHOOL:
        raise HTTPException(status_code=403, detail="Only school users can verify payment.")

    # Generate signature to verify
    generated_signature = hmac.new(
        bytes(settings.RAZORPAY_KEY_SECRET, 'utf-8'),
        bytes(f"{data.razorpay_order_id}|{data.razorpay_payment_id}", 'utf-8'),
        hashlib.sha256
    ).hexdigest()

    # Fetch the transaction by order_id
    transaction = db.query(TransactionHistory).filter(
        TransactionHistory.order_id == data.razorpay_order_id
    ).first()

    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found.")

    if generated_signature != data.razorpay_signature:
        # Update transaction status to FAILED
        transaction.transaction_id = data.razorpay_payment_id
        transaction.status = "FAILED"
        db.commit()
        raise HTTPException(status_code=400, detail="Invalid payment signature.")

    # If payment is verified, add credit to the school
    school = db.query(School).filter(School.user_id == current_user.id).first()
    if not school:
        raise HTTPException(status_code=404, detail="School not found for this user.")

    credit_master = db.query(CreditMaster).filter(CreditMaster.school_id == school.id).first()
    if not credit_master:
        raise HTTPException(status_code=404, detail="Credit master not found for this school.")

    # Update school credit
    credit_master.self_added_credit += data.amount
    credit_master.available_credit += data.amount

    # Update transaction status to SUCCESS
    transaction.transaction_id = data.razorpay_payment_id
    transaction.status = "SUCCESS"

    db.commit()

    return {"detail": "Payment verified and credit added successfully."}    
# @router.post("/school-credit/add/")
# def add_school_credit(
#     data: AddSchoolCredit,
#     db: Session = Depends(get_db),
#     current_user: User = Depends(get_current_user)
# ):
#     if current_user.role != UserRole.SCHOOL:
#         raise HTTPException(status_code=403, detail="Only school users can add credit.")

#     # Get the school associated with the current user
#     school = db.query(School).filter(School.user_id == current_user.id).first()
#     if not school:
#         raise HTTPException(status_code=404, detail="School not found for this user.")

#     # Check if credit master exists for this school
#     credit_master = db.query(CreditMaster).filter(CreditMaster.school_id == school.id).first()
#     if not credit_master:
#         raise HTTPException(status_code=404, detail="Credit master not found for this school.")

#     # Add self-added credit
#     credit_master.self_added_credit += data.self_added_credit
#     db.commit()
#     return {"detail": "Credit added successfully."}

@router.post("/school-credit/transfer/")
def transfer_school_credit(
    data: TransferSchoolCredit,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role != UserRole.SCHOOL:
        raise HTTPException(status_code=403, detail="Only school users can transfer credit.")

    # Get the sender's school
    sender_school = db.query(School).filter(School.user_id == current_user.id).first()
    if not sender_school:
        raise HTTPException(status_code=404, detail="Sender school not found.")

    # Get the sender's credit master
    sender_credit = db.query(CreditMaster).filter(CreditMaster.school_id == sender_school.id).first()
    if not sender_credit:
        raise HTTPException(status_code=404, detail="Credit master not found for sender school.")

    # Ensure sender has enough credit
    if sender_credit.available_credit < data.credit_amount:
        raise HTTPException(status_code=400, detail="Insufficient available credit for transfer.")

    # Get the receiver's credit master
    receiver_credit = db.query(CreditMaster).filter(CreditMaster.school_id == data.receiver_school_id).first()
    if not receiver_credit:
        raise HTTPException(status_code=404, detail="Credit master not found for receiver school.")
    # Perform the transfer
    sender_credit.transfer_credit += data.credit_amount
    receiver_credit.earned_credit += data.credit_amount

    # Recalculate available credits if needed
    # sender_credit.available_credit -= data.credit_amount
    # receiver_credit.available_credit += data.credit_amount
    db.commit()

    return {"detail": "Credit transferred successfully."}


#Exam Modules
@router.post("/create-exam/", status_code=status.HTTP_201_CREATED)
def create_exam(
    data: ExamCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role != UserRole.TEACHER:
        raise HTTPException(status_code=403, detail="Only teachers can create exams.")

    teacher = db.query(Teacher).filter(Teacher.user_id == current_user.id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher profile not found.")

    # ✅ Enforce business logic
    max_repeat = 1 if data.exam_type == "rank" else data.max_repeat

    try:
        # ✅ Fetch actual Section objects
        section_objs = db.query(Section).filter(Section.id.in_(data.sections)).all()
        if not section_objs:
            raise HTTPException(status_code=404, detail="No valid sections found.")

        exam = Exam(
            school_id=teacher.school_id,
            class_id=data.class_id,
            chapters=data.chapters,
            exam_type=data.exam_type,
            no_of_questions=data.no_of_questions,
            question_time=data.question_time,
            pass_percentage=data.pass_percentage,
            exam_activation_date=data.exam_activation_date,
            inactive_date=data.inactive_date,
            max_repeat=max_repeat,
            status=data.status,
            created_by=teacher.id,
            sections=section_objs
        )

        db.add(exam)
        db.commit()
        db.refresh(exam)

        return {
            "detail": "Exam created successfully.",
            "exam_id": exam.id
        }

    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    
@router.get("/exams/", response_model=List[ExamListResponse])
def list_exams(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role == UserRole.SCHOOL:
        school = db.query(School).filter(School.user_id == current_user.id).first()
        if not school:
            raise HTTPException(status_code=404, detail="School not found")
        
        exams = (
            db.query(Exam)
            .filter(
                Exam.school_id == school.id,
                Exam.is_published == True
            )
            .all()
        )

    elif current_user.role == UserRole.TEACHER:
        teacher = db.query(Teacher).filter(Teacher.user_id == current_user.id).first()
        exams = db.query(Exam).filter(Exam.created_by == teacher.id).all()

    elif current_user.role == UserRole.STUDENT:
        student = db.query(Student).filter(Student.user_id == current_user.id).first()
        if not student:
            raise HTTPException(status_code=404, detail="Student profile not found")
    
        exams = (
            db.query(Exam)
            .join(Exam.sections)
            .filter(
                Exam.school_id == student.school_id,
                Exam.class_id == student.class_id,
                Section.id == student.section_id,
                Exam.status == ExamStatusEnum.ACTIVE,
                Exam.is_published == True
            )
            .all()
        )

    else:
        raise HTTPException(status_code=403, detail="Invalid role for viewing exams.")

    # Serialize response
    response = [
        ExamListResponse(
            id=exam.id,
            exam_type=exam.exam_type,
            class_id=exam.class_id,
            standard=exam.class_obj.name if exam.class_obj else "",
            section_ids=[section.id for section in exam.sections],
            section_names=[section.name for section in exam.sections],
            chapters=exam.chapters,
            no_of_chapters=len(exam.chapters),
            no_of_questions=exam.no_of_questions,
            exam_time=exam.no_of_questions * exam.question_time if exam.no_of_questions and exam.question_time else 0,
            pass_percentage=exam.pass_percentage,
            exam_activation_date=exam.exam_activation_date,
            inactive_date=exam.inactive_date,
            max_repeat=exam.max_repeat,
            status=exam.status,
            no_students_appeared=exam.no_students_appeared,
            created_by=f"{exam.teacher.first_name} {exam.teacher.last_name}" if exam.teacher else "",
            created_at=exam.created_at
        )
        for exam in exams
    ]
    return response
@router.get("/exams/{exam_id}/", response_model=ExamDetailResponse)
def get_exam_detail(
    exam_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")

    # 🏫 School user access
    if current_user.role == UserRole.SCHOOL:
        school = db.query(School).filter(School.user_id == current_user.id).first()
        if not school:
            raise HTTPException(status_code=404, detail="School not found")

        if exam.school_id != school.id:
            raise HTTPException(status_code=403, detail="Not authorized to view this exam")

    # 👨‍🏫 Teacher access
    elif current_user.role == UserRole.TEACHER:
        teacher = db.query(Teacher).filter(Teacher.user_id == current_user.id).first()
        if not teacher:
            raise HTTPException(status_code=404, detail="Teacher not found")

        if exam.created_by != teacher.id:
            raise HTTPException(status_code=403, detail="You can only view exams you created")

    # 👨‍🎓 Student access
    elif current_user.role == UserRole.STUDENT:
        student = db.query(Student).filter(Student.user_id == current_user.id).first()
        if not student:
            raise HTTPException(status_code=404, detail="Student not found")

        if (
            exam.school_id != student.school_id
            or exam.class_id != student.class_id
            or not any(s.id == student.section_id for s in exam.sections)
            or exam.status != ExamStatusEnum.ACTIVE
            or not exam.is_published
        ):
            raise HTTPException(status_code=403, detail="You are not allowed to view this exam")

    else:
        raise HTTPException(status_code=403, detail="Invalid role for viewing exam details")

    # ✅ Build response
    return ExamDetailResponse(
        id=exam.id,
        exam_type=exam.exam_type,
        school_id=exam.school_id,
        class_id=exam.class_id,
        standard=exam.class_obj.name if exam.class_obj else "",
        section_ids=[section.id for section in exam.sections],
        section_names=[section.name for section in exam.sections],
        chapters=exam.chapters,
        no_of_chapters=len(exam.chapters),
        no_of_questions=exam.no_of_questions,
        exam_time=exam.no_of_questions * exam.question_time if exam.no_of_questions and exam.question_time else 0,
        pass_percentage=exam.pass_percentage,
        exam_activation_date=exam.exam_activation_date,
        inactive_date=exam.inactive_date,
        max_repeat=exam.max_repeat,
        status=exam.status,
        no_students_appeared=exam.no_students_appeared,
        created_by=f"{exam.teacher.first_name} {exam.teacher.last_name}" if exam.teacher else "",
        created_at=exam.created_at
    )

@router.put("/exam/{exam_id}")
def update_exam(
    exam_id: str,
    data: ExamUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Only school users should be allowed to update
    if current_user.role != "school":
        raise HTTPException(status_code=403, detail="Not authorized to update exam")

    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")

    # update only provided fields
    update_data = data.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(exam, key, value)

    # enforce business rule
    if data.exam_type == "rank":
        exam.max_repeat = 1

    db.commit()
    db.refresh(exam)
    return exam


# ✅ Delete Exam
@router.delete("/exams/{exam_id}", status_code=status.HTTP_200_OK)
def delete_exam(
    exam_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found.")

    # ✅ Role-based access
    if current_user.role == UserRole.TEACHER:
        teacher = db.query(Teacher).filter(Teacher.user_id == current_user.id).first()
        if not teacher or exam.created_by != teacher.id:
            raise HTTPException(status_code=403, detail="You can only delete your own exams.")
    elif current_user.role == UserRole.SCHOOL:
        school = db.query(School).filter(School.user_id == current_user.id).first()
        if not school or exam.school_id != school.id:
            raise HTTPException(status_code=403, detail="You can only delete exams in your school.")
    else:
        raise HTTPException(status_code=403, detail="Only teachers or admins can delete exams.")

    try:
        db.delete(exam)
        db.commit()
        return {"detail": "Exam deleted successfully."}
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/exams/{exam_id}/publish", response_model=ExamPublishResponse)
def publish_exam(
    exam_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)  # contains logged-in user info
):
    # ✅ Allow only TEACHERS
    if current_user.role != UserRole.TEACHER:
        raise HTTPException(status_code=403, detail="Only teachers can publish exams")

    # ✅ Get teacher object for logged-in user
    teacher = db.query(Teacher).filter(Teacher.user_id == current_user.id).first()
    if not teacher:
        raise HTTPException(status_code=403, detail="Teacher profile not found")

    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")

    if exam.is_published:
        raise HTTPException(status_code=400, detail="Exam already published")

    # ✅ Ensure the teacher publishing is the one who created it
    if exam.created_by != teacher.id:
        raise HTTPException(status_code=403, detail="You are not the creator of this exam")

    exam.is_published = True
    exam.exam_activation_date = datetime.utcnow()  # set activation time
    db.commit()
    db.refresh(exam)

    return {
        "exam_id": exam.id,
        "is_published": exam.is_published,
        "published_at": exam.exam_activation_date
    }

@router.put("/exams/{exam_id}/status", response_model=dict)
def update_exam_status(
    exam_id: str,
    data: ExamStatusUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # ✅ Only school users allowed
    if current_user.role != UserRole.SCHOOL:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only school users can update exam status"
        )
    
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")
    
    # ✅ Only allow ACTIVE or DECLINED
    if data.status not in [ExamStatusEnum.ACTIVE, ExamStatusEnum.DECLINED]:
        raise HTTPException(
            status_code=400,
            detail="Status can only be set to ACTIVE or DECLINED"
        )

    exam.status = data.status
    
    # Optional: set activation date when activating
    if data.status == ExamStatusEnum.ACTIVE:
        exam.exam_activation_date = datetime.utcnow()
    
    db.commit()
    db.refresh(exam)

    return {
        "exam_id": exam.id,
        "new_status": exam.status,
        "exam_activation_date": exam.exam_activation_date
    }
@router.post("/exam/{exam_id}/mcqs", response_model=List[McqResponse])
def add_mcqs(
    exam_id: str,
    mcq_bulk: McqBulkCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role not in [UserRole.SCHOOL, UserRole.TEACHER]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only school or teacher can add MCQs"
        )
    try:
        return create_mcq(db, exam_id, mcq_bulk)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    
@router.put("/{mcq_id}/")
def update_mcq(
    mcq_id: int,
    mcq_update: McqCreate,  # reuse schema
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # only school or teacher can update
    if current_user.role not in ["school", "teacher"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    mcq = db.query(McqBank).filter(McqBank.id == mcq_id).first()
    if not mcq:
        raise HTTPException(status_code=404, detail="MCQ not found")

    mcq.question = mcq_update.question
    mcq.mcq_type = mcq_update.mcq_type
    mcq.image = mcq_update.image
    mcq.option_a = mcq_update.option_a
    mcq.option_b = mcq_update.option_b
    mcq.option_c = mcq_update.option_c
    mcq.option_d = mcq_update.option_d
    mcq.correct_option = mcq_update.correct_option
    mcq.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(mcq)
    return mcq


@router.delete("/{mcq_id}")
def delete_mcq_endpoint(
    mcq_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in [UserRole.TEACHER]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only school or teacher can delete MCQs"
        )
    success = delete_mcq(db, mcq_id)
    if not success:
        raise HTTPException(status_code=404, detail="MCQ not found")
    return {"detail": "MCQ deleted successfully"}
@router.get("/exam/{exam_id}")
def fetch_mcqs(exam_id: str, db: Session = Depends(get_db),current_user: User = Depends(get_current_user)):
    if current_user.role not in [UserRole.SCHOOL, UserRole.TEACHER,UserRole.STUDENT]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only school or teacher can fetch MCQs"
        )
    mcqs = get_mcqs_by_exam(db, exam_id)
    if current_user.role == UserRole.STUDENT:
        return [
            {
                "id": mcq.id,
                "exam_id": mcq.exam_id,
                "question": mcq.question,
                "mcq_type": mcq.mcq_type,
                "image": mcq.image,
                "option_a": mcq.option_a,
                "option_b": mcq.option_b,
                "option_c": mcq.option_c,
                "option_d": mcq.option_d,
            }
            for mcq in mcqs
        ]

    # For school and teacher, return full rows from DB
    return mcqs

@router.post("/{exam_id}/submit")
def submit_exam(
    exam_id: str,
    submission: StudentExamSubmitRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role != UserRole.STUDENT:
        raise HTTPException(status_code=403, detail="Only students can submit exams")

    student_profile = current_user.student_profile
    if not student_profile:
        raise HTTPException(status_code=400, detail="Student profile not found")

    # Last attempt check
    last_attempt = (
        db.query(StudentExamData)
        .filter(
            StudentExamData.student_id == student_profile.id,
            StudentExamData.exam_id == exam_id
        )
        .order_by(StudentExamData.attempt_no.desc())
        .first()
    )
    next_attempt_no = last_attempt.attempt_no + 1 if last_attempt else 1

    # Fetch questions
    mcqs = db.query(McqBank).filter(McqBank.exam_id == exam_id).all()
    mcq_map = {mcq.id: mcq for mcq in mcqs}

    correct_count = 0
    total = len(submission.answers)

    for ans in submission.answers:
        mcq = mcq_map.get(ans.question_id)
        if mcq:
            correct_options = mcq.correct_option
            selected_options = ans.selected_option

        # Normalize: ensure both are lists
            if not isinstance(correct_options, list):
                correct_options = [correct_options]
            if not isinstance(selected_options, list):
                selected_options = [selected_options]

        # Count correct matches
            matched = [opt for opt in selected_options if opt in correct_options]

            if matched:
                correct_count += len(matched)
    result_percentage = (correct_count / total * 100) if total > 0 else 0
    status_result = "pass" if result_percentage >= 40 else "fail"

    # Save result
    student_exam_data = StudentExamData(
        student_id=student_profile.id,
        school_id=student_profile.school_id,
        exam_id=exam_id,
        attempt_no=next_attempt_no,
        answers=[ans.dict() for ans in submission.answers],
        result=result_percentage,
        status=status_result,
        submitted_at=datetime.utcnow()
    )
    db.add(student_exam_data)
    db.commit()
    db.refresh(student_exam_data)

    # ✅ Update rank in class
    update_class_ranks(db, exam_id, student_profile.class_id)

    return {
        "detail": "Exam submitted successfully",
        "exam_id": exam_id,
        "attempt_no": next_attempt_no,
        "result": result_percentage,
        "status": status_result
    }

@router.post("/leave-request/")
def create_leave_request(
    request: LeaveCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    print("🔹 create_leave_request called")
    print(f"🔹 request.attach_file: {request.attach_file}")
    if current_user.role not in [UserRole.TEACHER, UserRole.STUDENT]:
        raise HTTPException(status_code=403, detail="Only teacher or student can request leave")

    attach_file_url = None
    if request.attach_file:
        print("🔹 attach_file exists, uploading to S3...")
        attach_file_url = upload_base64_to_s3(
            base64_string=request.attach_file,
            filename_prefix="leave_request"
        )
        print(f"🔹 attach_file_url: {attach_file_url}")
        if not attach_file_url:
            raise HTTPException(status_code=500, detail="Failed to upload attachment")

    if current_user.role == UserRole.TEACHER:
        teacher = db.query(Teacher).filter(Teacher.user_id == current_user.id).first()
        school_id = teacher.school_id
        leave = LeaveRequest(
            subject=request.subject,
            start_date=request.start_date,
            end_date=request.end_date,
            description=request.description,
            status=LeaveStatus.PENDING,
            teacher_id=teacher.id,
            student_id=None,
            school_id=school_id,
            attach_file=attach_file_url
        )
    else:
        student = db.query(Student).filter(Student.user_id == current_user.id).first()
        school_id = student.school_id
        leave = LeaveRequest(
            subject=request.subject,
            start_date=request.start_date,
            end_date=request.end_date,
            description=request.description,
            status=LeaveStatus.PENDING,
            student_id=student.id,
            teacher_id=None,
            school_id=school_id,
            attach_file=attach_file_url
        )

    db.add(leave)
    db.commit()
    db.refresh(leave)

    return {
        "status": "success",
        "message": "Leave request sent successfully",
        "data": {
            "leave_id": leave.id,
            "subject": leave.subject,
            "start_date": leave.start_date,
            "end_date": leave.end_date,
            "status": leave.status.value,
            "school_id": leave.school_id,
            "attach_file": leave.attach_file  # now this should show the S3 URL
        }
    }

@router.get("/leave-request/")
def get_all_leaves(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    School user can see all leave requests (teachers + students) with user info.
    """
    if current_user.role != UserRole.SCHOOL:
        raise HTTPException(status_code=403, detail="Only school users can view all leave requests")

    leaves = db.query(LeaveRequest).order_by(LeaveRequest.id.desc()).all()

    result = []
    for leave in leaves:
        if leave.teacher_id:
            user_id = leave.teacher_id
            user_name = f"{leave.teacher.first_name} {leave.teacher.last_name}"
            role = "TEACHER"
        elif leave.student_id:
            user_id = leave.student_id
            user_name = f"{leave.student.first_name} {leave.student.last_name}"
            role = "STUDENT"
        else:
            user_id = None
            user_name = None
            role = None

        result.append({
            "id": leave.id,
            "subject": leave.subject,
            "start_date": leave.start_date,
            "end_date": leave.end_date,
            "status": leave.status.value,  # Enum to string
            "role": role,
            "user_id": user_id,
            "user_name": user_name
        })

    return {
        "status": "success",
        "total": len(result),
        "data": result
    }



@router.get("/leave-request/{leave_id}/")
def get_leave_by_id(
    leave_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """
    Get details of a specific leave request with user info.
    """
    if current_user.role != UserRole.SCHOOL:
        raise HTTPException(status_code=403, detail="Only school users can view leave details")

    leave = db.query(LeaveRequest).filter(LeaveRequest.id == leave_id).first()
    if not leave:
        raise HTTPException(status_code=404, detail="Leave request not found")

    if leave.teacher_id:
        user_id = leave.teacher_id
        user_name = f"{leave.teacher.first_name} {leave.teacher.last_name}"
        role = "TEACHER"
    elif leave.student_id:
        user_id = leave.student_id
        user_name = f"{leave.student.first_name} {leave.student.last_name}"
        role = "STUDENT"
    else:
        user_id = None
        user_name = None
        role = None

    return {
        "status": "success",
        "data": {
            "id": leave.id,
            "subject": leave.subject,
            "start_date": leave.start_date,
            "end_date": leave.end_date,
            "description": leave.description,
            "attach_file": leave.attach_file,
            "status": leave.status.value,
            "role": role,
            "user_id": user_id,
            "user_name": user_name,
            "school_id": leave.school_id
        }
    }


@router.put("/leave-request/{leave_id}/")
def update_leave_status(
    leave_id: int,
    status: LeaveStatusUpdate,  # Pydantic model
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """
    School can approve or decline leave requests and return full leave info.
    """
    if current_user.role != UserRole.SCHOOL:
        raise HTTPException(status_code=403, detail="Only school users can update leave status")

    leave = db.query(LeaveRequest).filter(LeaveRequest.id == leave_id).first()
    if not leave:
        raise HTTPException(status_code=404, detail="Leave request not found")

    status_value = status.status.lower()  # extract string from model

    if status_value not in ["approved", "declined"]:
        raise HTTPException(status_code=400, detail="Invalid status. Must be 'approved' or 'declined'")

    leave.status = LeaveStatus.APPROVED if status_value == "approved" else LeaveStatus.DECLINED
    db.commit()
    db.refresh(leave)

    # Determine user info
    if leave.teacher_id:
        user_id = leave.teacher_id
        user_name = f"{leave.teacher.first_name} {leave.teacher.last_name}"
        role = "TEACHER"
    elif leave.student_id:
        user_id = leave.student_id
        user_name = f"{leave.student.first_name} {leave.student.last_name}"
        role = "STUDENT"
    else:
        user_id = None
        user_name = None
        role = None

    return {
        "status": "success",
        "message": f"Leave request has been {status_value} successfully"
    }
