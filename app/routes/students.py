from fastapi import APIRouter, Depends, HTTPException,status,Query,Body
from app.models.users import User,Otp
from app.models.students import Student,Parent,PresentAddress,PermanentAddress,StudentStatus,StudentPayment,InstallmentType,StudentPaymentTransaction
from app.models.school import School,Class,Section,Attendance,Transport,StudentExamData
from app.models.staff import Staff
from app.schemas.users import UserRole
from app.schemas.students import StudentCreateRequest,ParentWithAddressCreate,StudentUpdateRequest,ParentWithAddressUpdate,StudentPaymentUpdate,PaymentTransactionCreate
from datetime import timezone
from sqlalchemy.orm import Session,joinedload,aliased
from sqlalchemy import func, and_, or_
from app.db.session import get_db
from app.utils.email_utility import generate_otp
from app.core.dependencies import get_current_user
from app.utils.permission import require_roles
from app.core.security import create_verification_token
from app.utils.email_utility import send_dynamic_email
from datetime import datetime, timedelta,date
from typing import List, Optional
from app.utils.s3 import upload_base64_to_s3
from app.services.pagination import PaginationParams
from app.models.admin import SchoolClassSubject,Chapter,ChapterVideo,ChapterImage,ChapterPDF,ChapterQnA,StudentChapterProgress
from app.utils.staff_logging import log_action
from app.models.staff import ActionType, ResourceType
router = APIRouter()
@router.post("/students/create")
def create_student(
    data: StudentCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # ✅ Allow SCHOOL, TEACHER, or STAFF
    if current_user.role not in [UserRole.SCHOOL, UserRole.TEACHER, UserRole.STAFF]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only schools, teachers, or staff can create students."
        )

    # ✅ Get the correct school_id based on the role
    if current_user.role == UserRole.SCHOOL:
        school = getattr(current_user, "school_profile", None)
        if not school:
            raise HTTPException(status_code=404, detail="School profile not found.")
        school_id = school.id
    elif current_user.role == UserRole.TEACHER:
        teacher = getattr(current_user, "teacher_profile", None)
        if not teacher:
            raise HTTPException(status_code=404, detail="Teacher profile not found.")
        school_id = teacher.school_id
    else:  # current_user.role == UserRole.STAFF
        staff = db.query(Staff).filter(Staff.user_id == current_user.id).first()
        if not staff:
            raise HTTPException(status_code=404, detail="Staff profile not found.")
        school_id = staff.school_id

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
            pickup_point=data.pickup_point,
            pickup_time=data.pickup_time,
            drop_point=data.drop_point,
            drop_time=data.drop_time,
            user_id=user.id,
            school_id=school_id,
            profile_image=profile_pic_url,
            status=StudentStatus.TRIAL,
            status_expiry_date=datetime.utcnow() + timedelta(days=15)
        )

        db.add(student)
        db.flush()  # ensures student.id is available

        # ✅ Create Student Payment record
        # Map string enum values to InstallmentType enum
        installment_type_map = {
            "monthly": InstallmentType.MONTHLY,
            "quarterly": InstallmentType.QUARTERLY,
            "half_yearly": InstallmentType.HALF_YEARLY,
            "yearly": InstallmentType.YEARLY
        }
        
        # Check if payment record already exists for this student and class
        existing_payment = db.query(StudentPayment).filter(
            StudentPayment.student_id == student.id,
            StudentPayment.class_id == data.class_id
        ).first()
        
        if existing_payment:
            raise HTTPException(
                status_code=400,
                detail=f"Payment record already exists for this student in class {data.class_id}"
            )
        
        student_payment = StudentPayment(
            student_id=student.id,
            class_id=data.class_id,
            course_fee=data.payment.course_fee,
            course_fee_installment_type=installment_type_map[data.payment.course_fee_installment_type.value],
            transport_fee=data.payment.transport_fee,
            transport_fee_installment_type=installment_type_map[data.payment.transport_fee_installment_type.value],
            tek_school_fee=data.payment.tek_school_fee,
            tek_school_fee_installment_type=installment_type_map[data.payment.tek_school_fee_installment_type.value]
        )
        db.add(student_payment)
        db.commit()
        db.refresh(user)
        db.refresh(student)
        db.refresh(student_payment)

        # ✅ Send verification email (non-blocking - don't fail student creation if email fails)
        email_sent = False
        email_error = None
        try:
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
            email_sent = True
        except Exception as email_exception:
            # Log email error but don't fail student creation
            email_error = str(email_exception)
            print(f"Warning: Failed to send verification email to {user.email}: {email_error}")

        # Log action
        log_action(
            db=db,
            current_user=current_user,
            action_type=ActionType.CREATE,
            resource_type=ResourceType.STUDENT,
            resource_id=str(student.id),
            description=f"Created student: {data.first_name} {data.last_name}",
            metadata={"student_id": student.id, "roll_no": data.roll_no, "class_id": data.class_id}
        )

        response = {
            "detail": "Student account created successfully." + (" Verification email sent." if email_sent else " Note: Verification email could not be sent."),
            "student_id": student.id,
            "user_id": user.id,
            "profile_pic_url": profile_pic_url,
            "email_sent": email_sent,
            "payment": {
                "payment_id": student_payment.id,
                "class_id": student_payment.class_id,
                "course_fee": student_payment.course_fee,
                "course_fee_installment_type": student_payment.course_fee_installment_type.value,
                "transport_fee": student_payment.transport_fee,
                "transport_fee_installment_type": student_payment.transport_fee_installment_type.value,
                "tek_school_fee": student_payment.tek_school_fee,
                "tek_school_fee_installment_type": student_payment.tek_school_fee_installment_type.value
            }
        }
        
        if not email_sent and email_error:
            response["email_error"] = email_error
        
        return response

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

@router.put("/students/{student_id}/update-parent-info")
def update_parent_and_address(
    student_id: int,
    data: ParentWithAddressUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Allow both school and staff
    if current_user.role == UserRole.SCHOOL:
        school_profile = getattr(current_user, "school_profile", None)
        if not school_profile:
            raise HTTPException(status_code=404, detail="School profile not found.")
        school_id = school_profile.id
    elif current_user.role == UserRole.STAFF:
        staff = db.query(Staff).filter(Staff.user_id == current_user.id).first()
        if not staff:
            raise HTTPException(status_code=404, detail="Staff profile not found.")
        school_id = staff.school_id
    else:
        raise HTTPException(status_code=403, detail="Only school or staff users can update parent and address data.")

    student = db.query(Student).filter(Student.id == student_id, Student.school_id == school_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found or not part of your school.")

    updated_sections: List[str] = []

    # ✅ Parent update
    parent = db.query(Parent).filter(Parent.student_id == student_id).first()
    if parent and data.parent:
        for field, value in data.parent.dict(exclude_unset=True).items():
            setattr(parent, field, value)
        updated_sections.append("parent")

    # ✅ Present address update
    present = db.query(PresentAddress).filter(PresentAddress.student_id == student_id).first()
    if present and data.present_address:
        for field, value in data.present_address.dict(exclude_unset=True).items():
            setattr(present, field, value)
        updated_sections.append("present_address")

    # ✅ Permanent address handling
    permanent = db.query(PermanentAddress).filter(PermanentAddress.student_id == student_id).first()
    if data.present_address and data.present_address.is_this_permanent_as_well:
        if permanent:
            db.delete(permanent)
            updated_sections.append("permanent_address_removed")
    elif data.permanent_address:
        if permanent:
            for field, value in data.permanent_address.dict(exclude_unset=True).items():
                setattr(permanent, field, value)
            updated_sections.append("permanent_address")
        else:
            permanent = PermanentAddress(
                **data.permanent_address.dict(exclude_unset=True),
                student_id=student_id
            )
            db.add(permanent)
            updated_sections.append("permanent_address_created")

    db.commit()

    log_action(
        db=db,
        current_user=current_user,
        action_type=ActionType.UPDATE,
        resource_type=ResourceType.STUDENT,
        resource_id=str(student.id),
        description=f"Updated parent/address info for student {student.first_name} {student.last_name}",
        metadata={"student_id": student.id, "updated_sections": updated_sections}
    )

    return {"detail": "Parent and address data updated successfully."}

@router.get("/students/")
def get_students(
    pagination: PaginationParams = Depends(),
    db: Session = Depends(get_db),
    current_user = Depends(require_roles(UserRole.SCHOOL, UserRole.TEACHER, UserRole.STAFF)),
    roll_no: int | None = Query(None, description="Filter by roll number"),
    name: str | None = Query(None, description="Filter by student name"),
    class_name: str | None = Query(None, description="Filter by class name"),
    section_name: str | None = Query(None, description="Filter by section name")
):
    # ✅ Determine school_id based on user role
    if current_user.role == UserRole.SCHOOL:
        school_id = current_user.school_profile.id
    elif current_user.role == UserRole.TEACHER:
        school_id = current_user.teacher_profile.school_id
    else:  # STAFF
        staff = db.query(Staff).filter(Staff.user_id == current_user.id).first()
        if not staff:
            raise HTTPException(status_code=404, detail="Staff profile not found.")
        school_id = staff.school_id

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

    # Payment subquery - get payment info for student's current class
    # We'll join this in the main query using student_id and matching class_id
    # Note: Rounding is done in Python to avoid PostgreSQL type issues
    payment_subquery = (
        db.query(
            StudentPayment.student_id,
            StudentPayment.class_id,
            StudentPayment.course_fee,
            StudentPayment.course_fee_paid,
            StudentPayment.course_fee_installment_type,
            StudentPayment.transport_fee,
            StudentPayment.transport_fee_paid,
            StudentPayment.transport_fee_installment_type,
            StudentPayment.tek_school_fee,
            StudentPayment.tek_school_fee_paid,
            StudentPayment.tek_school_fee_installment_type,
            (StudentPayment.course_fee_paid + 
             StudentPayment.transport_fee_paid + 
             StudentPayment.tek_school_fee_paid).label("total_paid"),
            ((StudentPayment.course_fee - StudentPayment.course_fee_paid) + 
             (StudentPayment.transport_fee - StudentPayment.transport_fee_paid) + 
             (StudentPayment.tek_school_fee - StudentPayment.tek_school_fee_paid)).label("total_remaining")
        )
        .subquery()
    )

    # --- Base Query ---
    base_query = (
        db.query(
            Student,
            attendance_subquery.c.attendance_count,
            exam_count_subquery.c.exam_count,
            rank_subquery.c.latest_rank,
            payment_subquery.c.course_fee,
            payment_subquery.c.course_fee_paid,
            payment_subquery.c.course_fee_installment_type,
            payment_subquery.c.transport_fee,
            payment_subquery.c.transport_fee_paid,
            payment_subquery.c.transport_fee_installment_type,
            payment_subquery.c.tek_school_fee,
            payment_subquery.c.tek_school_fee_paid,
            payment_subquery.c.tek_school_fee_installment_type,
            payment_subquery.c.total_paid,
            payment_subquery.c.total_remaining,
            Class.class_start_date,
            Class.class_end_date,
        )
        .outerjoin(attendance_subquery, Student.id == attendance_subquery.c.student_id)
        .outerjoin(exam_count_subquery, Student.id == exam_count_subquery.c.student_id)
        .outerjoin(rank_subquery, Student.id == rank_subquery.c.student_id)
        .outerjoin(
            payment_subquery, 
            and_(
                Student.id == payment_subquery.c.student_id,
                Student.class_id == payment_subquery.c.class_id
            )
        )
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
    if section_name:
        base_query = base_query.filter(Section.name.ilike(f"%{section_name}%"))

    # --- Count & Pagination ---
    total_count = base_query.count()
    students = base_query.offset(pagination.offset()).limit(pagination.limit()).all()

    # --- Get Payment History for each student ---
    # Create mapping of (student_id, class_id) -> payment_id
    student_payment_ids = {}
    if students:
        # Get payment IDs for students' current classes
        student_class_pairs = [(student.id, student.class_id) for student, _, _, _, _, _, _, _, _, _, _, _, _, _, _, _, _ in students]
        if student_class_pairs:
            # Build filter conditions for matching (student_id, class_id) pairs
            conditions = []
            for student_id, class_id in student_class_pairs:
                conditions.append(
                    and_(
                        StudentPayment.student_id == student_id,
                        StudentPayment.class_id == class_id
                    )
                )
            
            if conditions:
                payments = db.query(StudentPayment.id, StudentPayment.student_id, StudentPayment.class_id).filter(
                    or_(*conditions)
                ).all()
                for payment in payments:
                    key = (payment.student_id, payment.class_id)
                    student_payment_ids[key] = payment.id
    
    # Get last 5 transactions for each payment (for list view)
    payment_history = {}
    if student_payment_ids:
        payment_ids_list = list(student_payment_ids.values())
        # Get transactions grouped by payment_id, limit 5 per payment
        transactions = db.query(StudentPaymentTransaction).filter(
            StudentPaymentTransaction.student_payment_id.in_(payment_ids_list)
        ).order_by(
            StudentPaymentTransaction.student_payment_id,
            StudentPaymentTransaction.transaction_date.desc()
        ).all()
        
        # Group by payment_id and limit to 5 per payment
        for txn in transactions:
            payment_id = txn.student_payment_id
            if payment_id not in payment_history:
                payment_history[payment_id] = []
            if len(payment_history[payment_id]) < 5:  # Limit to last 5 transactions
                payment_history[payment_id].append({
                    "transaction_id": txn.id,
                    "amount": float(txn.amount),
                    "payment_type": txn.payment_type,
                    "payment_breakdown": txn.payment_breakdown if txn.payment_breakdown else None,
                    "transaction_date": txn.transaction_date.isoformat() if txn.transaction_date else None,
                    "description": txn.description,
                    "files": txn.files if txn.files else [],
                    "payment_method": txn.payment_method,
                    "transaction_reference": txn.transaction_reference,
                    "created_at": txn.created_at.isoformat() if txn.created_at else None,
                })

    # --- Format Response ---
    data = []
    for index, (student, attendance_count, exam_count, rank, course_fee, course_fee_paid, 
               course_fee_installment_type, transport_fee, transport_fee_paid, 
               transport_fee_installment_type, tek_school_fee, tek_school_fee_paid, 
               tek_school_fee_installment_type, total_paid, total_remaining, 
               class_start_date, class_end_date) in enumerate(students):
        
        # Get payment history for this student's current class
        payment_id = student_payment_ids.get((student.id, student.class_id))
        payment_history_list = payment_history.get(payment_id, []) if payment_id else []
        
        data.append({
            "sl_no": index + 1 + pagination.offset(),
            "student_id": student.id,
            "student_name": f"{student.first_name} {student.last_name}",
            "roll_no": student.roll_no,
            "class_name": student.classes.name,
            "section_name": student.section.name,
            "class_start_date": class_start_date.isoformat() if class_start_date else None,
            "class_end_date": class_end_date.isoformat() if class_end_date else None,
            "attendance_count": attendance_count or 0,
            "exam_count": exam_count or 0,
            "rank": rank or None,
            "status": student.status.value,
            "status_expiry_date": student.status_expiry_date,
            "is_present_today": any(att.is_today_present for att in student.attendances if att.date == date.today()) if student.attendances else False,
            "fee": {
                "course_fee": float(course_fee) if course_fee is not None else 0.0,
                "course_fee_paid": float(course_fee_paid) if course_fee_paid is not None else 0.0,
                "course_fee_remaining": round(float(course_fee) - float(course_fee_paid), 2) if course_fee is not None and course_fee_paid is not None else 0.0,
                "course_fee_installment_type": course_fee_installment_type.value if course_fee_installment_type else None,
                "transport_fee": float(transport_fee) if transport_fee is not None else 0.0,
                "transport_fee_paid": float(transport_fee_paid) if transport_fee_paid is not None else 0.0,
                "transport_fee_remaining": round(float(transport_fee) - float(transport_fee_paid), 2) if transport_fee is not None and transport_fee_paid is not None else 0.0,
                "transport_fee_installment_type": transport_fee_installment_type.value if transport_fee_installment_type else None,
                "tek_school_fee": float(tek_school_fee) if tek_school_fee is not None else 0.0,
                "tek_school_fee_paid": float(tek_school_fee_paid) if tek_school_fee_paid is not None else 0.0,
                "tek_school_fee_remaining": round(float(tek_school_fee) - float(tek_school_fee_paid), 2) if tek_school_fee is not None and tek_school_fee_paid is not None else 0.0,
                "tek_school_fee_installment_type": tek_school_fee_installment_type.value if tek_school_fee_installment_type else None,
                "total_paid": float(total_paid) if total_paid is not None else 0.0,
                "total_remaining": float(total_remaining) if total_remaining is not None else 0.0,
            },
            "payment_history": payment_history_list
        })

    return pagination.format_response(data, total_count)


@router.get("/students/{student_id}")
def get_student(
    student_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(require_roles(UserRole.SCHOOL, UserRole.TEACHER, UserRole.STAFF))
):
    # ✅ Determine school_id based on user role
    if current_user.role == UserRole.SCHOOL:
        school_id = current_user.school_profile.id
    elif current_user.role == UserRole.TEACHER:
        school_id = current_user.teacher_profile.school_id
    else:  # STAFF
        staff = db.query(Staff).filter(Staff.user_id == current_user.id).first()
        if not staff:
            raise HTTPException(status_code=404, detail="Staff profile not found.")
        school_id = staff.school_id

    student = (
        db.query(Student)
        .filter(Student.id == student_id, Student.school_id == school_id)
        .options(
            joinedload(Student.classes),
            joinedload(Student.section),
            joinedload(Student.parent),
            joinedload(Student.present_address),
            joinedload(Student.permanent_address),
            joinedload(Student.exam_data),
            joinedload(Student.driver),
        )
        .first()
    )

    if not student:
        raise HTTPException(status_code=404, detail="Student not found.")
    
    # Get student payment for current class
    student_payment = (
        db.query(StudentPayment)
        .filter(
            StudentPayment.student_id == student.id,
            StudentPayment.class_id == student.class_id
        )
        .first()
    )
    
    # Get payment history for this student's current class payment
    payment_history = []
    if student_payment:
        transactions = (
            db.query(StudentPaymentTransaction)
            .filter(StudentPaymentTransaction.student_payment_id == student_payment.id)
            .order_by(StudentPaymentTransaction.transaction_date.desc())
            .all()
        )
        
        for txn in transactions:
            payment_history.append({
                "transaction_id": txn.id,
                "amount": float(txn.amount),
                "payment_type": txn.payment_type,
                "payment_breakdown": txn.payment_breakdown if txn.payment_breakdown else None,
                "transaction_date": txn.transaction_date.isoformat() if txn.transaction_date else None,
                "description": txn.description,
                "files": txn.files if txn.files else [],
                "payment_method": txn.payment_method,
                "transaction_reference": txn.transaction_reference,
                "created_at": txn.created_at.isoformat() if txn.created_at else None,
            })
    
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
        "first_name": student.first_name,
        "last_name": student.last_name,
        "gender": student.gender,
        "dob": student.dob,
        "roll_no": student.roll_no,
        "class_name": student.classes.name,
        "section_name": student.section.name if student.section else None,
        "class_start_date": student.classes.class_start_date.isoformat() if student.classes and student.classes.class_start_date else None,
        "class_end_date": student.classes.class_end_date.isoformat() if student.classes and student.classes.class_end_date else None,
        "created_at": student.created_at,
        "status": student.status.value,
        "status_expiry_date": student.status_expiry_date,
        "last_appeared_exam":last_exam.submitted_at if last_exam else None,
        "exam_type":last_exam.exam.exam_type if last_exam and last_exam.exam else None,
        "exam_result":last_exam.result if last_exam else None,
        "vechicle_number":student.driver.vechicle_number if student.driver else None,
        "driver_name":student.driver.driver_name if student.driver else None,
        "pickup_point":student.pickup_point,
        "pickup_time":student.pickup_time,
        "drop_point":student.drop_point,
        "drop_time":student.drop_time,
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
        } if student.permanent_address else None,
        "fee": {
            "course_fee": float(student_payment.course_fee) if student_payment else 0.0,
            "course_fee_paid": float(student_payment.course_fee_paid) if student_payment else 0.0,
            "course_fee_remaining": round(float(student_payment.course_fee) - float(student_payment.course_fee_paid), 2) if student_payment and student_payment.course_fee is not None and student_payment.course_fee_paid is not None else 0.0,
            "course_fee_installment_type": student_payment.course_fee_installment_type.value if student_payment and student_payment.course_fee_installment_type else None,
            "transport_fee": float(student_payment.transport_fee) if student_payment else 0.0,
            "transport_fee_paid": float(student_payment.transport_fee_paid) if student_payment else 0.0,
            "transport_fee_remaining": round(float(student_payment.transport_fee) - float(student_payment.transport_fee_paid), 2) if student_payment and student_payment.transport_fee is not None and student_payment.transport_fee_paid is not None else 0.0,
            "transport_fee_installment_type": student_payment.transport_fee_installment_type.value if student_payment and student_payment.transport_fee_installment_type else None,
            "tek_school_fee": float(student_payment.tek_school_fee) if student_payment else 0.0,
            "tek_school_fee_paid": float(student_payment.tek_school_fee_paid) if student_payment else 0.0,
            "tek_school_fee_remaining": round(float(student_payment.tek_school_fee) - float(student_payment.tek_school_fee_paid), 2) if student_payment and student_payment.tek_school_fee is not None and student_payment.tek_school_fee_paid is not None else 0.0,
            "tek_school_fee_installment_type": student_payment.tek_school_fee_installment_type.value if student_payment and student_payment.tek_school_fee_installment_type else None,
            "total_paid": round(
                (float(student_payment.course_fee_paid) if student_payment else 0.0) + 
                (float(student_payment.transport_fee_paid) if student_payment else 0.0) + 
                (float(student_payment.tek_school_fee_paid) if student_payment else 0.0), 2
            ) if student_payment else 0.0,
            "total_remaining": round(
                ((float(student_payment.course_fee) if student_payment else 0.0) - (float(student_payment.course_fee_paid) if student_payment else 0.0)) + 
                ((float(student_payment.transport_fee) if student_payment else 0.0) - (float(student_payment.transport_fee_paid) if student_payment else 0.0)) + 
                ((float(student_payment.tek_school_fee) if student_payment else 0.0) - (float(student_payment.tek_school_fee_paid) if student_payment else 0.0)), 2
            ) if student_payment else 0.0,
        },
        "payment_history": payment_history
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
            "class_id", "section_id", "is_transport", "driver_id","pickup_point","pickup_time","drop_point","drop_time"
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
        
        # Log action
        log_action(
            db=db,
            current_user=current_user,
            action_type=ActionType.UPDATE,
            resource_type=ResourceType.STUDENT,
            resource_id=str(student.id),
            description=f"Updated student: {student.first_name} {student.last_name}",
            metadata={"student_id": student.id, "updated_fields": list(update_data.keys())}
        )
        
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
        "pickup_point":student.pickup_point,
        "pickup_time":student.pickup_time,
        "drop_point":student.drop_point,
        "drop_time":student.drop_time,
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

# ==================== STUDENT PAYMENT APIs ====================

@router.get("/students/{student_id}/payments/")
def get_student_payments(
    student_id: int,
    class_id: Optional[int] = Query(None, description="Filter by class_id"),
    db: Session = Depends(get_db),
    current_user = Depends(require_roles(UserRole.SCHOOL, UserRole.TEACHER, UserRole.STAFF))
):
    """
    Get payment records for a student.
    If class_id is provided, returns payment for that specific class.
    Otherwise, returns all payment records for the student.
    """
    # ✅ Determine school_id based on user role
    if current_user.role == UserRole.SCHOOL:
        school_id = current_user.school_profile.id
    elif current_user.role == UserRole.TEACHER:
        school_id = current_user.teacher_profile.school_id
    else:  # STAFF
        staff = db.query(Staff).filter(Staff.user_id == current_user.id).first()
        if not staff:
            raise HTTPException(status_code=404, detail="Staff profile not found.")
        school_id = staff.school_id

    # Verify student belongs to the school
    student = db.query(Student).filter(
        Student.id == student_id,
        Student.school_id == school_id
    ).first()
    
    if not student:
        raise HTTPException(status_code=404, detail="Student not found or not part of your school.")

    # Query payment records
    query = db.query(StudentPayment).filter(StudentPayment.student_id == student_id)
    
    if class_id:
        query = query.filter(StudentPayment.class_id == class_id)
    
    payments = query.options(
        joinedload(StudentPayment.classes)
    ).all()

    if not payments:
        return {
            "student_id": student_id,
            "student_name": f"{student.first_name} {student.last_name}",
            "payments": []
        }

    # Format response
    payment_list = []
    for payment in payments:
        payment_list.append({
            "payment_id": payment.id,
            "class_id": payment.class_id,
            "class_name": payment.classes.name if payment.classes else None,
            "course_fee": payment.course_fee,
            "course_fee_installment_type": payment.course_fee_installment_type.value,
            "course_fee_paid": payment.course_fee_paid,
            "course_fee_remaining": round(payment.course_fee - payment.course_fee_paid, 2),
            "transport_fee": payment.transport_fee,
            "transport_fee_installment_type": payment.transport_fee_installment_type.value,
            "transport_fee_paid": payment.transport_fee_paid,
            "transport_fee_remaining": round(payment.transport_fee - payment.transport_fee_paid, 2),
            "tek_school_fee": payment.tek_school_fee,
            "tek_school_fee_installment_type": payment.tek_school_fee_installment_type.value,
            "tek_school_fee_paid": payment.tek_school_fee_paid,
            "tek_school_fee_remaining": round(payment.tek_school_fee - payment.tek_school_fee_paid, 2),
            "total_paid": round(payment.course_fee_paid + payment.transport_fee_paid + payment.tek_school_fee_paid, 2),
            "total_remaining": round(
                (payment.course_fee - payment.course_fee_paid) + 
                (payment.transport_fee - payment.transport_fee_paid) + 
                (payment.tek_school_fee - payment.tek_school_fee_paid), 2
            ),
            "created_at": payment.created_at,
            "updated_at": payment.updated_at
        })

    return {
        "student_id": student_id,
        "student_name": f"{student.first_name} {student.last_name}",
        "payments": payment_list
    }

@router.get("/students/{student_id}/payments/{class_id}/")
def get_student_payment_by_class(
    student_id: int,
    class_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(require_roles(UserRole.SCHOOL, UserRole.TEACHER, UserRole.STAFF))
):
    """
    Get payment record for a specific student and class combination.
    """
    # ✅ Determine school_id based on user role
    if current_user.role == UserRole.SCHOOL:
        school_id = current_user.school_profile.id
    elif current_user.role == UserRole.TEACHER:
        school_id = current_user.teacher_profile.school_id
    else:  # STAFF
        staff = db.query(Staff).filter(Staff.user_id == current_user.id).first()
        if not staff:
            raise HTTPException(status_code=404, detail="Staff profile not found.")
        school_id = staff.school_id

    # Verify student belongs to the school
    student = db.query(Student).filter(
        Student.id == student_id,
        Student.school_id == school_id
    ).first()
    
    if not student:
        raise HTTPException(status_code=404, detail="Student not found or not part of your school.")

    # Get payment record
    payment = db.query(StudentPayment).filter(
        StudentPayment.student_id == student_id,
        StudentPayment.class_id == class_id
    ).options(
        joinedload(StudentPayment.classes)
    ).first()

    if not payment:
        raise HTTPException(
            status_code=404,
            detail=f"Payment record not found for student {student_id} in class {class_id}."
        )

    # Get transaction history for this payment
    transactions = db.query(StudentPaymentTransaction).filter(
        StudentPaymentTransaction.student_payment_id == payment.id
    ).order_by(StudentPaymentTransaction.transaction_date.desc()).all()
    
    transaction_list = []
    for txn in transactions:
        transaction_data = {
            "transaction_id": txn.id,
            "amount": txn.amount,
            "payment_type": txn.payment_type,
            "payment_breakdown": txn.payment_breakdown if txn.payment_breakdown else None,  # Include breakdown from model
            "transaction_date": txn.transaction_date,
            "description": txn.description,
            "files": txn.files if txn.files else [],
            "payment_method": txn.payment_method,
            "transaction_reference": txn.transaction_reference,
            "created_at": txn.created_at,
            "created_by": txn.created_by
        }
        
        transaction_list.append(transaction_data)
    
    return {
        "payment_id": payment.id,
        "student_id": payment.student_id,
        "student_name": f"{student.first_name} {student.last_name}",
        "class_id": payment.class_id,
        "class_name": payment.classes.name if payment.classes else None,
        "course_fee": payment.course_fee,
        "course_fee_installment_type": payment.course_fee_installment_type.value,
        "course_fee_paid": payment.course_fee_paid,
        "course_fee_remaining": round(payment.course_fee - payment.course_fee_paid, 2),
        "transport_fee": payment.transport_fee,
        "transport_fee_installment_type": payment.transport_fee_installment_type.value,
        "transport_fee_paid": payment.transport_fee_paid,
        "transport_fee_remaining": round(payment.transport_fee - payment.transport_fee_paid, 2),
        "tek_school_fee": payment.tek_school_fee,
        "tek_school_fee_installment_type": payment.tek_school_fee_installment_type.value,
        "tek_school_fee_paid": payment.tek_school_fee_paid,
        "tek_school_fee_remaining": round(payment.tek_school_fee - payment.tek_school_fee_paid, 2),
        "total_paid": round(payment.course_fee_paid + payment.transport_fee_paid + payment.tek_school_fee_paid, 2),
        "total_remaining": round(
            (payment.course_fee - payment.course_fee_paid) + 
            (payment.transport_fee - payment.transport_fee_paid) + 
            (payment.tek_school_fee - payment.tek_school_fee_paid), 2
        ),
        "transactions": transaction_list,
        "total_transactions": len(transaction_list),
        "created_at": payment.created_at,
        "updated_at": payment.updated_at
    }

@router.post("/students/{student_id}/payments/{class_id}/")
def create_payment_transaction(
    student_id: int,
    class_id: int,
    data: PaymentTransactionCreate,
    db: Session = Depends(get_db),
    current_user = Depends(require_roles(UserRole.SCHOOL, UserRole.STAFF))
):
    """
    Create payment transaction(s) for a student.
    You can pay one, two, or all three fees (course_fee, transport_fee, tek_school_fee) in a single request.
    This will:
    - Validate the payment amounts don't exceed remaining balances
    - Create separate transaction records for each payment
    - Update the paid amounts
    - Calculate and return pending balances
    """
    # ✅ Determine school_id based on user role
    if current_user.role == UserRole.SCHOOL:
        school_id = current_user.school_profile.id
    elif current_user.role == UserRole.STAFF:
        staff = db.query(Staff).filter(Staff.user_id == current_user.id).first()
        if not staff:
            raise HTTPException(status_code=404, detail="Staff profile not found.")
        school_id = staff.school_id
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only schools and staff can create payment transactions."
        )

    # Verify student belongs to the school
    student = db.query(Student).filter(
        Student.id == student_id,
        Student.school_id == school_id
    ).first()
    
    if not student:
        raise HTTPException(status_code=404, detail="Student not found or not part of your school.")

    # Get payment record
    payment = db.query(StudentPayment).filter(
        StudentPayment.student_id == student_id,
        StudentPayment.class_id == class_id
    ).first()

    if not payment:
        raise HTTPException(
            status_code=404,
            detail=f"Payment record not found for student {student_id} in class {class_id}."
        )

    # ✅ VALIDATION: At least one payment amount must be provided
    if not any([data.course_fee_amount, data.transport_fee_amount, data.tek_school_fee_amount]):
        raise HTTPException(
            status_code=400,
            detail="At least one payment amount must be provided (course_fee_amount, transport_fee_amount, or tek_school_fee_amount)"
        )

    # Handle file uploads (if provided) - upload to S3 and get URLs
    uploaded_file_urls = []
    if data.files:
        for file_base64 in data.files:
            try:
                # Extract file extension from base64 string
                file_ext = "pdf"  # Default extension
                if "," in file_base64:
                    if "image/png" in file_base64:
                        file_ext = "png"
                    elif "image/jpeg" in file_base64 or "image/jpg" in file_base64:
                        file_ext = "jpg"
                    elif "application/pdf" in file_base64:
                        file_ext = "pdf"
                
                # Upload to S3
                file_url = upload_base64_to_s3(
                    base64_string=file_base64,
                    filename_prefix=f"student_payments/{student_id}/class_{class_id}/transactions",
                    ext=file_ext
                )
                uploaded_file_urls.append(file_url)
            except Exception as e:
                print(f"Warning: Failed to upload file: {str(e)}")
                # Continue with other files even if one fails

    # Validate all payments first, then process them
    transaction_errors = []
    payment_breakdown = {}
    total_amount = 0.0
    
    # Validate and collect Course Fee Payment
    if data.course_fee_amount is not None:
        if data.course_fee_amount <= 0:
            transaction_errors.append("Course fee amount must be greater than 0")
        else:
            remaining = round(payment.course_fee - payment.course_fee_paid, 2)
            if remaining <= 0:
                transaction_errors.append(f"Course fee is already fully paid. Remaining balance: {remaining}")
            elif data.course_fee_amount > remaining:
                transaction_errors.append(f"Course fee payment amount ({data.course_fee_amount}) exceeds remaining balance ({remaining}). Maximum allowed: {remaining}")
            else:
                payment_breakdown["course_fee"] = data.course_fee_amount
                total_amount += data.course_fee_amount

    # Validate and collect Transport Fee Payment
    if data.transport_fee_amount is not None:
        if data.transport_fee_amount <= 0:
            transaction_errors.append("Transport fee amount must be greater than 0")
        else:
            remaining = round(payment.transport_fee - payment.transport_fee_paid, 2)
            if remaining <= 0:
                transaction_errors.append(f"Transport fee is already fully paid. Remaining balance: {remaining}")
            elif data.transport_fee_amount > remaining:
                transaction_errors.append(f"Transport fee payment amount ({data.transport_fee_amount}) exceeds remaining balance ({remaining}). Maximum allowed: {remaining}")
            else:
                payment_breakdown["transport_fee"] = data.transport_fee_amount
                total_amount += data.transport_fee_amount

    # Validate and collect Tek School Fee Payment
    if data.tek_school_fee_amount is not None:
        if data.tek_school_fee_amount <= 0:
            transaction_errors.append("Tek School fee amount must be greater than 0")
        else:
            remaining = round(payment.tek_school_fee - payment.tek_school_fee_paid, 2)
            if remaining <= 0:
                transaction_errors.append(f"Tek School fee is already fully paid. Remaining balance: {remaining}")
            elif data.tek_school_fee_amount > remaining:
                transaction_errors.append(f"Tek School fee payment amount ({data.tek_school_fee_amount}) exceeds remaining balance ({remaining}). Maximum allowed: {remaining}")
            else:
                payment_breakdown["tek_school_fee"] = data.tek_school_fee_amount
                total_amount += data.tek_school_fee_amount

    # If there are validation errors, return them without committing
    if transaction_errors:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Payment validation failed",
                "errors": transaction_errors
            }
        )

    # If no valid payments, return error
    if not payment_breakdown:
        raise HTTPException(
            status_code=400,
            detail="No valid payment transactions to process"
        )

    # Update paid amounts for all valid payments
    if "course_fee" in payment_breakdown:
        payment.course_fee_paid = round(payment.course_fee_paid + payment_breakdown["course_fee"], 2)
    if "transport_fee" in payment_breakdown:
        payment.transport_fee_paid = round(payment.transport_fee_paid + payment_breakdown["transport_fee"], 2)
    if "tek_school_fee" in payment_breakdown:
        payment.tek_school_fee_paid = round(payment.tek_school_fee_paid + payment_breakdown["tek_school_fee"], 2)

    # Determine payment_type - if only one fee type, use that; otherwise use first one
    if len(payment_breakdown) == 1:
        payment_type = list(payment_breakdown.keys())[0]
    else:
        # Multiple payment types - use the first one (course_fee, transport_fee, or tek_school_fee)
        payment_type = list(payment_breakdown.keys())[0]

    # Create ONE transaction record for the payment (even if multiple fee types)
    transaction = StudentPaymentTransaction(
        student_payment_id=payment.id,
        amount=round(total_amount, 2),
        payment_type=payment_type,
        payment_breakdown=payment_breakdown,  # Store the breakdown dynamically
        transaction_date=datetime.utcnow(),
        description=data.description,
        files=uploaded_file_urls if uploaded_file_urls else None,
        payment_method=data.payment_method,
        transaction_reference=data.transaction_reference,
        created_by=current_user.id
    )
    db.add(transaction)
    transactions_created = [transaction]

    try:
        db.commit()
        db.refresh(payment)
        for tx in transactions_created:
            db.refresh(tx)
        
        # Log action
        payment_types_list = list(payment_breakdown.keys())
        transaction_ids = [tx.id for tx in transactions_created]
        log_action(
            db=db,
            current_user=current_user,
            action_type=ActionType.CREATE,
            resource_type=ResourceType.STUDENT,
            resource_id=str(student.id),
            description=f"Created payment transaction(s) for student {student.first_name} {student.last_name} in class {class_id}",
            metadata={
                "student_id": student.id,
                "class_id": class_id,
                "payment_id": payment.id,
                "transaction_ids": transaction_ids,
                "payment_types": payment_types_list,
                "payment_breakdown": payment_breakdown,
                "total_amount": total_amount
            }
        )
        
        # Calculate pending balances
        course_fee_remaining = round(payment.course_fee - payment.course_fee_paid, 2)
        transport_fee_remaining = round(payment.transport_fee - payment.transport_fee_paid, 2)
        tek_school_fee_remaining = round(payment.tek_school_fee - payment.tek_school_fee_paid, 2)
        total_remaining = round(
            course_fee_remaining + transport_fee_remaining + tek_school_fee_remaining, 2
        )
        
        return {
            "detail": "Payment transaction created successfully.",
            "transaction": {
                "transaction_id": transaction.id,
                "amount": round(total_amount, 2),
                "payment_type": payment_type,
                "payment_breakdown": payment_breakdown,
                "transaction_date": transaction.transaction_date,
                "description": transaction.description,
                "files": transaction.files if transaction.files else [],
                "payment_method": transaction.payment_method,
                "transaction_reference": transaction.transaction_reference,
                "created_at": transaction.created_at,
                "created_by": transaction.created_by
            },
            "payment_id": payment.id,
            "student_id": payment.student_id,
            "class_id": payment.class_id,
            "total_amount_paid": round(total_amount, 2),
            # Payment structure (from existing payment)
            "course_fee": payment.course_fee,
            "course_fee_installment_type": payment.course_fee_installment_type.value,
            "course_fee_paid": payment.course_fee_paid,
            "course_fee_remaining": course_fee_remaining,
            "transport_fee": payment.transport_fee,
            "transport_fee_installment_type": payment.transport_fee_installment_type.value,
            "transport_fee_paid": payment.transport_fee_paid,
            "transport_fee_remaining": transport_fee_remaining,
            "tek_school_fee": payment.tek_school_fee,
            "tek_school_fee_installment_type": payment.tek_school_fee_installment_type.value,
            "tek_school_fee_paid": payment.tek_school_fee_paid,
            "tek_school_fee_remaining": tek_school_fee_remaining,
            "total_paid": round(payment.course_fee_paid + payment.transport_fee_paid + payment.tek_school_fee_paid, 2),
            "total_remaining": total_remaining,
            "created_at": transaction.created_at
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create payment transaction: {str(e)}")

@router.patch("/students/{student_id}/payments/{class_id}/")
def update_student_payment(
    student_id: int,
    class_id: int,
    data: StudentPaymentUpdate,
    db: Session = Depends(get_db),
    current_user = Depends(require_roles(UserRole.SCHOOL, UserRole.STAFF))
):
    """
    Update payment record for a student in a specific class.
    Only SCHOOL and STAFF roles can update payments.
    """
    # ✅ Determine school_id based on user role
    if current_user.role == UserRole.SCHOOL:
        school_id = current_user.school_profile.id
    elif current_user.role == UserRole.STAFF:
        staff = db.query(Staff).filter(Staff.user_id == current_user.id).first()
        if not staff:
            raise HTTPException(status_code=404, detail="Staff profile not found.")
        school_id = staff.school_id
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only schools and staff can update student payments."
        )

    # Verify student belongs to the school
    student = db.query(Student).filter(
        Student.id == student_id,
        Student.school_id == school_id
    ).first()
    
    if not student:
        raise HTTPException(status_code=404, detail="Student not found or not part of your school.")

    # Get payment record
    payment = db.query(StudentPayment).filter(
        StudentPayment.student_id == student_id,
        StudentPayment.class_id == class_id
    ).first()

    if not payment:
        raise HTTPException(
            status_code=404,
            detail=f"Payment record not found for student {student_id} in class {class_id}."
        )

    # Map string enum values to InstallmentType enum
    installment_type_map = {
        "monthly": InstallmentType.MONTHLY,
        "quarterly": InstallmentType.QUARTERLY,
        "half_yearly": InstallmentType.HALF_YEARLY,
        "yearly": InstallmentType.YEARLY
    }

    # Update only provided fields
    update_data = data.model_dump(exclude_unset=True)
    
    if "course_fee" in update_data and update_data["course_fee"] is not None:
        payment.course_fee = update_data["course_fee"]
    
    if "course_fee_installment_type" in update_data and update_data["course_fee_installment_type"] is not None:
        payment.course_fee_installment_type = installment_type_map[update_data["course_fee_installment_type"].value]
    
    if "transport_fee" in update_data and update_data["transport_fee"] is not None:
        payment.transport_fee = update_data["transport_fee"]
    
    if "transport_fee_installment_type" in update_data and update_data["transport_fee_installment_type"] is not None:
        payment.transport_fee_installment_type = installment_type_map[update_data["transport_fee_installment_type"].value]
    
    if "tek_school_fee" in update_data and update_data["tek_school_fee"] is not None:
        payment.tek_school_fee = update_data["tek_school_fee"]
    
    if "tek_school_fee_installment_type" in update_data and update_data["tek_school_fee_installment_type"] is not None:
        payment.tek_school_fee_installment_type = installment_type_map[update_data["tek_school_fee_installment_type"].value]
    
    # Store old values to calculate transaction amounts
    old_course_fee_paid = payment.course_fee_paid
    old_transport_fee_paid = payment.transport_fee_paid
    old_tek_school_fee_paid = payment.tek_school_fee_paid
    
    # ✅ VALIDATION: Check if paid amounts exceed actual fee amounts
    if "course_fee_paid" in update_data and update_data["course_fee_paid"] is not None:
        if update_data["course_fee_paid"] > payment.course_fee:
            raise HTTPException(
                status_code=400,
                detail=f"Course fee paid amount ({update_data['course_fee_paid']}) cannot exceed the actual course fee ({payment.course_fee})"
            )
    
    if "transport_fee_paid" in update_data and update_data["transport_fee_paid"] is not None:
        if update_data["transport_fee_paid"] > payment.transport_fee:
            raise HTTPException(
                status_code=400,
                detail=f"Transport fee paid amount ({update_data['transport_fee_paid']}) cannot exceed the actual transport fee ({payment.transport_fee})"
            )
    
    if "tek_school_fee_paid" in update_data and update_data["tek_school_fee_paid"] is not None:
        if update_data["tek_school_fee_paid"] > payment.tek_school_fee:
            raise HTTPException(
                status_code=400,
                detail=f"Tek School fee paid amount ({update_data['tek_school_fee_paid']}) cannot exceed the actual tek school fee ({payment.tek_school_fee})"
            )
    
    # Handle file uploads (if provided) - upload to S3 and get URLs
    uploaded_file_urls = []
    if "files" in update_data and update_data["files"] is not None:
        for file_base64 in update_data["files"]:
            try:
                # Extract file extension from base64 string
                file_ext = "pdf"  # Default extension
                if "," in file_base64:
                    if "image/png" in file_base64:
                        file_ext = "png"
                    elif "image/jpeg" in file_base64 or "image/jpg" in file_base64:
                        file_ext = "jpg"
                    elif "application/pdf" in file_base64:
                        file_ext = "pdf"
                
                # Upload to S3
                file_url = upload_base64_to_s3(
                    base64_string=file_base64,
                    filename_prefix=f"student_payments/{student_id}/class_{class_id}/transactions",
                    ext=file_ext
                )
                uploaded_file_urls.append(file_url)
            except Exception as e:
                print(f"Warning: Failed to upload file: {str(e)}")
                # Continue with other files even if one fails
    
    # Update payment clear amounts and create transactions
    if "course_fee_paid" in update_data and update_data["course_fee_paid"] is not None:
        new_amount = update_data["course_fee_paid"]
        payment.course_fee_paid = new_amount
        
        # Calculate difference (new payment amount)
        payment_difference = new_amount - old_course_fee_paid
        
        # Create transaction if there's an increase in payment
        if payment_difference > 0:
            transaction = StudentPaymentTransaction(
                student_payment_id=payment.id,
                amount=payment_difference,
                payment_type="course_fee",
                transaction_date=datetime.utcnow(),
                description=update_data.get("description"),
                files=uploaded_file_urls if uploaded_file_urls else None,
                created_by=current_user.id
            )
            db.add(transaction)
    
    if "transport_fee_paid" in update_data and update_data["transport_fee_paid"] is not None:
        new_amount = update_data["transport_fee_paid"]
        payment.transport_fee_paid = new_amount
        
        # Calculate difference
        payment_difference = new_amount - old_transport_fee_paid
        
        # Create transaction if there's an increase
        if payment_difference > 0:
            transaction = StudentPaymentTransaction(
                student_payment_id=payment.id,
                amount=payment_difference,
                payment_type="transport_fee",
                transaction_date=datetime.utcnow(),
                description=update_data.get("description"),
                files=uploaded_file_urls if uploaded_file_urls else None,
                created_by=current_user.id
            )
            db.add(transaction)
    
    if "tek_school_fee_paid" in update_data and update_data["tek_school_fee_paid"] is not None:
        new_amount = update_data["tek_school_fee_paid"]
        payment.tek_school_fee_paid = new_amount
        
        # Calculate difference
        payment_difference = new_amount - old_tek_school_fee_paid
        
        # Create transaction if there's an increase
        if payment_difference > 0:
            transaction = StudentPaymentTransaction(
                student_payment_id=payment.id,
                amount=payment_difference,
                payment_type="tek_school_fee",
                transaction_date=datetime.utcnow(),
                description=update_data.get("description"),
                files=uploaded_file_urls if uploaded_file_urls else None,
                created_by=current_user.id
            )
            db.add(transaction)

    try:
        db.commit()
        db.refresh(payment)
        
        # Log action
        log_action(
            db=db,
            current_user=current_user,
            action_type=ActionType.UPDATE,
            resource_type=ResourceType.STUDENT,
            resource_id=str(student.id),
            description=f"Updated payment for student {student.first_name} {student.last_name} in class {class_id}",
            metadata={
                "student_id": student.id,
                "class_id": class_id,
                "payment_id": payment.id,
                "updated_fields": list(update_data.keys())
            }
        )
        
        return {
            "detail": "Student payment updated successfully.",
            "payment_id": payment.id,
            "student_id": payment.student_id,
            "class_id": payment.class_id,
            "course_fee": payment.course_fee,
            "course_fee_installment_type": payment.course_fee_installment_type.value,
            "course_fee_paid": payment.course_fee_paid,
            "course_fee_remaining": round(payment.course_fee - payment.course_fee_paid, 2),
            "transport_fee": payment.transport_fee,
            "transport_fee_installment_type": payment.transport_fee_installment_type.value,
            "transport_fee_paid": payment.transport_fee_paid,
            "transport_fee_remaining": round(payment.transport_fee - payment.transport_fee_paid, 2),
            "tek_school_fee": payment.tek_school_fee,
            "tek_school_fee_installment_type": payment.tek_school_fee_installment_type.value,
            "tek_school_fee_paid": payment.tek_school_fee_paid,
            "tek_school_fee_remaining": round(payment.tek_school_fee - payment.tek_school_fee_paid, 2),
            "total_paid": round(payment.course_fee_paid + payment.transport_fee_paid + payment.tek_school_fee_paid, 2),
            "total_remaining": round(
                (payment.course_fee - payment.course_fee_paid) + 
                (payment.transport_fee - payment.transport_fee_paid) + 
                (payment.tek_school_fee - payment.tek_school_fee_paid), 2
            ),
            "updated_at": payment.updated_at
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update student payment: {str(e)}")
        