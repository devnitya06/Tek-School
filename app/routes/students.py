from fastapi import APIRouter, Depends, HTTPException,status,Query,Body
from app.models.users import User,Otp
from app.models.students import Student,Parent,PresentAddress,PermanentAddress,StudentStatus
from app.models.school import School,Class,Section,Attendance,Transport,StudentExamData
from app.schemas.users import UserRole
from app.schemas.students import StudentCreateRequest,ParentWithAddressCreate,StudentUpdateRequest
from datetime import timezone
from sqlalchemy.orm import Session,joinedload,aliased
from sqlalchemy import func
from app.db.session import get_db
from app.utils.email_utility import generate_otp
from app.core.dependencies import get_current_user
from app.utils.permission import require_roles
from app.core.security import create_verification_token
from app.utils.email_utility import send_dynamic_email
from datetime import datetime, timedelta,date
from app.utils.s3 import upload_base64_to_s3
from app.services.pagination import PaginationParams
from app.models.admin import SchoolClassSubject,Chapter,ChapterVideo,ChapterImage,ChapterPDF,ChapterQnA,StudentChapterProgress
router = APIRouter()
@router.post("/students/create")
def create_student(
    data: StudentCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # ✅ Allow only SCHOOL or TEACHER
    if current_user.role not in [UserRole.SCHOOL, UserRole.TEACHER]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only schools or teachers can create students."
        )

    # ✅ Get the correct school_id based on the role
    if current_user.role == UserRole.SCHOOL:
        school = getattr(current_user, "school_profile", None)
        if not school:
            raise HTTPException(status_code=400, detail="School profile not found.")
        school_id = school.id
    else:  # current_user.role == UserRole.TEACHER
        teacher = getattr(current_user, "teacher_profile", None)
        if not teacher:
            raise HTTPException(status_code=400, detail="Teacher profile not found.")
        school_id = teacher.school_id

    # ✅ Check if email already exists
    existing = db.query(User).filter(User.email == data.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already exists.")

    # ✅ Validate transport if enabled
    if data.is_transport:
        if not data.driver_id:
            raise HTTPException(status_code=400, detail="Driver ID is required when transport is enabled.")
        driver = db.query(Transport).filter(
            Transport.id == data.driver_id,
            Transport.school_id == school_id
        ).first()
        if not driver:
            raise HTTPException(status_code=400, detail="Driver not found for the given ID.")

    try:
        # ✅ Upload student profile image (if provided)
        profile_pic_url = None
        if data.profile_image:
            try:
                profile_pic_url = upload_base64_to_s3(data.profile_image, f"students/{school_id}/profile")
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"S3 Upload failed: {str(e)}")

        # ✅ Create User for the student
        user = User(
            name=f"{data.first_name} {data.last_name}",
            email=data.email,
            role=UserRole.STUDENT
        )
        db.add(user)
        db.flush()  # ensures user.id is available

        # ✅ Create Student profile
        student = Student(
            first_name=data.first_name,
            last_name=data.last_name,
            gender=data.gender,
            dob=data.dob,
            roll_no=data.roll_no,
            class_id=data.class_id,
            section_id=data.section_id,
            is_transport=data.is_transport,
            driver_id=data.driver_id,
            user_id=user.id,
            school_id=school_id,
            profile_image=profile_pic_url,
            status=StudentStatus.TRIAL,
            status_expiry_date=datetime.utcnow() + timedelta(days=15)
        )

        db.add(student)
        db.commit()
        db.refresh(user)
        db.refresh(student)

        # ✅ Send verification email
        token = create_verification_token(user.id)
        verification_link = f"https://tek-school.learningmust.com/users/verify-account?token={token}"

        send_dynamic_email(
            context_key="account_verification.html",
            subject="Student Account Verification",
            recipient_email=user.email,
            context_data={
                "name": f"{data.first_name} {data.last_name}",
                "verification_link": verification_link,
            },
            db=db
        )

        return {
            "detail": "Student account created. Verification email sent.",
            "student_id": student.id,
            "user_id": user.id,
            "profile_pic_url": profile_pic_url
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create student: {str(e)}")

@router.post("/students/{student_id}/activate")
def activate_student(student_id: int, db: Session = Depends(get_db)):
    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    now = datetime.now(timezone.utc)
    if student.status in [StudentStatus.TRIAL, StudentStatus.INACTIVE]:
        student.status = StudentStatus.ACTIVE
        student.status_expiry_date = now + timedelta(days=90)
    elif student.status == StudentStatus.ACTIVE:
        # renewal payment → extend expiry
        student.status_expiry_date = (student.status_expiry_date or now) + timedelta(days=90)

    db.commit()
    db.refresh(student)

    return {"detail": f"Student activated until {student.status_expiry_date}"}
@router.post("/students/{student_id}/add-parent-info")
def add_parent_and_address(
    student_id: int,
    data: ParentWithAddressCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role != UserRole.SCHOOL:
        raise HTTPException(status_code=403, detail="Only schools can add parent and address data.")

    # Get school profile of the current user
    school = db.query(School).filter(School.id == current_user.school_profile.id).first()
    if not school:
        raise HTTPException(status_code=404, detail="School profile not found.")

    # Check student belongs to this school
    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found.")

    if student.classes.school_id != school.id:
        raise HTTPException(status_code=403, detail="You do not have permission to modify this student.")

    # Create parent
    parent = Parent(
        parent_name=data.parent.parent_name,
        relation=data.parent.relation,
        phone=data.parent.phone,
        email=data.parent.email,
        occupation=data.parent.occupation,
        organization=data.parent.organization,
        student_id=student_id
    )
    db.add(parent)

    # Create present address
    present = PresentAddress(
        enter_pin=data.present_address.enter_pin,
        division=data.present_address.division,
        district=data.present_address.district,
        state=data.present_address.state,
        country=data.present_address.country,
        building=data.present_address.building,
        house_no=data.present_address.house_no,
        floor_name=data.present_address.floor_name,
        is_this_permanent_as_well=data.present_address.is_this_permanent_as_well,
        student_id=student_id
    )
    db.add(present)

    # Create permanent address only if needed
    if not data.present_address.is_this_permanent_as_well:
        if data.permanent_address is None:
            raise HTTPException(status_code=400, detail="Permanent address required if not same as present.")
        permanent = PermanentAddress(
            enter_pin=data.permanent_address.enter_pin,
            division=data.permanent_address.division,
            district=data.permanent_address.district,
            state=data.permanent_address.state,
            country=data.permanent_address.country,
            building=data.permanent_address.building,
            house_no=data.permanent_address.house_no,
            floor_name=data.permanent_address.floor_name,
            student_id=student_id
        )
        db.add(permanent)

    db.commit()

    return {"detail": "Parent and address data added successfully."}

@router.get("/students/")
def get_students(
    pagination: PaginationParams = Depends(),
    db: Session = Depends(get_db),
    current_user = Depends(require_roles(UserRole.SCHOOL, UserRole.TEACHER)),
    roll_no: int | None = Query(None, description="Filter by roll number"),
    name: str | None = Query(None, description="Filter by student name"),
    class_name: str | None = Query(None, description="Filter by class name"),
):
    # Determine school_id
    if current_user.role == UserRole.SCHOOL:
        school_id = current_user.school_profile.id
    else:
        school_id = current_user.teacher_profile.school_id

    # --- Subqueries ---
    attendance_subquery = (
        db.query(
            Attendance.student_id,
            func.count(Attendance.id).label("attendance_count")
        )
        .group_by(Attendance.student_id)
        .subquery()
    )

    exam_count_subquery = (
        db.query(
            StudentExamData.student_id,
            func.count(StudentExamData.id).label("exam_count")
        )
        .group_by(StudentExamData.student_id)
        .subquery()
    )

    rank_subquery = (
        db.query(
            StudentExamData.student_id,
            func.max(StudentExamData.class_rank).label("latest_rank")
        )
        .group_by(StudentExamData.student_id)
        .subquery()
    )

    # --- Base Query ---
    base_query = (
        db.query(
            Student,
            attendance_subquery.c.attendance_count,
            exam_count_subquery.c.exam_count,
            rank_subquery.c.latest_rank,
        )
        .outerjoin(attendance_subquery, Student.id == attendance_subquery.c.student_id)
        .outerjoin(exam_count_subquery, Student.id == exam_count_subquery.c.student_id)
        .outerjoin(rank_subquery, Student.id == rank_subquery.c.student_id)
        .join(Class, Student.class_id == Class.id)
        .join(Section, Student.section_id == Section.id)
        .filter(Class.school_id == school_id)
        .options(
            joinedload(Student.classes),
            joinedload(Student.section)
        )
    )

    # --- Apply Filters ---
    if roll_no:
        base_query = base_query.filter(Student.roll_no==roll_no)
    if name:
        base_query = base_query.filter(
            func.concat(Student.first_name, " ", Student.last_name).ilike(f"%{name}%")
        )
    if class_name:
        base_query = base_query.filter(Class.name.ilike(f"%{class_name}%"))

    # --- Count & Pagination ---
    total_count = base_query.count()
    students = base_query.offset(pagination.offset()).limit(pagination.limit()).all()

    # --- Format Response ---
    data = [
        {
            "sl_no": index + 1 + pagination.offset(),
            "student_id": student.id,
            "student_name": f"{student.first_name} {student.last_name}",
            "roll_no": student.roll_no,
            "class_name": student.classes.name,
            "section_name": student.section.name,
            "attendance_count": attendance_count or 0,
            "exam_count": exam_count or 0,
            "rank": rank or None,
            "status": student.status.value,
            "status_expiry_date": student.status_expiry_date,
            "is_present_today": any(att.is_today_present for att in student.attendances if att.date == date.today()) if student.attendances else False 
        }
        for index, (student, attendance_count, exam_count, rank) in enumerate(students)
    ]

    return pagination.format_response(data, total_count)


@router.get("/students/{student_id}")
def get_student(
    student_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(require_roles(UserRole.SCHOOL, UserRole.TEACHER))
):
    if current_user.role == UserRole.SCHOOL:
        school_id = current_user.school_profile.id
    else:
        school_id = current_user.teacher_profile.school_id

    student = (
        db.query(Student)
        .filter(Student.id == student_id, Student.school_id == school_id)
        .options(
            joinedload(Student.classes),
            joinedload(Student.section),
            joinedload(Student.parent),
            joinedload(Student.present_address),
            joinedload(Student.permanent_address),
            joinedload(Student.exam_data)
        )
        .first()
    )

    if not student:
        raise HTTPException(status_code=404, detail="Student not found.")
    last_exam = (
    db.query(StudentExamData)
    .filter(StudentExamData.student_id == student.id)
    .order_by(StudentExamData.submitted_at.desc())
    .first()
       )

    return {
        "student_id": student.id,
        "profile_image": student.profile_image,
        "student_name": f"{student.first_name} {student.last_name}",
        "roll_no": student.roll_no,
        "class_name": student.classes.name,
        "section_name": student.section.name if student.section else None,
        "created_at": student.created_at,
        "status": student.status.value,
        "status_expiry_date": student.status_expiry_date,
        "last_appeared_exam":last_exam.submitted_at if last_exam else None,
        "exam_type":last_exam.exam.exam_type if last_exam and last_exam.exam else None,
        "exam_result":last_exam.result if last_exam else None,
        "parent": {
            "parent_name": student.parent.parent_name,
            "relation": student.parent.relation,
            "phone": student.parent.phone,
            "email": student.parent.email,
            "occupation": student.parent.occupation,
            "organization": student.parent.organization
        } if student.parent else None,
        "present_address": {
            "enter_pin": student.present_address.enter_pin,
            "division": student.present_address.division,
            "district": student.present_address.district,
            "state": student.present_address.state,
            "country": student.present_address.country,
            "building": student.present_address.building,
            "house_no": student.present_address.house_no,
            "floor_name": student.present_address.floor_name
        } if student.present_address else None,
        "permanent_address": {
            "enter_pin": student.permanent_address.enter_pin,
            "division": student.permanent_address.division,
            "district": student.permanent_address.district,
            "state": student.permanent_address.state,
            "country": student.permanent_address.country,
            "building": student.permanent_address.building,
            "house_no": student.permanent_address.house_no,
            "floor_name": student.permanent_address.floor_name
        } if student.permanent_address else None
    }

@router.patch("/students/{student_id}")
def update_student(
    student_id: int,
    data: StudentUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Allow only school or teacher
    if current_user.role not in [UserRole.SCHOOL, UserRole.TEACHER]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only schools and teachers can update student profiles."
        )

    # Identify school_id for both
    if current_user.role == UserRole.SCHOOL:
        school = getattr(current_user, "school_profile", None)
        if not school:
            raise HTTPException(status_code=400, detail="School profile not found.")
        school_id = school.id
    else:
        teacher = getattr(current_user, "teacher_profile", None)
        if not teacher:
            raise HTTPException(status_code=400, detail="Teacher profile not found.")
        school_id = teacher.school_id

    # Fetch student from same school
    student = db.query(Student).filter(
        Student.id == student_id,
        Student.school_id == school_id
    ).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found in your school.")

    # Allowed fields by role
    if current_user.role == UserRole.SCHOOL:
        allowed_fields = [
            "first_name", "last_name", "gender", "dob",
            "class_id", "section_id", "is_transport", "driver_id"
        ]
    else:
        allowed_fields = ["first_name", "last_name", "gender", "dob", "class_id", "section_id"]

    # Handle transport validation (school only)
    if current_user.role == UserRole.SCHOOL and data.is_transport is not None:
        if data.is_transport:
            if not data.driver_id:
                raise HTTPException(status_code=400, detail="Driver ID required when transport is enabled.")
            driver = db.query(Transport).filter(
                Transport.id == data.driver_id,
                Transport.school_id == school_id
            ).first()
            if not driver:
                raise HTTPException(status_code=400, detail="Driver not found for the given ID.")
        else:
            student.driver_id = None

    # Handle optional profile image
    if data.profile_image:
        try:
            profile_pic_url = upload_base64_to_s3(data.profile_image, f"students/{school_id}/profile")
            student.profile_image = profile_pic_url
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"S3 Upload failed: {str(e)}")

    # Update only provided & allowed fields
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field in allowed_fields and value is not None:
            setattr(student, field, value)

    # Update User.name if name changed
    user = db.query(User).filter(User.id == student.user_id).first()
    if user:
        new_name = f"{student.first_name or ''} {student.last_name or ''}".strip()
        if new_name:
            user.name = new_name

    try:
        db.commit()
        db.refresh(student)
        return {"detail": "Student profile updated successfully."}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update student: {str(e)}")



@router.patch("/students/{student_id}/status")
def update_student_status(
    student_id: int,
    new_status:StudentStatus = Body(..., embed=True),
    db: Session = Depends(get_db),
    current_user = Depends(require_roles(UserRole.SCHOOL, UserRole.TEACHER))
):

    # Identify which school the current user belongs to
    if current_user.role == UserRole.SCHOOL:
        school_id = current_user.school_profile.id
    else:
        school_id = current_user.teacher_profile.school_id

    # Fetch the student within that school
    student = (
        db.query(Student)
        .filter(Student.id == student_id, Student.school_id == school_id)
        .first()
    )

    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student not found or unauthorized to modify."
        )

    # Update the student's status
    student.status = new_status
    student.status_updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(student)

    return {
        "message": f"Student status changed to {student.status.value}",
        "student_id": student.id,
        "new_status": student.status.value,
        "status_updated_at": getattr(student, "status_updated_at", None)
    }
@router.get("/students/profile/")
def get_own_student_profile(
    db: Session = Depends(get_db),
    current_user = Depends(require_roles(UserRole.STUDENT))
):
    student = (
        db.query(Student)
        .filter(Student.user_id == current_user.id)
        .options(
            joinedload(Student.classes),
            joinedload(Student.section),
            joinedload(Student.parent),
            joinedload(Student.present_address),
            joinedload(Student.permanent_address),
            joinedload(Student.exam_data)
        )
        .first()
    )

    if not student:
        raise HTTPException(status_code=404, detail="Student profile not found.")
    last_exam = (
    db.query(StudentExamData)
    .filter(StudentExamData.student_id == student.id)
    .order_by(StudentExamData.submitted_at.desc())
    .first()
       )

    return {
        "student_id": student.id,
        "profile_image": student.profile_image,
        "student_name": f"{student.first_name} {student.last_name}",
        "roll_no": student.roll_no,
        "class_name": student.classes.name,
        "section_name": student.section.name if student.section else None,
        "created_at": student.created_at,
        "total_attendance": len(student.attendances) if student.attendances else 0,
        "total_exams": len(student.exam_data) if student.exam_data else 0,
        "last_appeared_exam":last_exam.submitted_at if last_exam else None,
        # "exam_given": sum(1 for exam in student.exam_data if exam.is_exam_given) if student.exam_data else 0,
        "parent": {
            "parent_name": student.parent.parent_name,
            "relation": student.parent.relation,
            "phone": student.parent.phone,
            "email": student.parent.email,
            "occupation": student.parent.occupation,
            "organization": student.parent.organization
        } if student.parent else None,
        "present_address": {
            "enter_pin": student.present_address.enter_pin,
            "division": student.present_address.division,
            "district": student.present_address.district,
            "state": student.present_address.state,
            "country": student.present_address.country,
            "building": student.present_address.building,
            "house_no": student.present_address.house_no,
            "floor_name": student.present_address.floor_name
        } if student.present_address else None,
        "permanent_address": {
            "enter_pin": student.permanent_address.enter_pin,
            "division": student.permanent_address.division,
            "district": student.permanent_address.district,
            "state": student.permanent_address.state,
            "country": student.permanent_address.country,
            "building": student.permanent_address.building,
            "house_no": student.permanent_address.house_no,
            "floor_name": student.permanent_address.floor_name
        } if student.permanent_address else None
    }

@router.get("/e-books/subjects/")
def get_student_subjects(
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(UserRole.STUDENT)),
):
    # ✅ Get student info with class + school
    student = (
        db.query(Student)
        .filter(Student.user_id == current_user.id)
        .options(
            joinedload(Student.classes).joinedload(Class.school),
        )
        .first()
    )

    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    if not student.classes:
        raise HTTPException(status_code=400, detail="Student class not assigned")

    school = student.classes.school
    class_name = student.classes.name
    print(f"Student's class: {class_name}, School ID: {school.id if school else 'N/A'}")
    school_board = getattr(school, "school_board", None)
    school_medium = getattr(school, "school_medium", None)

    if not school_board or not school_medium:
        raise HTTPException(status_code=400, detail="School board/medium missing")

    # ✅ Get subjects for this class, board, medium
    subjects = (
        db.query(SchoolClassSubject)
        .filter(
            SchoolClassSubject.school_board == school_board,
            SchoolClassSubject.school_medium == school_medium,
            SchoolClassSubject.class_name == class_name,
        )
        .all()
    )

    if not subjects:
        raise HTTPException(status_code=404, detail="No subjects found for this class")

    return [
        {"subject_id": s.id, "subject_name": s.subject}
        for s in subjects
    ]


@router.get("/e-book/{subject_id}/chapters/")
def get_chapters_by_subject(
    subject_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(UserRole.STUDENT)),
):
    # ✅ Get student
    student = db.query(Student).filter(Student.user_id == current_user.id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    # ✅ Alias for progress
    progress_alias = aliased(StudentChapterProgress)

    # ✅ Get chapters + video count + last read time
    chapters = (
        db.query(
            Chapter.id.label("chapter_id"),
            Chapter.title.label("chapter_title"),
            func.count(ChapterVideo.id).label("video_count"),
            progress_alias.last_read_at.label("last_read_at")
        )
        .outerjoin(ChapterVideo, Chapter.id == ChapterVideo.chapter_id)
        .outerjoin(
            progress_alias,
            (progress_alias.chapter_id == Chapter.id)
            & (progress_alias.student_id == student.id)
        )
        .filter(Chapter.school_class_subject_id == subject_id)
        .group_by(Chapter.id, progress_alias.last_read_at)
        .all()
    )

    if not chapters:
        raise HTTPException(status_code=404, detail="No chapters found for this subject")

    return [
        {
            "chapter_id": c.chapter_id,
            "chapter_title": c.chapter_title,
            "number_of_videos": c.video_count,
            "last_read_at": c.last_read_at.isoformat() if c.last_read_at else None
        }
        for c in chapters
    ]

@router.get("/e-books/chapter/{chapter_id}/")
def get_chapter_details(
    chapter_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(UserRole.STUDENT)),
):
    # 1️⃣ Get student profile
    student = (
        db.query(Student)
        .filter(Student.user_id == current_user.id)
        .options(joinedload(Student.classes))
        .first()
    )
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    # 2️⃣ Fetch chapter
    chapter = (
        db.query(Chapter)
        .options(
            joinedload(Chapter.videos),
            joinedload(Chapter.images),
            joinedload(Chapter.pdfs),
            joinedload(Chapter.qnas),
        )
        .filter(Chapter.id == chapter_id)
        .first()
    )
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")

    # 3️⃣ Check student's class matches chapter
    class_subject = chapter.school_class_subject
    if student.classes.name != class_subject.class_name:
        raise HTTPException(
            status_code=403,
            detail="You are not allowed to view chapters from another class.",
        )

    # 4️⃣ Update or create progress
    progress = (
        db.query(StudentChapterProgress)
        .filter_by(student_id=student.id, chapter_id=chapter.id)
        .first()
    )

    now = datetime.now(timezone.utc)
    if progress:
        progress.last_read_at = now
    else:
        progress = StudentChapterProgress(
            student_id=student.id, chapter_id=chapter.id, last_read_at=now
        )
        db.add(progress)

    db.commit()
    db.refresh(progress)

    # 5️⃣ Return chapter with last_read_at
    return {
        "chapter_id": chapter.id,
        "title": chapter.title,
        "description": chapter.description,
        "last_read_at": progress.last_read_at,
        "total_videos": len(chapter.videos),
        "total_images": len(chapter.images),
        "total_pdfs": len(chapter.pdfs),
        "total_qnas": len(chapter.qnas),
        "videos": [{"id": v.id, "url": v.url} for v in chapter.videos],
        "images": [{"id": i.id, "url": i.url} for i in chapter.images],
        "pdfs": [{"id": p.id, "url": p.url} for p in chapter.pdfs],
        "qnas": [{"id": q.id, "question": q.question, "answer": q.answer} for q in chapter.qnas],
    }