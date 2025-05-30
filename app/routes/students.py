from fastapi import APIRouter, Depends, HTTPException,status
from app.models.users import User,Otp
from app.models.students import Student,Parent,PresentAddress,PermanentAddress
from app.models.school import School,Class,Section,Subject,ExtraCurricularActivity,class_extra_curricular,class_section,class_subjects,class_optional_subjects
from app.schemas.users import UserRole
from app.schemas.students import StudentCreateRequest,ParentWithAddressCreate
from sqlalchemy.orm import Session,joinedload
from sqlalchemy import delete, insert
from app.db.session import get_db
from app.utils.email_utility import generate_otp
from app.core.dependencies import get_current_user
from app.utils.permission import require_roles
router = APIRouter()
@router.post("/students/create")
def create_student(
    data: StudentCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    print("Incoming student creation data:", data)
    if current_user.role != UserRole.SCHOOL:
        raise HTTPException(status_code=403, detail="Only schools can create students.")

    # Ensure email doesn't already exist
    existing = db.query(User).filter(User.email == data.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already exists.")

    # Get the school profile for the current user
    school = db.query(School).filter(School.id == current_user.school_profile.id).first()
    if not school:
        raise HTTPException(status_code=400, detail="School profile not found.")

    # Step 1: Create User for the student
    user = User(
        name=f"{data.first_name} {data.last_name}",
        email=data.email,
        role=UserRole.STUDENT
    )
    db.add(user)
    db.commit()
    db.refresh(user)

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
        school_id=school.id,   #next time when i will create a student account i have to check
    )
    db.add(student)
    db.commit()
    db.refresh(student)

    # Step 3: Generate and store OTP
    otp = generate_otp()
    otp_entry = Otp(user_id=user.id, otp=otp)
    db.add(otp_entry)
    db.commit()

    # Step 4: Send OTP
    # send_otp_email(user.email, otp)

    return {"message": "OTP sent to student's email for verification"}

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

    return {"message": "Parent and address data added successfully."}

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

    students_query = (
        db.query(Student)
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
        }
        for index, student in enumerate(students_query)
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

    if student := (
        db.query(Student)
        .filter(Student.id == student_id, Student.school_id == school_id)
        .options(
            joinedload(Student.classes),
            joinedload(Student.section),
            joinedload(Student.parent),
            joinedload(Student.present_address),
            joinedload(Student.permanent_address),
        )
        .first()
    ):
        return {
            "student_id": student.id,
            "student_name": f"{student.first_name} {student.last_name}",
            "roll_no": student.roll_no,
            "class_name": student.classes.name,
            "section_name": student.section,
            "parent": {
                "parent_name": student.parent.parent_name,
                "relation": student.parent.relation,
                "phone": student.parent.phone,
                "email": student.parent.email,
                "occupation": student.parent.occupation,
                "organization": student.parent.organization
            },
            "present_address": {
                "enter_pin": student.present_address.enter_pin,
                "division": student.present_address.division,
                "district": student.present_address.district,
                "state": student.present_address.state,
                "country": student.present_address.country,
                "building": student.present_address.building,
                "house_no": student.present_address.house_no,
                "floor_name": student.present_address.floor_name
            },
            "permanent_address": {
                "enter_pin": student.permanent_address.enter_pin,
                "division": student.permanent_address.division,
                "district": student.permanent_address.district,
                "state": student.permanent_address.state,
                "country": student.permanent_address.country,
                "building": student.permanent_address.building,
                "house_no": student.permanent_address.house_no,
                "floor_name": student.permanent_address.floor_name
            }
        }
    else:
        raise HTTPException(status_code=404, detail="Student not found.")    