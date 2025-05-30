from fastapi import APIRouter, Depends, HTTPException,status,UploadFile,File,Query
from app.models.users import User
from app.models.teachers import Teacher,TeacherClassSectionSubject
from app.models.students import Student
from app.models.school import School,Class,Section,Subject,ExtraCurricularActivity,class_extra_curricular,class_section,class_subjects,class_optional_subjects,Transport,PickupStop,DropStop,Attendance,TimetableDay,TimetablePeriod
from app.schemas.users import UserRole
from app.schemas.school import SchoolProfileUpdate,ClassWithSubjectCreate,ClassInput,TransportCreate,TransportResponse,StopResponse,AttendanceCreate,PeriodCreate,TimetableCreate
from sqlalchemy.orm import Session,joinedload
from sqlalchemy import delete, insert,extract
from app.db.session import get_db
from app.core.dependencies import get_current_user
from app.utils.permission import require_roles
from typing import List,Optional
from app.utils.s3 import upload_to_s3
from calendar import month_name
from sqlalchemy import func
router = APIRouter()
@router.patch("/school-profile")
async def update_school_profile(
    profile_data: SchoolProfileUpdate = Depends(),
    profile_pic: Optional[UploadFile] = File(None),
    banner_pic: Optional[UploadFile] = File(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.role != UserRole.SCHOOL:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only school users can update school profiles"
        )
    
    profile = current_user.school_profile
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="School profile not found"
        )

    # ✅ Upload images and set directly on profile
    if profile_pic:
        try:
            profile.profile_pic_url = upload_to_s3(profile_pic, f"schools/{current_user.id}/profile")
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to upload profile picture: {str(e)}"
            )

    if banner_pic:
        try:
            profile.banner_pic_url = upload_to_s3(banner_pic, f"schools/{current_user.id}/banner")
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to upload banner picture: {str(e)}"
            )

    # ✅ Update only provided fields
    update_data = profile_data.dict(exclude_unset=True)
    if 'country' in update_data and update_data['country'] is None:
        update_data['country'] = "India"
    
    for field, value in update_data.items():
        setattr(profile, field, value)

    # ✅ Update User table if needed
    if 'school_name' in update_data:
        current_user.name = update_data['school_name']
    if 'school_email' in update_data:
        current_user.email = update_data['school_email']
    if 'school_phone' in update_data:
        current_user.phone = update_data['school_phone']

    try:
        db.add(profile)
        db.add(current_user)
        db.commit()
        db.refresh(profile)
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Database error: {str(e)}"
        )

    return profile


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
    if current_user.role != UserRole.SCHOOL:
        raise HTTPException(status_code=403, detail="Only school users can access this resource.")
    
    # Get the school associated with the current user
    school = db.query(School).filter(School.user_id == current_user.id).first()
    if not school:
        raise HTTPException(status_code=404, detail="School not found for this user.")

    classes = (
        db.query(Class)
        .filter(Class.school_id == school.id)
        .all()
    )

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
    if current_user.role != UserRole.SCHOOL:
        raise HTTPException(status_code=403, detail="Only school users can access this resource.")
    
    # Get the school associated with the current user
    school = db.query(School).filter(School.user_id == current_user.id).first()
    if not school:
        raise HTTPException(status_code=404, detail="School not found for this user.")

    classes = (
        db.query(Class)
        .options(joinedload(Class.sections))
        .options(joinedload(Class.subjects))
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

            teacher_names = [
                f"{teacher.first_name}" for teacher in teacher_assignments
            ]
            response.append({
                "sl_no": sl_no,
                "class_id": class_.id,
                "class_name": class_.name,
                "section_name": section.name,
                "subjects": [subject.name for subject in class_.subjects],
                "teachers": teacher_names,
                "students":student_count,
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
    
@router.get("/sections/")
def get_sections(
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

    sections = db.query(Section).join(
        class_section, class_section.c.section_id == Section.id
    ).filter(
        class_section.c.class_id == class_id,
        Section.school_id == school.id
    ).all()

    if not sections:
        raise HTTPException(status_code=404, detail="No sections found for this class.")

    return [
        {
            "section_id": section.id,
            "section_name": section.name
        }
        for section in sections
    ]
    
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
        school_id=data.school_id)
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
    vehicle_number: str,
    db: Session = Depends(get_db),
    current_user = Depends(require_roles(UserRole.SCHOOL, UserRole.TEACHER))
):
    if current_user.role == UserRole.SCHOOL:
        school_id = current_user.school_profile.id
    else:
        school_id = current_user.teacher_profile.school_id

    transport = db.query(Transport).filter(
        Transport.vehicle_number == vehicle_number,
        Transport.school_id == school_id
    ).first()

    if not transport:
        raise HTTPException(
            status_code=404,
            detail="Transport with this vehicle number not found for your school."
        )

    return {
        "vehicle_number": transport.vehicle_number,
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
    current_user=Depends(get_current_user),
):
    # Teacher attendance — only school users can record
    if data.teachers_id:
        if current_user.role != UserRole.SCHOOL:
            raise HTTPException(status_code=403, detail="Only school users can record teacher attendance.")

        teacher = db.query(Teacher).filter(
            Teacher.id == data.teachers_id,
            Teacher.school_id == current_user.school_profile.id
        ).first()
        if not teacher:
            raise HTTPException(status_code=404, detail="Teacher not found or not in your school.")

        # Check for duplicate teacher attendance
        existing = db.query(Attendance).filter_by(
            teachers_id=data.teachers_id,
            subject_id=data.subject_id,
            class_id=data.class_id,
            section_id=data.section_id,
            date=data.date
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="Attendance already recorded for this teacher on this subject, class, section, and date.")

    # Student attendance — can be taken by both
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

        # Check for duplicate student attendance
        existing = db.query(Attendance).filter_by(
            student_id=data.student_id,
            subject_id=data.subject_id,
            date=data.date
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="Attendance already recorded for this student for this subject and date.")

    # Save the attendance
    attendance = Attendance(**data.model_dump())
    db.add(attendance)
    db.commit()
    db.refresh(attendance)

    return {"message": "Attendance recorded successfully", "id": attendance.id}

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
def create_timetable(data: TimetableCreate, db: Session = Depends(get_db),current_user: User = Depends(get_current_user)):
    if current_user.role != "school":
        raise HTTPException(status_code=403, detail="Only schools can create timetables.")
    school = db.query(School).filter(School.id == current_user.school_profile.id).first()
    if not school:
        raise HTTPException(status_code=400, detail="School profile not found.")
    # Check if the timetable already exists for the class, section, and day
    existing = db.query(TimetableDay).filter_by(
        class_id=data.class_id,
        section_id=data.section_id,
        day=data.day
    ).first()

    if existing:
        raise HTTPException(status_code=400, detail="Timetable already exists for this class/section/day.")

    # Create TimetableDay
    timetable_day = TimetableDay(
        school_id=school.id,
        class_id=data.class_id,
        section_id=data.section_id,
        day=data.day
    )
    db.add(timetable_day)
    db.flush()

    # Add periods
    for period in data.periods:
        period_entry = TimetablePeriod(
            day_id=timetable_day.id,
            school_id=school.id,
            period_number=period.period_number,
            subject_id=period.subject_id,
            teacher_id=period.teacher_id,
            start_time=period.start_time,
            end_time=period.end_time
        )
        db.add(period_entry)

    db.commit()
    return {"message": "Timetable created successfully."}    