from fastapi import APIRouter, Depends, HTTPException,status
from app.models.users import User,Otp
from app.models.students import Student,Parent,PresentAddress,PermanentAddress,StudentStatus
from app.models.school import School,Class,Section,Attendance,Transport,StudentExamData
from app.schemas.users import UserRole
from app.schemas.students import StudentCreateRequest,ParentWithAddressCreate
from datetime import timezone
from sqlalchemy.orm import Session,joinedload
from sqlalchemy import func
from app.db.session import get_db
from app.utils.email_utility import generate_otp
from app.core.dependencies import get_current_user
from app.utils.permission import require_roles
from app.core.security import create_verification_token
from app.utils.email_utility import send_dynamic_email
from datetime import datetime, timedelta
router = APIRouter()
@router.post("/students/create")
def create_student(
    data: StudentCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role != UserRole.SCHOOL:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only schools can create students."
        )

    # Ensure email doesn't already exist
    existing = db.query(User).filter(User.email == data.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already exists.")

    # Get the school profile for the current user
    school = getattr(current_user, "school_profile", None)
    if not school:
        raise HTTPException(status_code=400, detail="School profile not found.")

    # Validate transport requirement
    if data.is_transport:
        if not data.driver_id:
            raise HTTPException(status_code=400, detail="Driver ID is required when transport is enabled.")
        driver = db.query(Transport).filter(
            Transport.id == data.driver_id,
            Transport.school_id == school.id
        ).first()
        if not driver:
            raise HTTPException(status_code=400, detail="Driver not found for the given ID.")

    try:
        # Step 1: Create User for the student
        user = User(
            name=f"{data.first_name} {data.last_name}",
            email=data.email,
            role=UserRole.STUDENT
        )
        db.add(user)

        # Step 2: Create Student profile
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
            school_id=school.id,
            status=StudentStatus.TRIAL,
            status_expiry_date=datetime.utcnow() + timedelta(days=15)
        )
        db.add(student)

        # Step 3: Generate and store OTP
        otp = generate_otp()
        otp_entry = Otp(user=user, otp=otp)
        db.add(otp_entry)

        # Commit once at the end
        db.commit()
        db.refresh(user)
        db.refresh(student)

        # Email sending after commit (to avoid rollback issues)
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

        return {"detail": "OTP sent to student's email for verification"}

    except Exception as e:
        db.rollback()  # undo partial inserts
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
    limit: int = 10,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user = Depends(require_roles(UserRole.SCHOOL, UserRole.TEACHER))
):
    if current_user.role == UserRole.SCHOOL:
        school_id = current_user.school_profile.id
    else:
        school_id = current_user.teacher_profile.school_id

    # Subquery to count attendance per student
    attendance_subquery = (
        db.query(
            Attendance.student_id,
            func.count(Attendance.id).label("attendance_count")
        )
        .group_by(Attendance.student_id)
        .subquery()
    )

    students_query = (
        db.query(
            Student,
            attendance_subquery.c.attendance_count
        )
        .outerjoin(attendance_subquery, Student.id == attendance_subquery.c.student_id)
        .join(Class, Student.class_id == Class.id)
        .join(Section, Student.section_id == Section.id)
        .filter(Class.school_id == school_id)
        .options(
            joinedload(Student.classes),
            joinedload(Student.section)
        )
        .offset(offset)
        .limit(limit)
        .all()
    )

    return [
        {
            "sl_no": index + 1 + offset,
            "student_id": student.id,
            "student_name": f"{student.first_name} {student.last_name}",
            "roll_no": student.roll_no,
            "class_name": student.classes.name,
            "section_name": student.section.name,
            "attendance_count": attendance_count or 0,
            "status": student.status.value,
            "status_expiry_date": student.status_expiry_date,
        }
        for index, (student, attendance_count) in enumerate(students_query)
    ]

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