from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException,status,UploadFile,File,Query,Form
from app.models.users import User
from app.models.teachers import Teacher,TeacherClassSectionSubject
from app.models.students import Student
from app.models.school import School,Class,Section,Subject,ExtraCurricularActivity,class_extra_curricular,class_section,class_subjects,class_optional_subjects,Transport,PickupStop,DropStop,Attendance,TimetableDay,TimetablePeriod,SchoolMarginConfiguration,TransactionHistory,Exam,McqBank,ExamStatusEnum,ExamStatus,StudentExamData
from app.models.admin import AccountConfiguration, CreditConfiguration, CreditMaster
from app.schemas.users import UserRole
from app.schemas.school import ClassWithSubjectCreate,ClassInput,TransportCreate,TransportResponse,StopResponse,AttendanceCreate,PeriodCreate,TimetableCreate,CreateSchoolCredit,TransferSchoolCredit,CreatePaymentRequest,PaymentVerificationRequest,ExamCreateRequest,ExamUpdateRequest,ExamListResponse,McqCreate,McqBulkCreate,McqResponse,ExamPublishResponse,ExamStatusUpdateRequest,StudentExamSubmitRequest
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

    return {"message": "School profile updated successfully"}


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
        "message": "Class created successfully with all associated data",
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
    return {"message": "Class section details updated successfully"}

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

            response.append({
                "sl_no": sl_no,
                "class_id": class_.id,
                "class_name": class_.name,
                "section_name": section.name,
                "subjects": [subject.name for subject in class_.subjects],
                "teachers": teacher_names,
                "students": student_count,
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
    if current_user.role != UserRole.SCHOOL:
        raise HTTPException(status_code=403, detail="Only school users can access this resource.")
    # Get the school associated with the current user
    school = db.query(School).filter(School.user_id == current_user.id).first()
    if not school:
        raise HTTPException(status_code=404, detail="School not found for this user.")
    classes = (
        db.query(Class)
        .options(joinedload(Class.sections))
        .filter(Class.school_id == school.id)
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
                Student.school_id == school.id
            ).scalar()
            
            teacher_assignments = db.query(Teacher).join(TeacherClassSectionSubject).filter(
                TeacherClassSectionSubject.class_id == class_.id,
                TeacherClassSectionSubject.section_id == section.id,
                TeacherClassSectionSubject.school_id == school.id
            ).all()
            response.append({
                "sl_no": sl_no,
                "class_id": class_.id,
                "class_name": class_.name,
                "section_name": section.name,
                "teachers": len(teacher_assignments),
                "students":student_count,
                "is_published": "pending",
                "published_at":"pending"
            })
            sl_no += 1
    return response       
@router.get("/class/{class_id}/timetable/{section_id}/periods/")
def get_class_timetable_periods(
    class_id: int,
    section_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role != UserRole.SCHOOL:
        raise HTTPException(status_code=403, detail="Only school users can access this resource.")

    school = db.query(School).filter(School.user_id == current_user.id).first()
    if not school:
        raise HTTPException(status_code=404, detail="School not found for this user.")

    # Fetch timetable days for this class/section/school
    timetable_days = (
        db.query(TimetableDay)
        .options(joinedload(TimetableDay.periods).joinedload(TimetablePeriod.subject), 
                 joinedload(TimetableDay.periods).joinedload(TimetablePeriod.teacher))
        .filter(
            TimetableDay.class_id == class_id,
            TimetableDay.section_id == section_id,
            TimetableDay.school_id == school.id
        )
        .order_by(TimetableDay.day)
        .all()
    )

    if not timetable_days:
        raise HTTPException(status_code=404, detail="No timetable found for this class and section.")

    response = []
    for day in timetable_days:
        day_data = {
            "day": day.day.name,  # e.g., "MONDAY"
            "periods": []
        }

        for period in sorted(day.periods, key=lambda p: p.start_time):
            day_data["periods"].append({
                "id": period.id,
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

    return {"message": "Transport created successfully", "transport_id": transport.id}

@router.get("/transports-list/", response_model=List[TransportResponse])
def get_transports_list(
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(UserRole.SCHOOL, UserRole.TEACHER))
):
    if current_user.role == UserRole.SCHOOL:
        school_id = current_user.school_profile.id
    else:
        school_id = current_user.teacher_profile.school_id

    transports = db.query(Transport).filter(Transport.school_id == school_id).all()

    if not transports:
        raise HTTPException(status_code=404, detail="No transports found for this school.")

    return [
        TransportResponse(
            id=t.id,
            vehicle_number=t.vechicle_number,
            vehicle_name=t.vechicle_name,
            driver_name=t.driver_name,
            phone_no=t.phone_no,
            duty_start_time=t.duty_start_time.strftime("%H:%M"),
            duty_end_time=t.duty_end_time.strftime("%H:%M"),
            school_id=t.school_id,
            pickup_stops=[
                StopResponse(stop_name=s.stop_name, stop_time=s.stop_time.strftime("%H:%M"))
                for s in t.pickup_stops
            ],
            drop_stops=[
                StopResponse(stop_name=s.stop_name, stop_time=s.stop_time.strftime("%H:%M"))
                for s in t.drop_stops
            ],
        )
        for t in transports
    ]

@router.get("/transports/")
def get_transports(
    vechicle_number: str,
    db: Session = Depends(get_db),
    current_user = Depends(require_roles(UserRole.SCHOOL, UserRole.TEACHER))
):
    if current_user.role == UserRole.SCHOOL:
        school_id = current_user.school_profile.id
    else:
        school_id = current_user.teacher_profile.school_id

    transport = db.query(Transport).filter(
        Transport.vechicle_number == vechicle_number,
        Transport.school_id == school_id
    ).first()

    if not transport:
        raise HTTPException(
            status_code=404,
            detail="Transport with this vehicle number not found for your school."
        )

    return {
        "vehicle_number": transport.vechicle_number,
        "driver_name": transport.driver_name,
        "phone_no": transport.phone_no,
        "duty_start_time": transport.duty_start_time.strftime("%H:%M"),
        "duty_end_time": transport.duty_end_time.strftime("%H:%M"),
        "school_id": transport.school_id
    }

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

    return {
        "school_name": school.school_name,
        "student_count": student_count,
        "teacher_count": teacher_count,
        "class_count": class_count,
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
                subject_id=data.subject_id,
                class_id=data.class_id,
                section_id=data.section_id,
                date=data.date
            ).first()
            if existing:
                raise HTTPException(status_code=400, detail="Attendance already recorded for this teacher on this subject, class, section, and date.")
            
            data.is_verified = False
        if data.student_id:
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
                subject_id=data.subject_id,
                date=data.date
            ).first()
            if existing:
                raise HTTPException(status_code=400, detail="Attendance already recorded for this student for this subject and date.")
            data.is_verified = True

        attendance = Attendance(**data.model_dump())
        db.add(attendance)
        db.commit()
        db.refresh(attendance)

        end = timer()
        return {
            "message": "Attendance recorded successfully",
            "id": attendance.id,
            "time_taken": round(end - start, 4)
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")
    
@router.post("/attendance/teacher-attendance/verify/") 
def verify_teacher_attendance(
    attendance_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(UserRole.SCHOOL, UserRole.TEACHER)),
):
    if current_user.role != UserRole.SCHOOL:
        raise HTTPException(status_code=403, detail="Only school users can verify teacher attendance.")

    attendance = db.query(Attendance).filter(
        Attendance.id == attendance_id,
        Attendance.teachers_id.isnot(None)
    ).first()

    if not attendance:
        raise HTTPException(status_code=404, detail="Attendance record not found or not a teacher's attendance.")

    if attendance.is_verified:
        raise HTTPException(status_code=400, detail="Attendance already verified.")

    attendance.is_verified = True
    db.commit()
    db.refresh(attendance)

    return {"message": "Teacher attendance verified successfully."}   
@router.get("/attendance/monthly-summary/")
def get_attendance_summary(
    student_id: int = Query(None),
    teachers_id: str = Query(None),
    subject_id: int = Query(None),
    class_id: int = Query(None),
    section_id: int = Query(None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not student_id and not teachers_id:
        raise HTTPException(status_code=400, detail="Provide either student_id or teachers_id.")

    school_id = None
    if current_user.role == UserRole.SCHOOL:
        school_id = current_user.school_profile.id
    elif current_user.role == UserRole.TEACHER:
        school_id = current_user.teacher_profile.school_id
    else:
        raise HTTPException(status_code=403, detail="Unauthorized user.")

    # Month map (1–12 → January–December)
    month_map = {i: month_name[i] for i in range(1, 13)}
    status_per_month = {month_map[i]: [] for i in range(1, 13)}  # initialize empty lists

    # === Student Attendance ===
    if student_id:
        student = db.query(Student).filter(
            Student.id == student_id,
            Student.school_id == school_id
        ).first()
        if not student:
            raise HTTPException(status_code=404, detail="Student not found or not in your school.")
        
        if not subject_id:
            raise HTTPException(status_code=400, detail="subject_id is required with student_id")

        records = db.query(
            extract('month', Attendance.date).label('month'),
            Attendance.status
        ).filter(
            Attendance.student_id == student_id,
            Attendance.subject_id == subject_id
        ).all()

        for month, status in records:
            month_name_str = month_map[month]
            status_per_month[month_name_str].append(status)

        return {
            "student_id": student_id,
            "subject_id": subject_id,
            "monthly_status": status_per_month
        }

    # === Teacher Attendance ===
    if teachers_id:
        teacher = db.query(Teacher).filter(
            Teacher.id == teachers_id,
            Teacher.school_id == school_id
        ).first()
        if not teacher:
            raise HTTPException(status_code=404, detail="Teacher not found or not in your school.")

        if not class_id or not section_id:
            raise HTTPException(status_code=400, detail="class_id and section_id required for teacher attendance")

        records = db.query(
            extract('month', Attendance.date).label('month'),
            Attendance.status
        ).filter(
            Attendance.teachers_id == teachers_id,
            Attendance.class_id == class_id,
            Attendance.section_id == section_id
        ).all()

        for month, status in records:
            month_name_str = month_map[month]
            status_per_month[month_name_str].append(status)

        return {
            "teachers_id": teachers_id,
            "class_id": class_id,
            "section_id": section_id,
            "monthly_status": status_per_month
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

    # Check if the timetable day exists
    timetable_day = db.query(TimetableDay).filter_by(
        class_id=data.class_id,
        section_id=data.section_id,
        day=data.day
    ).first()

    if not timetable_day:
        timetable_day = TimetableDay(
            school_id=school.id,
            class_id=data.class_id,
            section_id=data.section_id,
            day=data.day
        )
        db.add(timetable_day)
        db.flush()

    # Fetch existing periods for that day
    existing_periods = db.query(TimetablePeriod).filter_by(day_id=timetable_day.id).all()

    for new_period in data.periods:
        for existing in existing_periods:
            if is_time_overlap(
                new_period.start_time, new_period.end_time,
                existing.start_time, existing.end_time
            ):
                raise HTTPException(
                    status_code=400,
                    detail=f"Time conflict with an existing period from {existing.start_time} to {existing.end_time}"
                )

    # Add valid periods
    for period in data.periods:
        period_entry = TimetablePeriod(
            day_id=timetable_day.id,
            school_id=school.id,
            subject_id=period.subject_id,
            teacher_id=period.teacher_id,
            start_time=period.start_time,
            end_time=period.end_time
        )
        db.add(period_entry)

    db.commit()
    return {"message": "Timetable created successfully."}   

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
            "message": f"Credit configuration created successfully for {admin_credit_config.standard_name}"
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

    return {"message": "Payment verified and credit added successfully."}    
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
#     return {"message": "Credit added successfully."}

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

    return {"message": "Credit transferred successfully."}


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
            pass_percentage=data.pass_percentage,
            exam_activation_date=data.exam_activation_date,
            inactive_date=data.inactive_date,
            max_repeat=max_repeat,
            status=data.status,
            created_by=teacher.id,
            sections=section_objs   # ✅ assign objects not IDs
        )

        db.add(exam)
        db.commit()
        db.refresh(exam)

        return {
            "message": "Exam created successfully.",
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
    elif current_user.role == UserRole.ADMIN:
        school = db.query(School).filter(School.user_id == current_user.id).first()
        if not school or exam.school_id != school.id:
            raise HTTPException(status_code=403, detail="You can only delete exams in your school.")
    else:
        raise HTTPException(status_code=403, detail="Only teachers or admins can delete exams.")

    try:
        db.delete(exam)
        db.commit()
        return {"message": "Exam deleted successfully."}
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

    
@router.put("/exam/{mcq_id}", response_model=McqResponse)
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
    return {"message": "MCQ deleted successfully"}
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
    submission: StudentExamSubmitRequest,   # only `answers` now
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role != UserRole.STUDENT:
        raise HTTPException(status_code=403, detail="Only students can submit exams")

    # ✅ Get student profile (every student belongs to a school)
    student_profile = current_user.student_profile
    if not student_profile:
        raise HTTPException(status_code=400, detail="Student profile not found")

    # Find last attempt for this student & exam
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

    # Fetch exam questions
    mcqs = db.query(McqBank).filter(McqBank.exam_id == exam_id).all()
    mcq_map = {mcq.id: mcq for mcq in mcqs}

    correct_count = 0
    total = len(submission.answers)

    for ans in submission.answers:
        mcq = mcq_map.get(ans.question_id)
        if mcq and mcq.correct_option == ans.selected_option:
            correct_count += 1

    result_percentage = (correct_count / total * 100) if total > 0 else 0
    status_result = "pass" if result_percentage >= 40 else "fail"  # threshold

    # Save result
    student_exam_data = StudentExamData(
        student_id=student_profile.id,               # ✅ from student profile
        school_id=student_profile.school_id,         # ✅ school comes from student profile
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

    return {
        "message": "Exam submitted successfully",
        "exam_id": exam_id,
        "attempt_no": next_attempt_no,
        "result": result_percentage,
        "status": status_result
    }