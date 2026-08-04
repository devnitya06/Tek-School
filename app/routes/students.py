from fastapi import APIRouter, Depends, HTTPException,status,Query,Body
from app.models.users import User,Otp
from app.models.students import *
from app.models.school import (
    School,
    Class,
    Section,
    Attendance,
    Transport,
    StudentExamData,
    BankAccount,
    Exam,
    ExamTypeEnum,
    ExamStatusEnum,
    EvaluationScopeEnum,
    class_subjects,
)
from app.models.staff import Staff
from app.models.teachers import TeacherClassSectionSubject,Teacher
from app.schemas.users import UserRole
from app.schemas.students import *
from app.schemas.school import BankAccountResponse
from datetime import timezone
from sqlalchemy.orm import Session,joinedload,aliased
from sqlalchemy import func, and_, or_, exists
from app.db.session import get_db
from app.utils.email_utility import generate_otp
from app.core.dependencies import get_current_user
from app.utils.permission import require_roles, verify_school_business_access
from app.core.security import create_verification_token
from app.core.config import get_verification_base_url
from app.utils.email_utility import send_dynamic_email
from datetime import datetime, timedelta, date
from typing import List, Optional
from calendar import monthrange
from app.utils.s3 import upload_base64_to_s3
from app.services.pagination import PaginationParams
from app.models.admin import SchoolClassSubject,Chapter,ChapterVideo,ChapterImage,ChapterPDF,ChapterQnA,StudentChapterProgress
from app.utils.staff_logging import log_action
from app.models.staff import ActionType, ResourceType
from app.utils.school_settlement import (
    record_student_fee_credit,
    resolve_student_fee_settlement_bank_account_id,
)
from app.utils.payment_calculations import calculate_installment_pending_amount, calculate_single_fee_installment_pending
import asyncio
from starlette.concurrency import run_in_threadpool
router = APIRouter()


def _student_visible_active_exams_query(db: Session, student: Student):
    """Same visibility rules as GET /school/exams/ for STUDENT role."""
    admin_exam_condition = exists().where(
        and_(
            class_subjects.c.school_class_subject_id == Exam.selected_class_id,
            class_subjects.c.class_id == student.class_id,
        )
    )
    return db.query(Exam).filter(
        or_(
            and_(
                Exam.created_by_admin == False,
                Exam.class_id == student.class_id,
                Exam.sections.any(Section.id == student.section_id),
            ),
            and_(Exam.created_by_admin == True, admin_exam_condition),
        ),
        Exam.status == ExamStatusEnum.ACTIVE,
        or_(
            Exam.created_by_admin == True,
            and_(
                Exam.created_by_admin == False,
                or_(
                    and_(
                        Exam.evaluation_scope == EvaluationScopeEnum.INTERNAL,
                        Exam.school_id == student.school_id,
                    ),
                    and_(
                        Exam.evaluation_scope == EvaluationScopeEnum.EXTERNAL,
                        Exam.school_id != student.school_id,
                    ),
                    Exam.evaluation_scope == EvaluationScopeEnum.BOTH,
                ),
            ),
        ),
    )
@router.post("/students/create")
def create_student(
    data: StudentCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # ✅ Allow SCHOOL (business only), TEACHER, or STAFF
    if current_user.role not in [UserRole.SCHOOL, UserRole.TEACHER, UserRole.STAFF]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only schools, teachers, or staff can create students."
        )

    # ✅ For SCHOOL users, verify business account access
    if current_user.role == UserRole.SCHOOL:
        verify_school_business_access(current_user, db)

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
            registration_no=data.registration_no,
            blood_group=data.blood_group,
            date_of_admission=data.date_of_admission,
            previous_class_marks_obtained=data.previous_class_marks_obtained,
            previous_class_overall_percentage=data.previous_class_overall_percentage,
            previous_class_final_grade=data.previous_class_final_grade,
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
            status_expiry_date=datetime.utcnow() + timedelta(days=1)
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
            transport_fee=data.payment.transport_fee,
            tek_school_fee=data.payment.tek_school_fee,
            installment_type=installment_type_map[data.payment.installment_type].value
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
            verification_link = f"{get_verification_base_url('https://school.beingideal.com')}/users/verify-account?token={token}"

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
            "registration_no": student.registration_no,
            "blood_group": student.blood_group,
            "date_of_admission": student.date_of_admission,
            "previous_class_marks_obtained": student.previous_class_marks_obtained,
            "previous_class_overall_percentage": student.previous_class_overall_percentage,
            "previous_class_final_grade": student.previous_class_final_grade,
            "email_sent": email_sent,
            "payment": {
                "payment_id": student_payment.id,
                "class_id": student_payment.class_id,
                "course_fee": student_payment.course_fee,
                "transport_fee": student_payment.transport_fee,
                "tek_school_fee": student_payment.tek_school_fee,
                "installment_type": student_payment.installment_type
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
    
    # ✅ Verify business account access
    verify_school_business_access(current_user, db)

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
        education=data.parent.education,
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
    # Allow both school (business only) and staff
    if current_user.role == UserRole.SCHOOL:
        verify_school_business_access(current_user, db)
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

@router.get(
    "/students/",
    summary="Get list of students",
    description="Retrieve a paginated list of students with optional filters. Supports filtering by roll number, name, class, section, installment type, installment pending status, and latest transaction date/status."
)
def get_students(
    pagination: PaginationParams = Depends(),
    db: Session = Depends(get_db),
    current_user = Depends(require_roles(UserRole.SCHOOL, UserRole.TEACHER, UserRole.STAFF)),
    roll_no: int | None = Query(None, description="Filter by roll number"),
    name: str | None = Query(None, description="Filter by student name"),
    class_name: str | None = Query(None, description="Filter by class name"),
    section_name: str | None = Query(None, description="Filter by section name"),
    studentstatus:str | None =Query(None),
    installment_type: str | None = Query(None, description="Filter by installment type (monthly, quarterly, half_yearly, yearly)"),
    is_installment_pending: bool | None = Query(None, description="Filter by installment pending status (true for pending, false for no pending)"),
    last_transaction_start_date: date | None = Query(None, description="Filter by latest transaction start date (inclusive)"),
    last_transaction_end_date: date | None = Query(None, description="Filter by latest transaction end date (inclusive)"),
    status: List[str] | None = Query(None, description="Filter by latest transaction status(es). Can provide multiple statuses (comma-separated or multiple query params)")
):
    teacher_assignments = None
    # ✅ Determine school_id based on user role
    if current_user.role == UserRole.SCHOOL:
        verify_school_business_access(current_user, db)
        school_id = current_user.school_profile.id
    elif current_user.role == UserRole.TEACHER:
        teacher = current_user.teacher_profile
        if not teacher:
            raise HTTPException(status_code=404, detail="Teacher profile not found")

        school_id = teacher.school_id  # ✅ FIXED

        teacher_assignments = (
            db.query(
                TeacherClassSectionSubject.class_id,
                TeacherClassSectionSubject.section_id
            )
            .filter(TeacherClassSectionSubject.teacher_id == teacher.id)
            .all()
        )

        if not teacher_assignments:
            return pagination.format_response([], 0)
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
            StudentPayment.transport_fee,
            StudentPayment.transport_fee_paid,
            StudentPayment.tek_school_fee,
            StudentPayment.tek_school_fee_paid,
            StudentPayment.installment_type,
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
            payment_subquery.c.transport_fee,
            payment_subquery.c.transport_fee_paid,
            payment_subquery.c.tek_school_fee,
            payment_subquery.c.tek_school_fee_paid,
            payment_subquery.c.installment_type,
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
    if teacher_assignments:
        teacher_conditions = [
            and_(
                Student.class_id == class_id,
                Student.section_id == section_id
            )
            for class_id, section_id in teacher_assignments
        ]

        base_query = base_query.filter(or_(*teacher_conditions))


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
    if studentstatus:
         base_query = base_query.filter(Student.status == studentstatus)
    if installment_type:
        # Filter by installment type in payment subquery
        base_query = base_query.filter(payment_subquery.c.installment_type == installment_type)

    # --- Get all students (before pagination) for is_installment_pending filter ---
    # Note: We need to calculate installment_pending_amount to filter by is_installment_pending
    # So we fetch all matching students first, calculate, filter, then paginate
    all_students = base_query.all()
    
    # Filter by is_installment_pending if provided
    if is_installment_pending is not None:
        filtered_students = []
        for student_tuple in all_students:
            (student, attendance_count, exam_count, rank, course_fee, course_fee_paid,
             transport_fee, transport_fee_paid, tek_school_fee, tek_school_fee_paid,
             installment_type_val, total_paid, total_remaining,
             class_start_date, class_end_date) = student_tuple
            
            # Calculate installment_pending_amount
            pending_amount = calculate_installment_pending_amount(
                course_fee=float(course_fee) if course_fee is not None else 0.0,
                course_fee_paid=float(course_fee_paid) if course_fee_paid is not None else 0.0,
                transport_fee=float(transport_fee) if transport_fee is not None else 0.0,
                transport_fee_paid=float(transport_fee_paid) if transport_fee_paid is not None else 0.0,
                tek_school_fee=float(tek_school_fee) if tek_school_fee is not None else 0.0,
                tek_school_fee_paid=float(tek_school_fee_paid) if tek_school_fee_paid is not None else 0.0,
                installment_type=installment_type_val,
                class_start_date=class_start_date,
                class_end_date=class_end_date
            )
            
            # Filter based on is_installment_pending
            has_pending = pending_amount > 0
            if is_installment_pending == has_pending:
                filtered_students.append(student_tuple)
        
        all_students = filtered_students
    
    # --- Filter by latest transaction date and status ---
    if last_transaction_start_date or last_transaction_end_date or status:
        # Get payment IDs for all students first
        student_class_pairs_for_filter = [(student.id, student.class_id) for student, _, _, _, _, _, _, _, _, _, _, _, _, _, _ in all_students]
        
        if student_class_pairs_for_filter:
            # Build filter conditions for matching (student_id, class_id) pairs
            conditions = []
            for student_id, class_id in student_class_pairs_for_filter:
                conditions.append(
                    and_(
                        StudentPayment.student_id == student_id,
                        StudentPayment.class_id == class_id
                    )
                )
            
            if conditions:
                payments_for_filter = db.query(StudentPayment.id, StudentPayment.student_id, StudentPayment.class_id).filter(
                    or_(*conditions)
                ).all()
                
                payment_id_map = {}
                for payment in payments_for_filter:
                    key = (payment.student_id, payment.class_id)
                    payment_id_map[key] = payment.id
                
                # Get latest transaction for each payment
                payment_ids_list = list(payment_id_map.values())
                if payment_ids_list:
                    # Get all transactions and then pick the latest for each payment
                    all_transactions = (
                        db.query(StudentPaymentTransaction)
                        .filter(StudentPaymentTransaction.student_payment_id.in_(payment_ids_list))
                        .order_by(
                            StudentPaymentTransaction.student_payment_id,
                            StudentPaymentTransaction.transaction_date.desc(),
                            StudentPaymentTransaction.id.desc()
                        )
                        .all()
                    )
                    
                    # Group by payment_id and get the first (latest) transaction for each
                    latest_transactions_dict = {}
                    for txn in all_transactions:
                        if txn.student_payment_id not in latest_transactions_dict:
                            latest_transactions_dict[txn.student_payment_id] = txn
                    
                    # Create mapping: (student_id, class_id) -> latest_transaction
                    latest_transaction_map = {}
                    for payment_id, txn in latest_transactions_dict.items():
                        payment_obj = db.query(StudentPayment).filter(StudentPayment.id == payment_id).first()
                        if payment_obj:
                            key = (payment_obj.student_id, payment_obj.class_id)
                            latest_transaction_map[key] = txn
                    
                    # Filter students based on latest transaction
                    filtered_students = []
                    for student_tuple in all_students:
                        (student, attendance_count, exam_count, rank, course_fee, course_fee_paid,
                         transport_fee, transport_fee_paid, tek_school_fee, tek_school_fee_paid,
                         installment_type_val, total_paid, total_remaining,
                         class_start_date, class_end_date) = student_tuple
                        
                        key = (student.id, student.class_id)
                        latest_txn = latest_transaction_map.get(key)
                        
                        # If no transaction exists and filters are provided, exclude this student
                        if not latest_txn:
                            if last_transaction_start_date or last_transaction_end_date or status:
                                continue
                            else:
                                filtered_students.append(student_tuple)
                                continue
                        
                        # Filter by date range
                        if last_transaction_start_date or last_transaction_end_date:
                            txn_date = latest_txn.transaction_date.date() if latest_txn.transaction_date else None
                            if not txn_date:
                                continue
                            
                            if last_transaction_start_date and txn_date < last_transaction_start_date:
                                continue
                            if last_transaction_end_date and txn_date > last_transaction_end_date:
                                continue
                        
                        # Filter by status
                        if status:
                            # status is a list, check if latest transaction status is in the list
                            if latest_txn.status not in status:
                                continue
                        
                        filtered_students.append(student_tuple)
                    
                    all_students = filtered_students
    
    # --- Count & Pagination ---
    total_count = len(all_students)
    students = all_students[pagination.offset():pagination.offset() + pagination.limit()]

    # --- Get Payment History for each student ---
    # Create mapping of (student_id, class_id) -> payment_id
    student_payment_ids = {}
    if students:
        # Get payment IDs for students' current classes
        # Query returns: Student, attendance_count, exam_count, rank, course_fee, course_fee_paid,
        # transport_fee, transport_fee_paid, tek_school_fee, tek_school_fee_paid, installment_type,
        # total_paid, total_remaining, class_start_date, class_end_date (15 items total)
        student_class_pairs = [(student.id, student.class_id) for student, _, _, _, _, _, _, _, _, _, _, _, _, _, _ in students]
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
                    "bank_account_id": txn.bank_account_id if txn.bank_account_id else None,
                    "status": txn.status if txn.status else 'verified',
                    "verified_at": txn.verified_at.isoformat() if txn.verified_at else None,
                    "rejection_reason": txn.rejection_reason if txn.rejection_reason else None,
                    "created_at": txn.created_at.isoformat() if txn.created_at else None,
                })

    # --- Format Response ---
    data = []
    for index, (student, attendance_count, exam_count, rank, course_fee, course_fee_paid, 
               transport_fee, transport_fee_paid, tek_school_fee, tek_school_fee_paid, 
               installment_type, total_paid, total_remaining, 
               class_start_date, class_end_date) in enumerate(students):
        
        # Get payment history for this student's current class
        payment_id = student_payment_ids.get((student.id, student.class_id))
        payment_history_list = payment_history.get(payment_id, []) if payment_id else []
        
        # Calculate installment_pending_amount using utility function
        installment_pending_amount = calculate_installment_pending_amount(
            course_fee=float(course_fee) if course_fee is not None else 0.0,
            course_fee_paid=float(course_fee_paid) if course_fee_paid is not None else 0.0,
            transport_fee=float(transport_fee) if transport_fee is not None else 0.0,
            transport_fee_paid=float(transport_fee_paid) if transport_fee_paid is not None else 0.0,
            tek_school_fee=float(tek_school_fee) if tek_school_fee is not None else 0.0,
            tek_school_fee_paid=float(tek_school_fee_paid) if tek_school_fee_paid is not None else 0.0,
            installment_type=installment_type,
            class_start_date=class_start_date,
            class_end_date=class_end_date
        )
        
        data.append({
            "sl_no": index + 1 + pagination.offset(),
            "student_id": student.id,
            "student_name": f"{student.first_name} {student.last_name}",
            "roll_no": student.roll_no,
            "registration_no": student.registration_no,
            "class_id": student.class_id,
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
                "transport_fee": float(transport_fee) if transport_fee is not None else 0.0,
                "transport_fee_paid": float(transport_fee_paid) if transport_fee_paid is not None else 0.0,
                "transport_fee_remaining": round(float(transport_fee) - float(transport_fee_paid), 2) if transport_fee is not None and transport_fee_paid is not None else 0.0,
                "tek_school_fee": float(tek_school_fee) if tek_school_fee is not None else 0.0,
                "tek_school_fee_paid": float(tek_school_fee_paid) if tek_school_fee_paid is not None else 0.0,
                "tek_school_fee_remaining": round(float(tek_school_fee) - float(tek_school_fee_paid), 2) if tek_school_fee is not None and tek_school_fee_paid is not None else 0.0,
                "installment_type": installment_type if installment_type else None,
                "total_paid": float(total_paid) if total_paid is not None else 0.0,
                "total_remaining": float(total_remaining) if total_remaining is not None else 0.0,
                "installment_pending_amount": installment_pending_amount,
            },
            "payment_history": payment_history_list
        })

    return pagination.format_response(data, total_count)


@router.get("/students/{student_id}")
def get_student(
    student_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(require_roles(UserRole.SCHOOL, UserRole.TEACHER, UserRole.STAFF, UserRole.STUDENT,UserRole.ADMIN))
):
    # ✅ Determine school_id based on user role
    if current_user.role == UserRole.ADMIN:
        school_id = None
    elif current_user.role == UserRole.SCHOOL:
        verify_school_business_access(current_user, db)
        school_id = current_user.school_profile.id
    elif current_user.role == UserRole.TEACHER:
        school_id = current_user.teacher_profile.school_id
    elif current_user.role == UserRole.STAFF:
        staff = db.query(Staff).filter(Staff.user_id == current_user.id).first()
        if not staff:
            raise HTTPException(status_code=404, detail="Staff profile not found.")
        school_id = staff.school_id
    else:  # STUDENT
        # Students can only access their own profile
        student_profile = db.query(Student).filter(Student.user_id == current_user.id).first()
        if not student_profile:
            raise HTTPException(status_code=404, detail="Student profile not found for this user.")
        
        # Verify that the requested student_id matches the logged-in student's ID
        if student_profile.id != student_id:
            raise HTTPException(
                status_code=403,
                detail="You can only access your own student profile."
            )
        
        school_id = student_profile.school_id

    query  = (
        db.query(Student)
        .filter(Student.id == student_id)
        .options(
            joinedload(Student.classes),
            joinedload(Student.section),
            joinedload(Student.parent),
            joinedload(Student.present_address),
            joinedload(Student.permanent_address),
            joinedload(Student.exam_data),
            joinedload(Student.driver),
        )
    )

    if school_id is not None:
        query = query.filter(Student.school_id == school_id)

    student = query.first()
    
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
            .options(joinedload(StudentPaymentTransaction.bank_account))
            .filter(StudentPaymentTransaction.student_payment_id == student_payment.id)
            .order_by(StudentPaymentTransaction.transaction_date.desc())
            .all()
        )
        
        for txn in transactions:
            bank_details = None
            if txn.bank_account:
                bank_details = {
                    "id": txn.bank_account.id,
                    "school_id": txn.bank_account.school_id,
                    "account_holder_name": txn.bank_account.account_holder_name,
                    "account_number": txn.bank_account.account_number,
                    "ifsc_code": txn.bank_account.ifsc_code,
                    "bank_name": txn.bank_account.bank_name,
                    "branch_name": txn.bank_account.branch_name,
                    "account_type": txn.bank_account.account_type,
                    "is_primary": txn.bank_account.is_primary,
                    "created_at": txn.bank_account.created_at.isoformat() if txn.bank_account.created_at else None,
                    "updated_at": txn.bank_account.updated_at.isoformat() if txn.bank_account.updated_at else None,
                }
            
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
                "bank_details": bank_details,
                "status": txn.status if txn.status else 'verified',
                "verified_at": txn.verified_at.isoformat() if txn.verified_at else None,
                "rejection_reason": txn.rejection_reason if txn.rejection_reason else None,
                "created_at": txn.created_at.isoformat() if txn.created_at else None,
            })
    
    # -----------------------------
    # LAST EXAM
    # -----------------------------
    last_exam = (
        db.query(StudentExamData)
        .options(joinedload(StudentExamData.exam))
        .filter(StudentExamData.student_id == student.id)
        .order_by(StudentExamData.submitted_at.desc())
        .first()
    )


      # -------------------------
    # LAST EXAM
    # -------------------------
    last_exam = (
        db.query(StudentExamData)
        .options(joinedload(StudentExamData.exam))
        .filter(StudentExamData.student_id == student.id)
        .order_by(StudentExamData.submitted_at.desc())
        .first()
    )


    # -------------------------
    # MOCK TEST COUNT
    # -------------------------
    mock_tests_count = (
        db.query(func.count(StudentExamData.id))
        .join(Exam, Exam.id == StudentExamData.exam_id)
        .filter(
            StudentExamData.student_id == student.id,
            Exam.exam_type == ExamTypeEnum.MOCK,
            StudentExamData.is_submitted == True
        )
        .scalar()
    )


    # -------------------------
    # RANK TEST COUNT
    # -------------------------
    rank_tests_count = (
        db.query(func.count(StudentExamData.id))
        .join(Exam, Exam.id == StudentExamData.exam_id)
        .filter(
            StudentExamData.student_id == student.id,
            Exam.exam_type == ExamTypeEnum.RANK,
            StudentExamData.is_submitted == True
        )
        .scalar()
    )


    # -------------------------
    # RANK TEST RESULTS
    # -------------------------
    rank_test_results = (
        db.query(
            Exam.id.label("exam_id"),
            StudentExamData.class_rank,
            StudentExamData.percentage_scored,
            StudentExamData.total_marks_obtained,
        )
        .join(Exam, Exam.id == StudentExamData.exam_id)
        .filter(
            StudentExamData.student_id == student.id,
            Exam.exam_type == ExamTypeEnum.RANK,
            StudentExamData.is_submitted == True
        )
        .order_by(StudentExamData.submitted_at.desc())
        .all()
    )

    rank_tests = [
        {
            "exam_id": r.exam_id,
            "rank": r.class_rank,
            "percentage": r.percentage_scored,
            "marks": r.total_marks_obtained
        }
        for r in rank_test_results
    ]

    # Calculate installment_pending_amount
    class_start_date = student.classes.class_start_date if student.classes else None
    class_end_date = student.classes.class_end_date if student.classes else None
    
    installment_pending_amount = 0.0
    if student_payment:
        installment_pending_amount = calculate_installment_pending_amount(
            course_fee=student_payment.course_fee,
            course_fee_paid=student_payment.course_fee_paid,
            transport_fee=student_payment.transport_fee,
            transport_fee_paid=student_payment.transport_fee_paid,
            tek_school_fee=student_payment.tek_school_fee,
            tek_school_fee_paid=student_payment.tek_school_fee_paid,
            installment_type=student_payment.installment_type,
            class_start_date=class_start_date,
            class_end_date=class_end_date
        )

    return {
        "student_id": student.id,
        "profile_image": student.profile_image,
        "student_name": f"{student.first_name} {student.last_name}",
        "first_name": student.first_name,
        "last_name": student.last_name,
        "gender": student.gender,
        "dob": student.dob,
        "registration_no": student.registration_no,
        "blood_group": student.blood_group,
        "date_of_admission": student.date_of_admission,
        "previous_class_marks_obtained": student.previous_class_marks_obtained,
        "previous_class_overall_percentage": student.previous_class_overall_percentage,
        "previous_class_final_grade": student.previous_class_final_grade,
        "roll_no": student.roll_no,
        "class_id": student.class_id,
        "class_name": student.classes.name,
        "section_name": student.section.name if student.section else None,
        "class_start_date": student.classes.class_start_date.isoformat() if student.classes and student.classes.class_start_date else None,
        "class_end_date": student.classes.class_end_date.isoformat() if student.classes and student.classes.class_end_date else None,
        "created_at": student.created_at,
        "status": student.status.value,
        "status_expiry_date": student.status_expiry_date,
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
            "education": student.parent.education,
            "organization": student.parent.organization
        } if student.parent else None,
        "last_appeared_exam": (
            last_exam.submitted_at.isoformat()
            if last_exam and last_exam.submitted_at
            else None
        ),

        "exam_type": (
            last_exam.exam.exam_type
            if last_exam and last_exam.exam
            else None
        ),

        "exam_result": (
            last_exam.status.value
            if last_exam and last_exam.status
            else None
        ),
        "exam_statistics": {

            "mock_tests_given": mock_tests_count or 0,
            "rank_tests_given": rank_tests_count or 0,

            "rank_tests": rank_tests
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
            "transport_fee": float(student_payment.transport_fee) if student_payment else 0.0,
            "transport_fee_paid": float(student_payment.transport_fee_paid) if student_payment else 0.0,
            "transport_fee_remaining": round(float(student_payment.transport_fee) - float(student_payment.transport_fee_paid), 2) if student_payment and student_payment.transport_fee is not None and student_payment.transport_fee_paid is not None else 0.0,
            "tek_school_fee": float(student_payment.tek_school_fee) if student_payment else 0.0,
            "tek_school_fee_paid": float(student_payment.tek_school_fee_paid) if student_payment else 0.0,
            "tek_school_fee_remaining": round(float(student_payment.tek_school_fee) - float(student_payment.tek_school_fee_paid), 2) if student_payment and student_payment.tek_school_fee is not None and student_payment.tek_school_fee_paid is not None else 0.0,
            "installment_type": student_payment.installment_type if student_payment and student_payment.installment_type else None,
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
            "installment_pending_amount": installment_pending_amount,
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
    # Allow only school (business only) or teacher
    if current_user.role not in [UserRole.SCHOOL, UserRole.TEACHER]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only schools and teachers can update student profiles."
        )

    # ✅ For SCHOOL users, verify business account access
    if current_user.role == UserRole.SCHOOL:
        verify_school_business_access(current_user, db)

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
            "registration_no", "blood_group", "date_of_admission", "previous_class_marks_obtained",
            "previous_class_overall_percentage", "previous_class_final_grade",
            "class_id", "section_id", "is_transport", "driver_id","pickup_point","pickup_time","drop_point","drop_time"
        ]
    else:
        allowed_fields = [
            "first_name", "last_name", "gender", "dob",
            "registration_no", "blood_group", "date_of_admission", "previous_class_marks_obtained",
            "previous_class_overall_percentage", "previous_class_final_grade",
            "class_id", "section_id"
        ]

    # Handle transport validation (school only - business account required)
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

    # ✅ Handle payment update if provided (similar to create_student)
    payment_updated = False
    payment_response = None
    updated_payment_obj = None  # Store the payment object for refreshing
    
    if data.payment is not None:
        # Determine which class_id to use for payment update
        # If class_id is being updated, use the new class_id; otherwise use current class_id
        target_class_id = data.class_id if data.class_id is not None else student.class_id
        
        if target_class_id is None:
            raise HTTPException(
                status_code=400,
                detail="Cannot update payment: student must have a class_id. Please set class_id first."
            )
        
        # Verify class exists and belongs to school
        class_obj = db.query(Class).filter(
            Class.id == target_class_id,
            Class.school_id == school_id
        ).first()
        
        if not class_obj:
            raise HTTPException(
                status_code=404,
                detail=f"Class {target_class_id} not found or does not belong to your school."
            )
        
        # Map string enum values to InstallmentType enum
        installment_type_map = {
            "monthly": InstallmentType.MONTHLY,
            "quarterly": InstallmentType.QUARTERLY,
            "half_yearly": InstallmentType.HALF_YEARLY,
            "yearly": InstallmentType.YEARLY
        }
        
        # Check if payment record exists for this student and class
        existing_payment = db.query(StudentPayment).filter(
            StudentPayment.student_id == student.id,
            StudentPayment.class_id == target_class_id
        ).first()
        
        if existing_payment:
            # Update existing payment record
            existing_payment.course_fee = data.payment.course_fee
            existing_payment.transport_fee = data.payment.transport_fee
            existing_payment.tek_school_fee = data.payment.tek_school_fee
            existing_payment.installment_type = installment_type_map[data.payment.installment_type].value
            payment_updated = True
            updated_payment_obj = existing_payment
            payment_response = {
                "payment_id": existing_payment.id,
                "class_id": existing_payment.class_id,
                "course_fee": existing_payment.course_fee,
                "transport_fee": existing_payment.transport_fee,
                "tek_school_fee": existing_payment.tek_school_fee,
                "installment_type": existing_payment.installment_type,
                "action": "updated"
            }
        else:
            # Create new payment record for this class
            new_payment = StudentPayment(
                student_id=student.id,
                class_id=target_class_id,
                course_fee=data.payment.course_fee,
                transport_fee=data.payment.transport_fee,
                tek_school_fee=data.payment.tek_school_fee,
                installment_type=installment_type_map[data.payment.installment_type].value
            )
            db.add(new_payment)
            payment_updated = True
            updated_payment_obj = new_payment
            payment_response = {
                "payment_id": new_payment.id,
                "class_id": new_payment.class_id,
                "course_fee": new_payment.course_fee,
                "transport_fee": new_payment.transport_fee,
                "tek_school_fee": new_payment.tek_school_fee,
                "installment_type": new_payment.installment_type,
                "action": "created"
            }

    try:
        db.commit()
        db.refresh(student)
        
        # Refresh payment if it was updated
        if payment_updated and updated_payment_obj:
            db.refresh(updated_payment_obj)
        
        # Log action
        log_action(
            db=db,
            current_user=current_user,
            action_type=ActionType.UPDATE,
            resource_type=ResourceType.STUDENT,
            resource_id=str(student.id),
            description=f"Updated student: {student.first_name} {student.last_name}",
            metadata={
                "student_id": student.id,
                "updated_fields": list(update_data.keys()),
                "payment_updated": payment_updated
            }
        )
        
        response = {"detail": "Student profile updated successfully."}
        if payment_updated and payment_response:
            response["payment"] = payment_response
        
        return response
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
            joinedload(Student.exam_data),
            joinedload(Student.school),
            joinedload(Student.driver)  # ✅ added this
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
        "registration_no": student.registration_no,
        "school_name": student.school.school_name if student.school else None,
        "board": student.school.school_board if student.school else None,
        "class_name": student.classes.name if student.classes else None,
        "section_name": student.section.name if student.section else None,
        "blood_group": student.blood_group,
        "date_of_admission": student.date_of_admission,
        "previous_class_marks_obtained": student.previous_class_marks_obtained,
        "previous_class_overall_percentage": student.previous_class_overall_percentage,
        "previous_class_final_grade": student.previous_class_final_grade,
        "created_at": student.created_at,
        "total_attendance": len(student.attendances) if student.attendances else 0,
        "total_exams": len(student.exam_data) if student.exam_data else 0,
        "last_appeared_exam": last_exam.submitted_at if last_exam else None,
        "status": student.status,
        "expiry": student.status_expiry_date,

        # ✅ Transport Details
        "transport_details": {
            "vehicle_number": student.driver.vechicle_number,
            "vehicle_name": student.driver.vechicle_name,
            "driver_name": student.driver.driver_name,
            "driver_phone": student.driver.phone_no,
            "duty_start_time": student.driver.duty_start_time,
            "duty_end_time": student.driver.duty_end_time,
        } if student.driver else None,

        "pickup_point": student.pickup_point,
        "pickup_time": student.pickup_time,
        "drop_point": student.drop_point,
        "drop_time": student.drop_time,

        "parent": {
            "parent_name": student.parent.parent_name,
            "relation": student.parent.relation,
            "phone": student.parent.phone,
            "email": student.parent.email,
            "occupation": student.parent.occupation,
            "education": student.parent.education,
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


@router.get("/students/me/dashboard-summary/")
def get_student_dashboard_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.STUDENT)),
):
    student = (
        db.query(Student)
        .filter(Student.user_id == current_user.id)
        .first()
    )
    if not student:
        raise HTTPException(status_code=404, detail="Student profile not found.")

    visible_exams = _student_visible_active_exams_query(db, student)
    total_mock_test = visible_exams.filter(Exam.exam_type == ExamTypeEnum.MOCK).count()
    rank_test_total = visible_exams.filter(Exam.exam_type == ExamTypeEnum.RANK).count()

    attend_mock_test = (
        db.query(func.count(StudentExamData.id))
        .join(Exam, Exam.id == StudentExamData.exam_id)
        .filter(
            StudentExamData.student_id == student.id,
            Exam.exam_type == ExamTypeEnum.MOCK,
            StudentExamData.is_submitted == True,
        )
        .scalar()
    ) or 0

    rank_test_attend = (
        db.query(func.count(StudentExamData.id))
        .join(Exam, Exam.id == StudentExamData.exam_id)
        .filter(
            StudentExamData.student_id == student.id,
            Exam.exam_type == ExamTypeEnum.RANK,
            StudentExamData.is_submitted == True,
        )
        .scalar()
    ) or 0

    attendance_present = (
        db.query(func.count(Attendance.id))
        .filter(
            Attendance.student_id == student.id,
            func.upper(Attendance.status) == "P",
        )
        .scalar()
    ) or 0

    attendance_absent = (
        db.query(func.count(Attendance.id))
        .filter(
            Attendance.student_id == student.id,
            func.upper(Attendance.status) == "A",
        )
        .scalar()
    ) or 0

    return {
        "attendance_present": attendance_present,
        "attendance_absent": attendance_absent,
        "total_mock_test": total_mock_test,
        "attend_mock_test": attend_mock_test,
        "rank_test_total": rank_test_total,
        "rank_test_attend": rank_test_attend,
    }


@router.get("/students/me/attendance-percentage/")
def get_student_attendance_percentage(
    month: int = Query(..., ge=1, le=12, description="Calendar month (1-12)"),
    year: int = Query(..., ge=2000, le=2100, description="Four-digit year"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.STUDENT)),
):
    student = (
        db.query(Student)
        .filter(Student.user_id == current_user.id)
        .first()
    )
    if not student:
        raise HTTPException(status_code=404, detail="Student profile not found.")

    period_start = date(year, month, 1)
    period_end = date(year, month, monthrange(year, month)[1])

    present_count = (
        db.query(func.count(Attendance.id))
        .filter(
            Attendance.student_id == student.id,
            Attendance.date >= period_start,
            Attendance.date <= period_end,
            func.upper(Attendance.status) == "P",
        )
        .scalar()
    ) or 0

    absent_count = (
        db.query(func.count(Attendance.id))
        .filter(
            Attendance.student_id == student.id,
            Attendance.date >= period_start,
            Attendance.date <= period_end,
            func.upper(Attendance.status) == "A",
        )
        .scalar()
    ) or 0

    total_marked = present_count + absent_count
    if total_marked == 0:
        present_pct = 0.0
        absent_pct = 0.0
    else:
        present_pct = round(100.0 * present_count / total_marked, 2)
        absent_pct = round(100.0 * absent_count / total_marked, 2)

    return {
        "month": month,
        "year": year,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "present_count": present_count,
        "absent_count": absent_count,
        "attendance_present_percentage": present_pct,
        "attendance_absent_percentage": absent_pct,
    }


@router.get("/e-books/subjects/")
def get_student_subjects(
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(UserRole.STUDENT)),
):
    # Get student
    student = (
        db.query(Student)
        .filter(Student.user_id == current_user.id)
        .first()
    )

    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    if not student.class_id:
        raise HTTPException(status_code=400, detail="Student class not assigned")

    # Get subjects mapped to this class
    subjects = (
        db.query(SchoolClassSubject)
        .join(
            class_subjects,
            class_subjects.c.school_class_subject_id == SchoolClassSubject.id
        )
        .filter(class_subjects.c.class_id == student.class_id)
        .all()
    )

    if not subjects:
        raise HTTPException(status_code=404, detail="No subjects found for this class")

    return [
        {
            "subject_id": subject.id,
            "subject_name": subject.subject
        }
        for subject in subjects
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
    # 3️⃣ Check student's class matches chapter's subject
    class_subject = chapter.school_class_subject

    is_allowed = db.query(class_subjects).filter(
        class_subjects.c.class_id == student.class_id,
        class_subjects.c.school_class_subject_id == class_subject.id
    ).first()

    if not is_allowed:
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

@router.get(
    "/students/bank-accounts/",
    summary="Get student bank accounts",
    description="Retrieve all bank accounts available for the student's school for payment purposes.",
    response_model=List[BankAccountResponse]
)
def get_student_bank_accounts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get all bank accounts for the student's school.
    Students can use this to know which bank accounts they can pay into.
    """
    try:
        # ✅ VALIDATION: Only STUDENT role can access this endpoint
        if current_user.role != UserRole.STUDENT:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only students can access bank account information."
            )

        # ✅ Get student profile to determine school_id
        student = db.query(Student).filter(
            Student.user_id == current_user.id
        ).first()
        
        if not student:
            raise HTTPException(status_code=404, detail="Student profile not found.")

        # ✅ Get all bank accounts for the student's school
        bank_accounts = db.query(BankAccount).filter(
            BankAccount.school_id == student.school_id
        ).order_by(BankAccount.is_primary.desc(), BankAccount.created_at.desc()).all()

        return bank_accounts

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve bank accounts: {str(e)}")


@router.get(
    "/students/{student_id}/payments/",
    summary="Get all student payments",
    description="Retrieve all payment records for a student across all classes, including fee details and installment information."
)
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
        verify_school_business_access(current_user, db)
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
            "course_fee_paid": payment.course_fee_paid,
            "course_fee_remaining": round(payment.course_fee - payment.course_fee_paid, 2),
            "transport_fee": payment.transport_fee,
            "transport_fee_paid": payment.transport_fee_paid,
            "transport_fee_remaining": round(payment.transport_fee - payment.transport_fee_paid, 2),
            "tek_school_fee": payment.tek_school_fee,
            "tek_school_fee_paid": payment.tek_school_fee_paid,
            "tek_school_fee_remaining": round(payment.tek_school_fee - payment.tek_school_fee_paid, 2),
            "installment_type": payment.installment_type,
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

@router.put(
    "/students/{student_id}/payment-structure/{class_id}/",
    summary="Update student payment structure",
    description="Update a student's payment structure including course fee, transport fee, tek school fee, and installment type for a specific class."
)
def update_student_payment_structure(
    student_id: int,
    class_id: int,
    data: StudentPaymentCreate,
    db: Session = Depends(get_db),
    current_user = Depends(require_roles(UserRole.SCHOOL, UserRole.STAFF))
):
    """
    Update payment structure (fee structure) for a student in a specific class.
    This updates the fee amounts and installment types, similar to student creation.
    Only SCHOOL and STAFF roles can update payment structure.
    """
    # ✅ Determine school_id based on user role
    if current_user.role == UserRole.SCHOOL:
        verify_school_business_access(current_user, db)
        school_id = current_user.school_profile.id
    elif current_user.role == UserRole.STAFF:
        staff = db.query(Staff).filter(Staff.user_id == current_user.id).first()
        if not staff:
            raise HTTPException(status_code=404, detail="Staff profile not found.")
        school_id = staff.school_id
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only schools and staff can update payment structure."
        )

    # Verify student belongs to the school
    student = db.query(Student).filter(
        Student.id == student_id,
        Student.school_id == school_id
    ).first()
    
    if not student:
        raise HTTPException(status_code=404, detail="Student not found or not part of your school.")

    # Verify class exists and belongs to school
    class_obj = db.query(Class).filter(
        Class.id == class_id,
        Class.school_id == school_id
    ).first()
    
    if not class_obj:
        raise HTTPException(
            status_code=404,
            detail=f"Class {class_id} not found or does not belong to your school."
        )

    # Map string enum values to InstallmentType enum
    installment_type_map = {
        "monthly": InstallmentType.MONTHLY,
        "quarterly": InstallmentType.QUARTERLY,
        "half_yearly": InstallmentType.HALF_YEARLY,
        "yearly": InstallmentType.YEARLY
    }

    # Check if payment record exists for this student and class
    existing_payment = db.query(StudentPayment).filter(
        StudentPayment.student_id == student_id,
        StudentPayment.class_id == class_id
    ).first()

    # ✅ VALIDATION: If payment exists, ensure new fees are not less than already paid amounts
    if existing_payment:
        if data.course_fee < existing_payment.course_fee_paid:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot set course fee to {data.course_fee}. Student has already paid {existing_payment.course_fee_paid}. Please reduce paid amount first or set a higher fee."
            )
        if data.transport_fee < existing_payment.transport_fee_paid:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot set transport fee to {data.transport_fee}. Student has already paid {existing_payment.transport_fee_paid}. Please reduce paid amount first or set a higher fee."
            )
        if data.tek_school_fee < existing_payment.tek_school_fee_paid:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot set tek school fee to {data.tek_school_fee}. Student has already paid {existing_payment.tek_school_fee_paid}. Please reduce paid amount first or set a higher fee."
            )
        
        # Update existing payment structure
        existing_payment.course_fee = data.course_fee
        existing_payment.transport_fee = data.transport_fee
        existing_payment.tek_school_fee = data.tek_school_fee
        existing_payment.installment_type = installment_type_map[data.installment_type.value].value
        
        payment_obj = existing_payment
        action = "updated"
    else:
        # Create new payment record for this class
        new_payment = StudentPayment(
            student_id=student_id,
            class_id=class_id,
            course_fee=data.course_fee,
            transport_fee=data.transport_fee,
            tek_school_fee=data.tek_school_fee,
            installment_type=installment_type_map[data.installment_type.value].value
        )
        db.add(new_payment)
        payment_obj = new_payment
        action = "created"

    try:
        db.commit()
        db.refresh(payment_obj)
        
        # Log action
        log_action(
            db=db,
            current_user=current_user,
            action_type=ActionType.UPDATE if action == "updated" else ActionType.CREATE,
            resource_type=ResourceType.STUDENT,
            resource_id=str(student.id),
            description=f"{action.capitalize()} payment structure for student {student.first_name} {student.last_name} in class {class_id}",
            metadata={
                "student_id": student.id,
                "class_id": class_id,
                "payment_id": payment_obj.id,
                "action": action
            }
        )
        
        return {
            "detail": f"Payment structure {action} successfully.",
            "payment_id": payment_obj.id,
            "student_id": student_id,
            "student_name": f"{student.first_name} {student.last_name}",
            "class_id": class_id,
            "class_name": class_obj.name,
            "course_fee": payment_obj.course_fee,
            "transport_fee": payment_obj.transport_fee,
            "tek_school_fee": payment_obj.tek_school_fee,
            "installment_type": payment_obj.installment_type,
            "course_fee_paid": payment_obj.course_fee_paid,
            "transport_fee_paid": payment_obj.transport_fee_paid,
            "tek_school_fee_paid": payment_obj.tek_school_fee_paid,
            "action": action
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update payment structure: {str(e)}")

@router.get(
    "/students/{student_id}/payments/{class_id}/",
    summary="Get student payment by class",
    description="Retrieve payment details for a specific student and class combination, including fee breakdown, payment history, and installment pending amount."
)
def get_student_payment_by_class(
    student_id: int,
    class_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(require_roles(UserRole.SCHOOL, UserRole.TEACHER, UserRole.STAFF))
):
    # ✅ Determine school_id based on user role
    if current_user.role == UserRole.SCHOOL:
        verify_school_business_access(current_user, db)
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
            "amount": float(txn.amount),
            "payment_type": txn.payment_type,
            "payment_breakdown": txn.payment_breakdown if txn.payment_breakdown else None,
            "transaction_date": txn.transaction_date.isoformat() if txn.transaction_date else None,
            "description": txn.description,
            "files": txn.files if txn.files else [],
            "payment_method": txn.payment_method,
            "transaction_reference": txn.transaction_reference,
            "bank_account_id": txn.bank_account_id if txn.bank_account_id else None,  # Add bank_account_id
            "status": txn.status if txn.status else 'verified',  # Add status field
            "verified_at": txn.verified_at.isoformat() if txn.verified_at else None,  # Add verified_at
            "verified_by": txn.verified_by,  # Add verified_by
            "rejection_reason": txn.rejection_reason if txn.rejection_reason else None,  # Add rejection_reason
            "created_at": txn.created_at.isoformat() if txn.created_at else None,
            "created_by": txn.created_by
        }
        
        transaction_list.append(transaction_data)
    
    # Get class dates
    class_start_date = payment.classes.class_start_date if payment.classes else None
    class_end_date = payment.classes.class_end_date if payment.classes else None
    
    # Calculate installment_pending_amount using utility function
    installment_pending_amount = calculate_installment_pending_amount(
        course_fee=payment.course_fee,
        course_fee_paid=payment.course_fee_paid,
        transport_fee=payment.transport_fee,
        transport_fee_paid=payment.transport_fee_paid,
        tek_school_fee=payment.tek_school_fee,
        tek_school_fee_paid=payment.tek_school_fee_paid,
        installment_type=payment.installment_type,
        class_start_date=class_start_date,
        class_end_date=class_end_date
    )
    
    return {
        "payment_id": payment.id,
        "student_id": payment.student_id,
        "student_name": f"{student.first_name} {student.last_name}",
        "class_id": payment.class_id,
        "class_name": payment.classes.name if payment.classes else None,
        "class_start_date": class_start_date.isoformat() if class_start_date else None,  # Add class_start_date
        "class_end_date": class_end_date.isoformat() if class_end_date else None,  # Add class_end_date
        "course_fee": float(payment.course_fee),
        "course_fee_paid": float(payment.course_fee_paid),
        "course_fee_remaining": round(payment.course_fee - payment.course_fee_paid, 2),
        "transport_fee": float(payment.transport_fee),
        "transport_fee_paid": float(payment.transport_fee_paid),
        "transport_fee_remaining": round(payment.transport_fee - payment.transport_fee_paid, 2),
        "tek_school_fee": float(payment.tek_school_fee),
        "tek_school_fee_paid": float(payment.tek_school_fee_paid),
        "tek_school_fee_remaining": round(payment.tek_school_fee - payment.tek_school_fee_paid, 2),
        "installment_type": payment.installment_type if payment.installment_type else None,
        "total_paid": round(payment.course_fee_paid + payment.transport_fee_paid + payment.tek_school_fee_paid, 2),
        "total_remaining": round(
            (payment.course_fee - payment.course_fee_paid) + 
            (payment.transport_fee - payment.transport_fee_paid) + 
            (payment.tek_school_fee - payment.tek_school_fee_paid), 2
        ),
        "installment_pending_amount": installment_pending_amount,
        "transactions": transaction_list,  # Now includes status, verified_at, verified_by, rejection_reason
        "total_transactions": len(transaction_list),
        "created_at": payment.created_at.isoformat() if payment.created_at else None,
        "updated_at": payment.updated_at.isoformat() if payment.updated_at else None
    }

@router.post(
    "/students/{student_id}/payments/{class_id}/",
    summary="Create payment transaction",
    description="Create a new payment transaction for a student in a specific class. This is typically used when recording a payment manually."
)
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
        verify_school_business_access(current_user, db)
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

    settlement_bank_account_id = resolve_student_fee_settlement_bank_account_id(
        data.payment_method, data.bank_account_id
    )
    if settlement_bank_account_id is not None:
        ba = (
            db.query(BankAccount)
            .filter(
                BankAccount.id == settlement_bank_account_id,
                BankAccount.school_id == school_id,
            )
            .first()
        )
        if not ba:
            raise HTTPException(
                status_code=400,
                detail="Invalid bank_account_id for this school.",
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
        bank_account_id=settlement_bank_account_id,
        created_by=current_user.id
    )
    db.add(transaction)
    transactions_created = [transaction]

    # Update student status to ACTIVE and set expiry date
    if total_amount > 0:
        validity_days = 90  # default
        if payment and payment.installment_type:
            inst_type = payment.installment_type.lower()
            if inst_type == "monthly":
                validity_days = 30
            elif inst_type == "quarterly":
                validity_days = 90
            elif inst_type == "half_yearly":
                validity_days = 180
            elif inst_type == "yearly":
                validity_days = 365

        now = datetime.utcnow()
        student.status = StudentStatus.ACTIVE
        if student.status_expiry_date and student.status_expiry_date > now:
            student.status_expiry_date = student.status_expiry_date + timedelta(days=validity_days)
        else:
            student.status_expiry_date = now + timedelta(days=validity_days)

    try:
        db.flush()
        if total_amount > 0:
            record_student_fee_credit(
                db,
                school_id=school_id,
                bank_account_id=settlement_bank_account_id,
                credited_amount=float(total_amount),
                source_reference=f"student_payment_transaction:{transaction.id}",
                description=f"Manual student payment student_id={student_id} class_id={class_id}",
                recorded_by_user_id=current_user.id,
            )
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
            "course_fee_paid": payment.course_fee_paid,
            "course_fee_remaining": course_fee_remaining,
            "transport_fee": payment.transport_fee,
            "transport_fee_paid": payment.transport_fee_paid,
            "transport_fee_remaining": transport_fee_remaining,
            "tek_school_fee": payment.tek_school_fee,
            "tek_school_fee_paid": payment.tek_school_fee_paid,
            "tek_school_fee_remaining": tek_school_fee_remaining,
            "installment_type": payment.installment_type,
            "total_paid": round(payment.course_fee_paid + payment.transport_fee_paid + payment.tek_school_fee_paid, 2),
            "total_remaining": total_remaining,
            "created_at": transaction.created_at
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create payment transaction: {str(e)}")

@router.patch(
    "/students/{student_id}/payments/{class_id}/",
    summary="Update student payment",
    description="Update an existing payment record for a student in a specific class, including fee amounts and paid amounts."
)
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
        verify_school_business_access(current_user, db)
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
    
    # ✅ VALIDATION: If reducing fee amounts, ensure existing paid amounts don't exceed new fee amounts
    # Check before updating to validate against current paid amounts
    if "course_fee" in update_data and update_data["course_fee"] is not None:
        new_course_fee = update_data["course_fee"]
        if new_course_fee < payment.course_fee_paid:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot reduce course fee to {new_course_fee}. Student has already paid {payment.course_fee_paid}. Please reduce paid amount first or set a higher fee."
            )
        payment.course_fee = new_course_fee
    
    if "transport_fee" in update_data and update_data["transport_fee"] is not None:
        new_transport_fee = update_data["transport_fee"]
        if new_transport_fee < payment.transport_fee_paid:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot reduce transport fee to {new_transport_fee}. Student has already paid {payment.transport_fee_paid}. Please reduce paid amount first or set a higher fee."
            )
        payment.transport_fee = new_transport_fee
    
    if "tek_school_fee" in update_data and update_data["tek_school_fee"] is not None:
        new_tek_school_fee = update_data["tek_school_fee"]
        if new_tek_school_fee < payment.tek_school_fee_paid:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot reduce tek school fee to {new_tek_school_fee}. Student has already paid {payment.tek_school_fee_paid}. Please reduce paid amount first or set a higher fee."
            )
        payment.tek_school_fee = new_tek_school_fee
    
    if "installment_type" in update_data and update_data["installment_type"] is not None:
        payment.installment_type = installment_type_map[update_data["installment_type"].value].value
    
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
    
    # ✅ VALIDATION: Validate bank_account_id if provided
    bank_account = None
    if "bank_account_id" in update_data and update_data["bank_account_id"] is not None:
        bank_account = db.query(BankAccount).filter(
            BankAccount.id == update_data["bank_account_id"],
            BankAccount.school_id == school_id
        ).first()
        
        if not bank_account:
            raise HTTPException(
                status_code=404,
                detail=f"Bank account with ID {update_data['bank_account_id']} not found or does not belong to your school."
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
                bank_account_id=update_data.get("bank_account_id") if "bank_account_id" in update_data else None,
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
                bank_account_id=update_data.get("bank_account_id") if "bank_account_id" in update_data else None,
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
                bank_account_id=update_data.get("bank_account_id") if "bank_account_id" in update_data else None,
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
            "course_fee_paid": payment.course_fee_paid,
            "course_fee_remaining": round(payment.course_fee - payment.course_fee_paid, 2),
            "transport_fee": payment.transport_fee,
            "transport_fee_paid": payment.transport_fee_paid,
            "transport_fee_remaining": round(payment.transport_fee - payment.transport_fee_paid, 2),
            "tek_school_fee": payment.tek_school_fee,
            "tek_school_fee_paid": payment.tek_school_fee_paid,
            "tek_school_fee_remaining": round(payment.tek_school_fee - payment.tek_school_fee_paid, 2),
            "installment_type": payment.installment_type,
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

# ==================== Payment Reminder and Verification Flow ====================

@router.post(
    "/students/{student_id}/payments/{class_id}/send-reminder/",
    summary="Send payment reminder",
    description="School sends a payment reminder/request to a student. This creates a transaction with 'school_request' status that the student can then update with payment details."
)
def send_payment_reminder(
    student_id: int,
    class_id: int,
    data: PaymentReminderRequest,
    db: Session = Depends(get_db),
    current_user = Depends(require_roles(UserRole.SCHOOL, UserRole.STAFF))
):
    try:
        # ✅ VALIDATION: student_id and class_id must be positive
        if student_id <= 0:
            raise HTTPException(status_code=400, detail="Invalid student_id. Must be a positive integer.")
        if class_id <= 0:
            raise HTTPException(status_code=400, detail="Invalid class_id. Must be a positive integer.")

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
                detail="Only schools and staff can send payment reminders."
            )

        # ✅ VALIDATION: Verify student belongs to the school
        student = db.query(Student).options(joinedload(Student.classes)).filter(
            Student.id == student_id,
            Student.school_id == school_id
        ).first()
        
        if not student:
            raise HTTPException(status_code=404, detail="Student not found or not part of your school.")

        # ✅ VALIDATION: Verify class exists and belongs to school
        class_obj = db.query(Class).filter(
            Class.id == class_id,
            Class.school_id == school_id
        ).first()
        
        if not class_obj:
            raise HTTPException(status_code=404, detail="Class not found or does not belong to your school.")

        # ✅ VALIDATION: Verify student is in the specified class
        if student.class_id != class_id:
            raise HTTPException(
                status_code=400, 
                detail=f"Student is not enrolled in class {class_id}. Current class: {student.class_id}"
            )

        # ✅ VALIDATION: Get payment record
        payment = db.query(StudentPayment).filter(
            StudentPayment.student_id == student_id,
            StudentPayment.class_id == class_id
        ).first()

        if not payment:
            raise HTTPException(
                status_code=404,
                detail=f"Payment record not found for student {student_id} in class {class_id}."
            )
        
        # Helper function to calculate remaining amount based on installment type
        def calculate_remaining_by_installment(fee_amount, fee_paid, installment_type, class_start_date, class_end_date):
            """
            Calculate remaining amount based on installment type and class dates.
            Returns the remaining amount for the current installment period.
            """
            remaining_total = fee_amount - fee_paid
            if remaining_total <= 0:
                return 0.0
            
            today = date.today()
            
            # If class has ended, return total remaining
            if today >= class_end_date:
                return round(remaining_total, 2)
            
            # Calculate period based on installment type
            if installment_type == InstallmentType.MONTHLY.value:
                # Calculate months from today to class_end_date
                months_remaining = (class_end_date.year - today.year) * 12 + (class_end_date.month - today.month)
                if class_end_date.day >= today.day:
                    months_remaining += 1
                if months_remaining <= 0:
                    months_remaining = 1
                
                # Calculate total months in class period
                total_months = (class_end_date.year - class_start_date.year) * 12 + (class_end_date.month - class_start_date.month)
                if class_end_date.day >= class_start_date.day:
                    total_months += 1
                if total_months <= 0:
                    total_months = 1
                
                # Monthly amount
                monthly_amount = fee_amount / total_months
                # Remaining amount for remaining months
                remaining_amount = monthly_amount * months_remaining
                
            elif installment_type == InstallmentType.QUARTERLY.value:
                # Calculate quarters from today to class_end_date
                start_quarter = (class_start_date.month - 1) // 3 + 1
                end_quarter = (class_end_date.month - 1) // 3 + 1
                today_quarter = (today.month - 1) // 3 + 1
                
                total_quarters = (class_end_date.year - class_start_date.year) * 4 + (end_quarter - start_quarter) + 1
                if total_quarters <= 0:
                    total_quarters = 1
                
                # Calculate remaining quarters
                if today.year == class_end_date.year:
                    quarters_remaining = end_quarter - today_quarter + 1
                else:
                    quarters_remaining = (class_end_date.year - today.year - 1) * 4 + (4 - today_quarter + 1) + end_quarter
                
                if quarters_remaining <= 0:
                    quarters_remaining = 1
                
                # Quarterly amount
                quarterly_amount = fee_amount / total_quarters
                # Remaining amount for remaining quarters
                remaining_amount = quarterly_amount * quarters_remaining
                
            elif installment_type == InstallmentType.HALF_YEARLY.value:
                # Calculate half-years from today to class_end_date
                start_half = 1 if class_start_date.month <= 6 else 2
                end_half = 1 if class_end_date.month <= 6 else 2
                today_half = 1 if today.month <= 6 else 2
                
                total_half_years = (class_end_date.year - class_start_date.year) * 2 + (end_half - start_half) + 1
                if total_half_years <= 0:
                    total_half_years = 1
                
                # Calculate remaining half-years
                if today.year == class_end_date.year:
                    half_years_remaining = end_half - today_half + 1
                else:
                    half_years_remaining = (class_end_date.year - today.year - 1) * 2 + (2 - today_half + 1) + end_half
                
                if half_years_remaining <= 0:
                    half_years_remaining = 1
                
                # Half-yearly amount
                half_yearly_amount = fee_amount / total_half_years
                # Remaining amount for remaining half-years
                remaining_amount = half_yearly_amount * half_years_remaining
                
            elif installment_type == InstallmentType.YEARLY.value:
                # For yearly, return total remaining
                remaining_amount = remaining_total
            else:
                # Default: return total remaining
                remaining_amount = remaining_total
            
            # Ensure remaining_amount doesn't exceed total remaining
            remaining_amount = min(remaining_amount, remaining_total)
            return round(remaining_amount, 2)
        
        # Calculate remaining amounts based on installment type (same for all fees)
        installment_type_value = payment.installment_type if payment.installment_type else InstallmentType.YEARLY.value
        
        course_fee_remaining = calculate_remaining_by_installment(
            payment.course_fee,
            payment.course_fee_paid,
            installment_type_value,
            class_obj.class_start_date,
            class_obj.class_end_date
        )
        
        transport_fee_remaining = calculate_remaining_by_installment(
            payment.transport_fee,
            payment.transport_fee_paid,
            installment_type_value,
            class_obj.class_start_date,
            class_obj.class_end_date
        )
        
        tek_school_fee_remaining = calculate_remaining_by_installment(
            payment.tek_school_fee,
            payment.tek_school_fee_paid,
            installment_type_value,
            class_obj.class_start_date,
            class_obj.class_end_date
        )
        
        # Calculate total due based on installment-based remaining amounts
        total_due = course_fee_remaining + transport_fee_remaining + tek_school_fee_remaining

        # ✅ VALIDATION: Check if there's any amount due
        if total_due <= 0:
            raise HTTPException(
                status_code=400,
                detail="No payment due. All fees have been paid."
            )

        # ✅ VALIDATION: If fee amounts are provided, validate them against calculated remaining amounts
        validation_errors = []
        if data.course_fee is not None and data.course_fee > 0:
            if data.course_fee > course_fee_remaining:
                validation_errors.append(
                    f"Course fee amount ({data.course_fee}) exceeds calculated remaining amount ({course_fee_remaining:.2f}) for {installment_type_value} installment."
                )
        
        if data.transport_fee is not None and data.transport_fee > 0:
            if data.transport_fee > transport_fee_remaining:
                validation_errors.append(
                    f"Transport fee amount ({data.transport_fee}) exceeds calculated remaining amount ({transport_fee_remaining:.2f}) for {installment_type_value} installment."
                )
        
        if data.tek_school_fee is not None and data.tek_school_fee > 0:
            if data.tek_school_fee > tek_school_fee_remaining:
                validation_errors.append(
                    f"Tek School fee amount ({data.tek_school_fee}) exceeds calculated remaining amount ({tek_school_fee_remaining:.2f}) for {installment_type_value} installment."
                )
        
        if validation_errors:
            raise HTTPException(
                status_code=400,
                detail="; ".join(validation_errors)
            )

        # ✅ VALIDATION: Validate amount_due if provided
        # If fee amounts are provided, amount_due should match their sum
        # Otherwise, it should match the calculated total_due
        if data.amount_due is not None:
            if data.amount_due < 0:
                raise HTTPException(status_code=400, detail="Amount due cannot be negative.")
            
            # Calculate expected amount_due
            provided_fee_sum = (data.course_fee or 0) + (data.transport_fee or 0) + (data.tek_school_fee or 0)
            
            if provided_fee_sum > 0:
                # If fee amounts are provided, amount_due should be their sum
                if abs(data.amount_due - provided_fee_sum) > 0.01:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Provided amount_due ({data.amount_due}) does not match sum of provided fee amounts ({provided_fee_sum:.2f})."
                    )
            else:
                # If no fee amounts provided, amount_due should match calculated total
                if abs(data.amount_due - total_due) > 0.01:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Provided amount_due ({data.amount_due}) does not match calculated remaining amount ({total_due:.2f})."
                    )

        # ✅ VALIDATION: Validate bank_account_id if provided
        bank_account = None
        if data.bank_account_id is not None:
            bank_account = db.query(BankAccount).filter(
                BankAccount.id == data.bank_account_id,
                BankAccount.school_id == school_id
            ).first()
            
            if not bank_account:
                raise HTTPException(
                    status_code=404,
                    detail=f"Bank account with ID {data.bank_account_id} not found or does not belong to your school."
                )

        # Create payment request transaction with status "school_request"
        # Check if there's already a pending school_request for this payment
        existing_request = db.query(StudentPaymentTransaction).filter(
            StudentPaymentTransaction.student_payment_id == payment.id,
            StudentPaymentTransaction.status == PaymentTransactionStatus.SCHOOL_REQUEST.value
        ).first()

        # Calculate payment breakdown from provided fee fields
        payment_breakdown = {}
        total_amount = 0.0
        
        if data.course_fee is not None and data.course_fee > 0:
            payment_breakdown["course_fee"] = round(data.course_fee, 2)
            total_amount += data.course_fee
        
        if data.transport_fee is not None and data.transport_fee > 0:
            payment_breakdown["transport_fee"] = round(data.transport_fee, 2)
            total_amount += data.transport_fee
        
        if data.tek_school_fee is not None and data.tek_school_fee > 0:
            payment_breakdown["tek_school_fee"] = round(data.tek_school_fee, 2)
            total_amount += data.tek_school_fee

        # Determine primary payment type
        primary_payment_type = "course_fee"
        if data.transport_fee and data.transport_fee > 0:
            primary_payment_type = "transport_fee"
        if data.tek_school_fee and data.tek_school_fee > 0:
            primary_payment_type = "tek_school_fee"

        if existing_request:
            # Update existing request
            existing_request.transaction_date = datetime.utcnow()
            existing_request.description = data.message if data.message else existing_request.description
            existing_request.amount = round(total_amount, 2) if total_amount > 0 else existing_request.amount
            existing_request.payment_type = primary_payment_type if total_amount > 0 else existing_request.payment_type
            existing_request.payment_breakdown = payment_breakdown if payment_breakdown else existing_request.payment_breakdown
            existing_request.bank_account_id = data.bank_account_id if data.bank_account_id else existing_request.bank_account_id
            transaction = existing_request
            db.commit()
            db.refresh(transaction)
        else:
            # Create new payment request
            transaction = StudentPaymentTransaction(
                student_payment_id=payment.id,
                amount=round(total_amount, 2) if total_amount > 0 else 0.0,  # Amount from fee fields or 0
                payment_type=primary_payment_type if total_amount > 0 else "course_fee",  # Default, will be updated by student
                payment_breakdown=payment_breakdown if payment_breakdown else None,  # Fee breakdown from request
                transaction_date=datetime.utcnow(),
                description=data.message if data.message else f"Payment request for {student.first_name} {student.last_name}",
                files=None,
                payment_method=None,
                transaction_reference=None,
                bank_account_id=data.bank_account_id if data.bank_account_id else None,
                status=PaymentTransactionStatus.SCHOOL_REQUEST.value,
                created_by=current_user.id
            )
            db.add(transaction)
            db.commit()
            db.refresh(transaction)

        # Send email to student/parent if they have email
        email_sent = None
        if student.parent and student.parent.email:
            try:
                class_name = student.classes.name if student.classes else 'Class'
                email_subject = f"Payment Request - {class_name}"
                # Build requested amounts section if provided
                requested_section = ""
                if payment_breakdown:
                    requested_section = "<p><strong>Requested Payment Amounts:</strong></p><ul>"
                    installment_type_display = data.installment_type.value if data.installment_type else payment.installment_type if payment.installment_type else "N/A"
                    if "course_fee" in payment_breakdown:
                        requested_section += f"<li>Course Fee: ₹{payment_breakdown['course_fee']:.2f} ({installment_type_display})</li>"
                    if "transport_fee" in payment_breakdown:
                        requested_section += f"<li>Transport Fee: ₹{payment_breakdown['transport_fee']:.2f} ({installment_type_display})</li>"
                    if "tek_school_fee" in payment_breakdown:
                        requested_section += f"<li>Tek School Fee: ₹{payment_breakdown['tek_school_fee']:.2f} ({installment_type_display})</li>"
                    requested_section += "</ul>"
                
                email_body = f"""
                <h2>Payment Request</h2>
                <p>Dear {student.parent.parent_name},</p>
                <p>This is a payment request for {student.first_name} {student.last_name} (Roll No: {student.roll_no}).</p>
                <p><strong>Total Amount Due (Based on Installment Type): ₹{total_due:.2f}</strong></p>
                <p>Remaining Balances (Calculated by Installment Type):</p>
                <ul>
                    <li>Course Fee Remaining ({installment_type_value}): ₹{course_fee_remaining:.2f}</li>
                    <li>Transport Fee Remaining ({installment_type_value}): ₹{transport_fee_remaining:.2f}</li>
                    <li>Tek School Fee Remaining ({installment_type_value}): ₹{tek_school_fee_remaining:.2f}</li>
                </ul>
                <p><small>Note: Amounts are calculated based on remaining time period from today ({date.today().isoformat()}) to class end date ({class_obj.class_end_date.isoformat()}) and installment type.</small></p>
                {requested_section}
                {f'<p>{data.message}</p>' if data.message else ''}
                <p>Please fill the payment form in the student portal.</p>
                <p>Thank you.</p>
                """
                send_dynamic_email(
                    recipient_email=student.parent.email,
                    subject=email_subject,
                    body=email_body
                )
                email_sent = student.parent.email
            except Exception as e:
                print(f"Warning: Failed to send email reminder: {str(e)}")
                # Continue even if email fails

        # Determine the installment_type to return (from request or payment record)
        response_installment_type = data.installment_type.value if data.installment_type else installment_type_value
        
        return {
            "detail": "Payment request created successfully",
            "transaction_id": transaction.id,
            "student_id": student_id,
            "student_name": f"{student.first_name} {student.last_name}",
            "total_due": round(total_due, 2),
            "status": transaction.status,
            "installment_type": response_installment_type,
            "payment_breakdown": transaction.payment_breakdown if transaction.payment_breakdown else None,
            "calculated_remaining_amounts": {
                "course_fee_remaining": course_fee_remaining,
                "transport_fee_remaining": transport_fee_remaining,
                "tek_school_fee_remaining": tek_school_fee_remaining,
            },
            "requested_amounts": {
                "course_fee": data.course_fee if data.course_fee else None,
                "transport_fee": data.transport_fee if data.transport_fee else None,
                "tek_school_fee": data.tek_school_fee if data.tek_school_fee else None,
            },
            "email_sent": email_sent,
            "message": "Student can now fill the payment form with amounts and documents."
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send payment reminder: {str(e)}")


@router.post(
    "/students/send-bulk-reminders/",
    summary="Send payment reminders to multiple students",
    description="Send payment reminders to multiple students at once. For each student, the system automatically calculates the pending amount based on their installment type and creates a payment request transaction."
)
async def send_bulk_payment_reminders(
    data: BulkPaymentReminderRequest,
    db: Session = Depends(get_db),
    current_user = Depends(require_roles(UserRole.SCHOOL, UserRole.STAFF))
):
    """
    School sends payment reminders to multiple students asynchronously.
    For each student, automatically calculates pending amount based on installment type
    and creates a payment request transaction with 'school_request' status.
    Processes students concurrently for better performance.
    """
    
    async def process_single_student(
        student_id: int,
        student_map: dict,
        payment_map: dict,
        school_id: int,
        message: str | None,
        bank_account_id: int | None,
        current_user_id: int
    ) -> dict:
        """Process a single student's payment reminder asynchronously."""
        student_result = {
            "student_id": student_id,
            "success": False,
            "message": "",
            "transaction_id": None,
            "total_due": None,
            "installment_pending_amount": None,
            "email_sent": None
        }
        
        try:
            # Get student
            student = student_map.get(student_id)
            if not student:
                student_result["message"] = "Student not found or not part of your school."
                return student_result

            # Get student's current class
            if not student.class_id:
                student_result["message"] = "Student is not enrolled in any class."
                return student_result

            class_obj = student.classes
            if not class_obj:
                student_result["message"] = "Class not found for student."
                return student_result

            # Get payment record for student's current class
            payment = payment_map.get((student.id, student.class_id))
            if not payment:
                student_result["message"] = f"Payment record not found for student in class {student.class_id}."
                return student_result

            # Calculate installment_pending_amount (total)
            installment_type_value = payment.installment_type if payment.installment_type else InstallmentType.YEARLY.value
            installment_pending_amount = calculate_installment_pending_amount(
                course_fee=payment.course_fee,
                course_fee_paid=payment.course_fee_paid,
                transport_fee=payment.transport_fee,
                transport_fee_paid=payment.transport_fee_paid,
                tek_school_fee=payment.tek_school_fee,
                tek_school_fee_paid=payment.tek_school_fee_paid,
                installment_type=installment_type_value,
                class_start_date=class_obj.class_start_date if class_obj else None,
                class_end_date=class_obj.class_end_date if class_obj else None
            )

            # Check if there's any amount due
            if installment_pending_amount <= 0:
                student_result["message"] = "No payment due. All fees have been paid."
                return student_result

            # Calculate installment-based pending amounts for each fee type
            course_fee_pending = calculate_single_fee_installment_pending(
                fee_amount=payment.course_fee,
                fee_paid=payment.course_fee_paid,
                installment_type=installment_type_value,
                class_start_date=class_obj.class_start_date if class_obj else None,
                class_end_date=class_obj.class_end_date if class_obj else None
            )
            
            transport_fee_pending = calculate_single_fee_installment_pending(
                fee_amount=payment.transport_fee,
                fee_paid=payment.transport_fee_paid,
                installment_type=installment_type_value,
                class_start_date=class_obj.class_start_date if class_obj else None,
                class_end_date=class_obj.class_end_date if class_obj else None
            )
            
            tek_school_fee_pending = calculate_single_fee_installment_pending(
                fee_amount=payment.tek_school_fee,
                fee_paid=payment.tek_school_fee_paid,
                installment_type=installment_type_value,
                class_start_date=class_obj.class_start_date if class_obj else None,
                class_end_date=class_obj.class_end_date if class_obj else None
            )
            
            # Total due is the installment_pending_amount
            total_due = installment_pending_amount

            # Create payment breakdown based on installment-based pending amounts
            payment_breakdown = {}
            if course_fee_pending > 0:
                payment_breakdown["course_fee"] = round(course_fee_pending, 2)
            if transport_fee_pending > 0:
                payment_breakdown["transport_fee"] = round(transport_fee_pending, 2)
            if tek_school_fee_pending > 0:
                payment_breakdown["tek_school_fee"] = round(tek_school_fee_pending, 2)

            # Determine primary payment type
            primary_payment_type = "course_fee"
            if transport_fee_pending > 0:
                primary_payment_type = "transport_fee"
            if tek_school_fee_pending > 0:
                primary_payment_type = "tek_school_fee"

            # Database operations in thread pool
            def create_or_update_transaction():
                # Create a new session for this transaction
                from app.db.session import SessionLocal
                local_db = SessionLocal()
                try:
                    # Check if there's already a pending school_request for this payment
                    existing_request = local_db.query(StudentPaymentTransaction).filter(
                        StudentPaymentTransaction.student_payment_id == payment.id,
                        StudentPaymentTransaction.status == PaymentTransactionStatus.SCHOOL_REQUEST.value
                    ).first()

                    if existing_request:
                        # Update existing request
                        existing_request.transaction_date = datetime.utcnow()
                        existing_request.description = message if message else existing_request.description
                        existing_request.amount = round(total_due, 2)
                        existing_request.payment_type = primary_payment_type
                        existing_request.payment_breakdown = payment_breakdown
                        existing_request.bank_account_id = bank_account_id if bank_account_id else existing_request.bank_account_id
                        transaction = existing_request
                        local_db.commit()
                        local_db.refresh(transaction)
                    else:
                        # Create new payment request
                        transaction = StudentPaymentTransaction(
                            student_payment_id=payment.id,
                            amount=round(total_due, 2),
                            payment_type=primary_payment_type,
                            payment_breakdown=payment_breakdown,
                            transaction_date=datetime.utcnow(),
                            description=message if message else f"Payment request for {student.first_name} {student.last_name}",
                            files=None,
                            payment_method=None,
                            transaction_reference=None,
                            bank_account_id=bank_account_id if bank_account_id else None,
                            status=PaymentTransactionStatus.SCHOOL_REQUEST.value,
                            created_by=current_user_id
                        )
                        local_db.add(transaction)
                        local_db.commit()
                        local_db.refresh(transaction)
                    
                    return transaction.id
                finally:
                    local_db.close()
            
            # Run database operation in thread pool
            transaction_id = await run_in_threadpool(create_or_update_transaction)

            # Send email asynchronously (fire and forget)
            email_sent = None
            if student.parent and student.parent.email:
                async def send_email():
                    try:
                        class_name = student.classes.name if student.classes else 'Class'
                        email_subject = f"Payment Request - {class_name}"
                        
                        # Build requested amounts section
                        requested_section = "<p><strong>Requested Payment Amounts:</strong></p><ul>"
                        installment_type_display = installment_type_value
                        if "course_fee" in payment_breakdown:
                            requested_section += f"<li>Course Fee: ₹{payment_breakdown['course_fee']:.2f} ({installment_type_display})</li>"
                        if "transport_fee" in payment_breakdown:
                            requested_section += f"<li>Transport Fee: ₹{payment_breakdown['transport_fee']:.2f} ({installment_type_display})</li>"
                        if "tek_school_fee" in payment_breakdown:
                            requested_section += f"<li>Tek School Fee: ₹{payment_breakdown['tek_school_fee']:.2f} ({installment_type_display})</li>"
                        requested_section += "</ul>"
                        
                        email_body = f"""
                        <h2>Payment Request</h2>
                        <p>Dear {student.parent.parent_name},</p>
                        <p>This is a payment request for {student.first_name} {student.last_name} (Roll No: {student.roll_no}).</p>
                        <p><strong>Total Amount Due (Based on Installment Type): ₹{total_due:.2f}</strong></p>
                        <p>Remaining Balances (Calculated by Installment Type):</p>
                        <ul>
                            <li>Course Fee Remaining ({installment_type_value}): ₹{course_fee_pending:.2f}</li>
                            <li>Transport Fee Remaining ({installment_type_value}): ₹{transport_fee_pending:.2f}</li>
                            <li>Tek School Fee Remaining ({installment_type_value}): ₹{tek_school_fee_pending:.2f}</li>
                        </ul>
                        <p><small>Note: Amounts are calculated based on remaining time period from today ({date.today().isoformat()}) to class end date ({class_obj.class_end_date.isoformat() if class_obj.class_end_date else 'N/A'}) and installment type.</small></p>
                        {requested_section}
                        {f'<p>{message}</p>' if message else ''}
                        <p>Please fill the payment form in the student portal.</p>
                        <p>Thank you.</p>
                        """
                        # Create a simple email sending function
                        def send_email_sync():
                            import smtplib
                            from email.mime.multipart import MIMEMultipart
                            from email.mime.text import MIMEText
                            from app.core.config import settings
                            
                            msg = MIMEMultipart("alternative")
                            msg["Subject"] = email_subject
                            msg["From"] = f"{settings.MAIL_FROM_NAME} <{settings.MAIL_FROM}>"
                            msg["To"] = student.parent.email
                            msg.attach(MIMEText(email_body, "html"))
                            
                            with smtplib.SMTP(settings.MAIL_SERVER, settings.MAIL_PORT) as server:
                                server.starttls()
                                server.login(settings.MAIL_USERNAME, settings.MAIL_PASSWORD)
                                server.sendmail(settings.MAIL_FROM, student.parent.email, msg.as_string())
                        
                        await run_in_threadpool(send_email_sync)
                        return student.parent.email
                    except Exception as e:
                        print(f"Warning: Failed to send email reminder to {student.parent.email}: {str(e)}")
                        return None
                
                # Fire and forget email sending
                email_sent = await send_email()

            # Success
            student_result["success"] = True
            student_result["message"] = "Payment reminder sent successfully."
            student_result["transaction_id"] = transaction_id
            student_result["total_due"] = round(total_due, 2)
            student_result["installment_pending_amount"] = installment_pending_amount
            student_result["email_sent"] = email_sent
            return student_result

        except Exception as e:
            student_result["message"] = f"Error processing student: {str(e)}"
            return student_result

    try:
        # ✅ Determine school_id based on user role
        if current_user.role == UserRole.SCHOOL:
            school_id = current_user.school_profile.id
        elif current_user.role == UserRole.STAFF:
            staff = await run_in_threadpool(
                lambda: db.query(Staff).filter(Staff.user_id == current_user.id).first()
            )
            if not staff:
                raise HTTPException(status_code=404, detail="Staff profile not found.")
            school_id = staff.school_id
        else:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only schools and staff can send payment reminders."
            )

        # ✅ VALIDATION: Validate bank_account_id if provided
        bank_account = None
        if data.bank_account_id is not None:
            bank_account = await run_in_threadpool(
                lambda: db.query(BankAccount).filter(
                    BankAccount.id == data.bank_account_id,
                    BankAccount.school_id == school_id
                ).first()
            )
            
            if not bank_account:
                raise HTTPException(
                    status_code=404,
                    detail=f"Bank account with ID {data.bank_account_id} not found or does not belong to your school."
                )

        # ✅ VALIDATION: Remove duplicates from student_ids
        unique_student_ids = list(set(data.student_ids))
        if len(unique_student_ids) == 0:
            raise HTTPException(status_code=400, detail="At least one student ID is required.")

        # Get all students in one query (run in thread pool)
        def fetch_students():
            return (
                db.query(Student)
                .options(joinedload(Student.classes))
                .filter(
                    Student.id.in_(unique_student_ids),
                    Student.school_id == school_id
                )
                .all()
            )
        
        students = await run_in_threadpool(fetch_students)

        # Create mapping of student_id -> student
        student_map = {student.id: student for student in students}

        # Get all payment records for these students (run in thread pool)
        def fetch_payments():
            return (
                db.query(StudentPayment)
                .filter(
                    StudentPayment.student_id.in_(unique_student_ids)
                )
                .all()
            )
        
        payments = await run_in_threadpool(fetch_payments)

        # Create mapping of (student_id, class_id) -> payment
        payment_map = {}
        for payment in payments:
            key = (payment.student_id, payment.class_id)
            payment_map[key] = payment

        # Process all students concurrently
        tasks = [
            process_single_student(
                student_id=student_id,
                student_map=student_map,
                payment_map=payment_map,
                school_id=school_id,
                message=data.message,
                bank_account_id=data.bank_account_id,
                current_user_id=current_user.id
            )
            for student_id in unique_student_ids
        ]
        
        results = await asyncio.gather(*tasks)

        # Count successes and failures
        successful_count = sum(1 for r in results if r.get("success", False))
        failed_count = len(results) - successful_count

        return {
            "detail": f"Bulk payment reminders processed. Success: {successful_count}, Failed: {failed_count}",
            "total_students": len(unique_student_ids),
            "successful_count": successful_count,
            "failed_count": failed_count,
            "results": results
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send bulk payment reminders: {str(e)}")


@router.put(
    "/students/{student_id}/payments/{class_id}/transactions/{transaction_id}/",
    summary="Student update payment transaction",
    description="Student updates a payment transaction that was created by the school (status: 'school_request'). Updates the transaction with payment amounts, documents, and changes status to 'payment_update_by_student'."
)
def student_update_payment_transaction(
    student_id: int,
    class_id: int,
    transaction_id: int,
    data: StudentPaymentSubmit,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Student updates a payment transaction.
    Updates an existing payment request (status: school_request) with payment amounts and documents.
    Status automatically changes to "payment_update_by_student" after update.
    """
    try:
        # ✅ VALIDATION: student_id, class_id, and transaction_id must be positive
        if student_id <= 0:
            raise HTTPException(status_code=400, detail="Invalid student_id. Must be a positive integer.")
        if class_id <= 0:
            raise HTTPException(status_code=400, detail="Invalid class_id. Must be a positive integer.")
        if transaction_id <= 0:
            raise HTTPException(status_code=400, detail="Invalid transaction_id. Must be a positive integer.")

        # ✅ VALIDATION: Only STUDENT role can update payment transactions
        if current_user.role != UserRole.STUDENT:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only students can update payment transactions."
            )

        # ✅ VALIDATION: Verify student exists and belongs to current user
        student = db.query(Student).filter(
            Student.id == student_id,
            Student.user_id == current_user.id
        ).first()
        
        if not student:
            raise HTTPException(status_code=404, detail="Student not found or not authorized.")

        # ✅ VALIDATION: Verify class matches student's current class
        if student.class_id != class_id:
            raise HTTPException(
                status_code=400, 
                detail=f"Class ID does not match student's current class. Student is in class {student.class_id}."
            )

        # ✅ VALIDATION: Get payment record
        payment = db.query(StudentPayment).filter(
            StudentPayment.student_id == student_id,
            StudentPayment.class_id == class_id
        ).first()

        if not payment:
            raise HTTPException(
                status_code=404,
                detail=f"Payment record not found for student {student_id} in class {class_id}."
            )

        # ✅ VALIDATION: Find the specific transaction
        existing_transaction = db.query(StudentPaymentTransaction).filter(
            StudentPaymentTransaction.id == transaction_id,
            StudentPaymentTransaction.student_payment_id == payment.id
        ).first()
        
        if not existing_transaction:
            raise HTTPException(
                status_code=404,
                detail=f"Transaction {transaction_id} not found for this student and class."
            )
        
        # ✅ VALIDATION: Transaction must be in "school_request" status
        if existing_transaction.status != PaymentTransactionStatus.SCHOOL_REQUEST.value:
            raise HTTPException(
                status_code=400,
                detail=f"Transaction is not in 'school_request' status. Current status: {existing_transaction.status}. Only transactions with 'school_request' status can be updated by students."
            )

        # ✅ VALIDATION: At least one payment amount must be provided
        if not any([data.course_fee_amount, data.transport_fee_amount, data.tek_school_fee_amount]):
            raise HTTPException(
                status_code=400,
                detail="At least one payment amount must be provided (course_fee_amount, transport_fee_amount, or tek_school_fee_amount)"
            )

        # ✅ VALIDATION: All provided amounts must be positive
        if data.course_fee_amount is not None and data.course_fee_amount <= 0:
            raise HTTPException(status_code=400, detail="Course fee amount must be greater than 0.")
        if data.transport_fee_amount is not None and data.transport_fee_amount <= 0:
            raise HTTPException(status_code=400, detail="Transport fee amount must be greater than 0.")
        if data.tek_school_fee_amount is not None and data.tek_school_fee_amount <= 0:
            raise HTTPException(status_code=400, detail="Tek School fee amount must be greater than 0.")

        # ✅ VALIDATION: File count limit
        if data.files and len(data.files) > 10:
            raise HTTPException(status_code=400, detail="Maximum 10 files allowed per payment submission.")

        # Handle file uploads
        uploaded_file_urls = []
        if data.files:
            for file_base64 in data.files:
                try:
                    # ✅ VALIDATION: Check if file is base64 encoded
                    if not file_base64 or len(file_base64) < 100:
                        raise HTTPException(status_code=400, detail="Invalid file format. Files must be base64 encoded.")
                    
                    file_ext = "pdf"
                    if "," in file_base64:
                        if "image/png" in file_base64:
                            file_ext = "png"
                        elif "image/jpeg" in file_base64 or "image/jpg" in file_base64:
                            file_ext = "jpg"
                        elif "application/pdf" in file_base64:
                            file_ext = "pdf"
                    
                    file_url = upload_base64_to_s3(
                        base64_string=file_base64,
                        filename_prefix=f"student_payments/{student_id}/class_{class_id}/transactions",
                        ext=file_ext
                    )
                    uploaded_file_urls.append(file_url)
                except HTTPException:
                    raise
                except Exception as e:
                    print(f"Warning: Failed to upload file: {str(e)}")
                    raise HTTPException(status_code=400, detail=f"Failed to upload file: {str(e)}")

        # ✅ VALIDATION: Validate payment amounts don't exceed remaining balances
        payment_breakdown = {}
        total_amount = 0.0
        transaction_errors = []

        if data.course_fee_amount is not None and data.course_fee_amount > 0:
            remaining = round(payment.course_fee - payment.course_fee_paid, 2)
            if remaining <= 0:
                transaction_errors.append("Course fee is already fully paid.")
            elif data.course_fee_amount > remaining:
                transaction_errors.append(f"Course fee payment ({data.course_fee_amount}) exceeds remaining balance ({remaining:.2f}).")
            else:
                payment_breakdown["course_fee"] = round(data.course_fee_amount, 2)
                total_amount += data.course_fee_amount

        if data.transport_fee_amount is not None and data.transport_fee_amount > 0:
            remaining = round(payment.transport_fee - payment.transport_fee_paid, 2)
            if remaining <= 0:
                transaction_errors.append("Transport fee is already fully paid.")
            elif data.transport_fee_amount > remaining:
                transaction_errors.append(f"Transport fee payment ({data.transport_fee_amount}) exceeds remaining balance ({remaining:.2f}).")
            else:
                payment_breakdown["transport_fee"] = round(data.transport_fee_amount, 2)
                total_amount += data.transport_fee_amount

        if data.tek_school_fee_amount is not None and data.tek_school_fee_amount > 0:
            remaining = round(payment.tek_school_fee - payment.tek_school_fee_paid, 2)
            if remaining <= 0:
                transaction_errors.append("Tek School fee is already fully paid.")
            elif data.tek_school_fee_amount > remaining:
                transaction_errors.append(f"Tek School fee payment ({data.tek_school_fee_amount}) exceeds remaining balance ({remaining:.2f}).")
            else:
                payment_breakdown["tek_school_fee"] = round(data.tek_school_fee_amount, 2)
                total_amount += data.tek_school_fee_amount

        if transaction_errors:
            raise HTTPException(
                status_code=400,
                detail="; ".join(transaction_errors)
            )

        # ✅ VALIDATION: Total amount must be positive
        if total_amount <= 0:
            raise HTTPException(status_code=400, detail="Total payment amount must be greater than 0.")

        effective_payment_method = data.payment_method or existing_transaction.payment_method
        effective_bank_account_id = data.bank_account_id if data.bank_account_id is not None else existing_transaction.bank_account_id

        if effective_payment_method and effective_payment_method.strip().lower() not in ["cash", "cash_offline"]:
            if not effective_bank_account_id:
                raise HTTPException(
                    status_code=400,
                    detail="bank_account_id is required for bank payment methods."
                )

        submit_settlement_bank_id = resolve_student_fee_settlement_bank_account_id(
            effective_payment_method, effective_bank_account_id
        )
        if submit_settlement_bank_id is not None:
            ba = (
                db.query(BankAccount)
                .filter(
                    BankAccount.id == submit_settlement_bank_id,
                    BankAccount.school_id == student.school_id,
                )
                .first()
            )
            if not ba:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid bank_account_id for this school.",
                )

        # Determine primary payment type
        primary_payment_type = "course_fee"
        if data.transport_fee_amount and data.transport_fee_amount > 0:
            primary_payment_type = "transport_fee"
        if data.tek_school_fee_amount and data.tek_school_fee_amount > 0:
            primary_payment_type = "tek_school_fee"

        # Update existing transaction with student's payment details
        existing_transaction.amount = round(total_amount, 2)
        existing_transaction.payment_type = primary_payment_type
        existing_transaction.payment_breakdown = payment_breakdown if payment_breakdown else None
        existing_transaction.transaction_date = datetime.utcnow()
        existing_transaction.description = data.description if data.description else existing_transaction.description
        existing_transaction.files = uploaded_file_urls if uploaded_file_urls else existing_transaction.files
        existing_transaction.payment_method = data.payment_method if data.payment_method else existing_transaction.payment_method
        existing_transaction.transaction_reference = data.transaction_reference if data.transaction_reference else existing_transaction.transaction_reference
        existing_transaction.bank_account_id = submit_settlement_bank_id
        existing_transaction.status = PaymentTransactionStatus.PAYMENT_UPDATE_BY_STUDENT.value  # Status changed to payment_update_by_student

        db.commit()
        db.refresh(existing_transaction)

        return {
            "detail": "Payment transaction updated successfully. Status changed to 'payment_update_by_student'. Waiting for school verification.",
            "transaction_id": existing_transaction.id,
            "amount": float(existing_transaction.amount),
            "status": existing_transaction.status,
            "payment_breakdown": existing_transaction.payment_breakdown,
            "message": "Your payment has been updated. School will now verify and approve or reject the payment."
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to submit payment: {str(e)}")


@router.post(
    "/students/{student_id}/payments/{class_id}/submit-manual-payment/",
    summary="Student submit manual payment",
    description="Student submits manual payment details (amount, method, reference, proof). Creates a new transaction with status 'payment_update_by_student' for school verification."
)
def student_submit_manual_payment(
    student_id: int,
    class_id: int,
    data: StudentPaymentSubmit,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Student submits manual payment details.
    Creates a new payment transaction with status 'payment_update_by_student'.
    School will verify and approve or reject the payment.
    """
    try:
        # ✅ VALIDATION: student_id and class_id must be positive
        if student_id <= 0:
            raise HTTPException(status_code=400, detail="Invalid student_id. Must be a positive integer.")
        if class_id <= 0:
            raise HTTPException(status_code=400, detail="Invalid class_id. Must be a positive integer.")

        # ✅ VALIDATION: Only STUDENT role can submit manual payments
        if current_user.role != UserRole.STUDENT:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only students can submit manual payments."
            )

        # ✅ VALIDATION: Verify student exists and belongs to current user
        student = db.query(Student).filter(
            Student.id == student_id,
            Student.user_id == current_user.id
        ).first()
        
        if not student:
            raise HTTPException(status_code=404, detail="Student not found or not authorized.")

        # ✅ VALIDATION: Verify class matches student's current class
        if student.class_id != class_id:
            raise HTTPException(
                status_code=400, 
                detail=f"Class ID does not match student's current class. Student is in class {student.class_id}."
            )

        # ✅ VALIDATION: Get payment record
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
        if not any([
            data.course_fee_amount,
            data.transport_fee_amount,
            data.tek_school_fee_amount
        ]):
            raise HTTPException(
                status_code=400,
                detail="At least one payment amount must be provided (course_fee_amount, transport_fee_amount, or tek_school_fee_amount)."
            )

        # ✅ VALIDATION: Payment amounts must be positive if provided
        if data.course_fee_amount and data.course_fee_amount <= 0:
            raise HTTPException(status_code=400, detail="course_fee_amount must be greater than 0.")
        if data.transport_fee_amount and data.transport_fee_amount <= 0:
            raise HTTPException(status_code=400, detail="transport_fee_amount must be greater than 0.")
        if data.tek_school_fee_amount and data.tek_school_fee_amount <= 0:
            raise HTTPException(status_code=400, detail="tek_school_fee_amount must be greater than 0.")

        # ✅ VALIDATION: Bank account is required for bank payment methods
        if data.payment_method and data.payment_method.strip().lower() not in ["cash", "cash_offline"]:
            if not data.bank_account_id:
                raise HTTPException(
                    status_code=400,
                    detail="bank_account_id is required for bank payment methods."
                )

        # ✅ Calculate total amount
        total_amount = sum([
            data.course_fee_amount or 0,
            data.transport_fee_amount or 0,
            data.tek_school_fee_amount or 0
        ])

        # ✅ Create payment breakdown
        payment_breakdown = {}
        if data.course_fee_amount:
            payment_breakdown["course_fee"] = data.course_fee_amount
        if data.transport_fee_amount:
            payment_breakdown["transport_fee"] = data.transport_fee_amount
        if data.tek_school_fee_amount:
            payment_breakdown["tek_school_fee"] = data.tek_school_fee_amount

        # ✅ Upload files to S3 if provided
        uploaded_files = []
        if data.files:
            for file_data in data.files:
                try:
                    file_url = upload_base64_to_s3(file_data, f"payments/student_{student_id}")
                    uploaded_files.append(file_url)
                except Exception as e:
                    raise HTTPException(
                        status_code=500,
                        detail=f"Failed to upload payment proof file: {str(e)}"
                    )

        # ✅ Create the transaction
        new_transaction = StudentPaymentTransaction(
            student_payment_id=payment.id,
            amount=total_amount,
            payment_type="manual",  # Since it's manual submission
            payment_breakdown=payment_breakdown,
            transaction_date=datetime.utcnow(),
            description=data.description,
            files=uploaded_files if uploaded_files else None,
            payment_method=data.payment_method,
            transaction_reference=data.transaction_reference,
            bank_account_id=data.bank_account_id,
            status=PaymentTransactionStatus.PAYMENT_UPDATE_BY_STUDENT.value,
            created_by=current_user.id
        )

        db.add(new_transaction)
        db.commit()
        db.refresh(new_transaction)

        return {
            "detail": "Manual payment submitted successfully. Waiting for school verification.",
            "transaction_id": new_transaction.id,
            "amount": float(new_transaction.amount),
            "status": new_transaction.status,
            "payment_breakdown": new_transaction.payment_breakdown,
            "message": "Your payment details have been submitted. School will verify and approve or reject the payment."
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to submit manual payment: {str(e)}")


@router.put(
    "/students/{student_id}/payments/{class_id}/transactions/{transaction_id}/verify/",
    summary="Verify payment transaction",
    description="School verifies a payment transaction. If status is 'done', calculates and deducts payment amounts. If status is 'cancel', cancels the request with a rejection reason."
)
def verify_payment_transaction(
    student_id: int,
    class_id: int,
    transaction_id: int,
    data: PaymentVerificationRequest,
    db: Session = Depends(get_db),
    current_user = Depends(require_roles(UserRole.SCHOOL, UserRole.STAFF))
):
    """
    School verifies or rejects a payment transaction submitted by student.
    If verified, amounts are calculated and updated automatically using database transaction.
    """
    try:
        # ✅ VALIDATION: All IDs must be positive
        if student_id <= 0:
            raise HTTPException(status_code=400, detail="Invalid student_id. Must be a positive integer.")
        if class_id <= 0:
            raise HTTPException(status_code=400, detail="Invalid class_id. Must be a positive integer.")
        if transaction_id <= 0:
            raise HTTPException(status_code=400, detail="Invalid transaction_id. Must be a positive integer.")

        # ✅ VALIDATION: Status must be "done" or "cancel"
        if data.status not in ["done", "cancel"]:
            raise HTTPException(
                status_code=400,
                detail="Status must be either 'done' (to verify and calculate amounts) or 'cancel' (to cancel the request)."
            )

        # ✅ VALIDATION: Rejection reason required if cancelled
        if data.status == "cancel" and not data.rejection_reason:
            raise HTTPException(
                status_code=400,
                detail="Rejection reason is required when cancelling a payment request."
            )

        # ✅ VALIDATION: Rejection reason length
        if data.status == "cancel" and data.rejection_reason and len(data.rejection_reason) > 500:
            raise HTTPException(
                status_code=400,
                detail="Rejection reason cannot exceed 500 characters."
            )

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
                detail="Only schools and staff can verify payments."
            )

        # ✅ VALIDATION: Verify student belongs to the school
        student = db.query(Student).filter(
            Student.id == student_id,
            Student.school_id == school_id
        ).first()
        
        if not student:
            raise HTTPException(status_code=404, detail="Student not found or not part of your school.")

        # ✅ VALIDATION: Verify class exists and belongs to school
        class_obj = db.query(Class).filter(
            Class.id == class_id,
            Class.school_id == school_id
        ).first()
        
        if not class_obj:
            raise HTTPException(status_code=404, detail="Class not found or does not belong to your school.")

        # ✅ VALIDATION: Get payment record
        payment = db.query(StudentPayment).filter(
            StudentPayment.student_id == student_id,
            StudentPayment.class_id == class_id
        ).first()

        if not payment:
            raise HTTPException(
                status_code=404,
                detail=f"Payment record not found for student {student_id} in class {class_id}."
            )

        # ✅ VALIDATION: Get transaction with lock to prevent concurrent updates
        transaction = db.query(StudentPaymentTransaction).filter(
            StudentPaymentTransaction.id == transaction_id,
            StudentPaymentTransaction.student_payment_id == payment.id
        ).first()

        if not transaction:
            raise HTTPException(
                status_code=404,
                detail="Transaction not found or does not belong to this payment."
            )

        # ✅ VALIDATION: Check if already done or cancelled
        if transaction.status == PaymentTransactionStatus.DONE.value:
            raise HTTPException(
                status_code=400,
                detail="This payment request has already been completed."
            )
        
        if transaction.status == PaymentTransactionStatus.CANCEL.value:
            raise HTTPException(
                status_code=400,
                detail="This payment request has already been cancelled."
            )

        # ✅ VALIDATION: Transaction must be in "payment_update_by_student" status
        if transaction.status != PaymentTransactionStatus.PAYMENT_UPDATE_BY_STUDENT.value:
            raise HTTPException(
                status_code=400,
                detail=f"Transaction is not ready for verification. Current status: {transaction.status}. Expected: payment_update_by_student"
            )

        # ✅ Start database transaction for atomic update
        try:
            # Update transaction status
            if data.status == "done":
                transaction.status = PaymentTransactionStatus.DONE.value
                transaction.verified_at = datetime.utcnow()
                transaction.verified_by = current_user.id
                transaction.rejection_reason = None

                # Update student status to ACTIVE and set expiry date
                validity_days = 90  # default
                if payment and payment.installment_type:
                    inst_type = payment.installment_type.lower()
                    if inst_type == "monthly":
                        validity_days = 30
                    elif inst_type == "quarterly":
                        validity_days = 90
                    elif inst_type == "half_yearly":
                        validity_days = 180
                    elif inst_type == "yearly":
                        validity_days = 365

                now = datetime.utcnow()
                student.status = StudentStatus.ACTIVE
                if student.status_expiry_date and student.status_expiry_date > now:
                    student.status_expiry_date = student.status_expiry_date + timedelta(days=validity_days)
                else:
                    student.status_expiry_date = now + timedelta(days=validity_days)

                # ✅ Calculate and update payment amounts (ATOMIC OPERATION)
                old_course_fee_paid = payment.course_fee_paid
                old_transport_fee_paid = payment.transport_fee_paid
                old_tek_school_fee_paid = payment.tek_school_fee_paid

                applied_course_fee_amount = 0.0
                applied_transport_fee_amount = 0.0
                applied_tek_school_fee_amount = 0.0
                overpayment_amount = 0.0

                if transaction.payment_breakdown:
                    # Update based on payment breakdown
                    course_fee_amount = float(transaction.payment_breakdown.get("course_fee", 0))
                    transport_fee_amount = float(transaction.payment_breakdown.get("transport_fee", 0))
                    tek_school_fee_amount = float(transaction.payment_breakdown.get("tek_school_fee", 0))

                    # ✅ Apply each amount up to the remaining fee balance
                    if course_fee_amount > 0:
                        remaining = round(payment.course_fee - payment.course_fee_paid, 2)
                        applied_course_fee_amount = min(course_fee_amount, max(remaining, 0.0))
                        payment.course_fee_paid = round(payment.course_fee_paid + applied_course_fee_amount, 2)
                        overpayment_amount += max(course_fee_amount - applied_course_fee_amount, 0.0)

                    if transport_fee_amount > 0:
                        remaining = round(payment.transport_fee - payment.transport_fee_paid, 2)
                        applied_transport_fee_amount = min(transport_fee_amount, max(remaining, 0.0))
                        payment.transport_fee_paid = round(payment.transport_fee_paid + applied_transport_fee_amount, 2)
                        overpayment_amount += max(transport_fee_amount - applied_transport_fee_amount, 0.0)

                    if tek_school_fee_amount > 0:
                        remaining = round(payment.tek_school_fee - payment.tek_school_fee_paid, 2)
                        applied_tek_school_fee_amount = min(tek_school_fee_amount, max(remaining, 0.0))
                        payment.tek_school_fee_paid = round(payment.tek_school_fee_paid + applied_tek_school_fee_amount, 2)
                        overpayment_amount += max(tek_school_fee_amount - applied_tek_school_fee_amount, 0.0)
                else:
                    # Fallback: update based on primary payment type
                    if transaction.payment_type == "course_fee":
                        remaining = round(payment.course_fee - payment.course_fee_paid, 2)
                        if transaction.amount > remaining:
                            raise HTTPException(
                                status_code=400,
                                detail=f"Cannot verify: Course fee amount ({transaction.amount}) exceeds remaining balance ({remaining:.2f})."
                            )
                        payment.course_fee_paid = round(payment.course_fee_paid + transaction.amount, 2)
                    elif transaction.payment_type == "transport_fee":
                        remaining = round(payment.transport_fee - payment.transport_fee_paid, 2)
                        if transaction.amount > remaining:
                            raise HTTPException(
                                status_code=400,
                                detail=f"Cannot verify: Transport fee amount ({transaction.amount}) exceeds remaining balance ({remaining:.2f})."
                            )
                        payment.transport_fee_paid = round(payment.transport_fee_paid + transaction.amount, 2)
                    elif transaction.payment_type == "tek_school_fee":
                        remaining = round(payment.tek_school_fee - payment.tek_school_fee_paid, 2)
                        if transaction.amount > remaining:
                            raise HTTPException(
                                status_code=400,
                                detail=f"Cannot verify: Tek School fee amount ({transaction.amount}) exceeds remaining balance ({remaining:.2f})."
                            )
                        payment.tek_school_fee_paid = round(payment.tek_school_fee_paid + transaction.amount, 2)

                # ✅ VALIDATION: Ensure paid amounts don't exceed fee amounts (safety check)
                payment.course_fee_paid = min(round(payment.course_fee_paid, 2), round(payment.course_fee, 2))
                payment.transport_fee_paid = min(round(payment.transport_fee_paid, 2), round(payment.transport_fee, 2))
                payment.tek_school_fee_paid = min(round(payment.tek_school_fee_paid, 2), round(payment.tek_school_fee, 2))

                # ✅ VALIDATION: Ensure paid amounts are not negative
                if payment.course_fee_paid < 0:
                    payment.course_fee_paid = 0
                if payment.transport_fee_paid < 0:
                    payment.transport_fee_paid = 0
                if payment.tek_school_fee_paid < 0:
                    payment.tek_school_fee_paid = 0

                credited_amount = 0.0
                if transaction.payment_breakdown:
                    credited_amount += float(
                        transaction.payment_breakdown.get("course_fee", 0) or 0
                    )
                    credited_amount += float(
                        transaction.payment_breakdown.get("transport_fee", 0) or 0
                    )
                    credited_amount += float(
                        transaction.payment_breakdown.get("tek_school_fee", 0) or 0
                    )
                else:
                    credited_amount = float(transaction.amount or 0)
                
                if credited_amount > 0:
                    if transaction.payment_method and transaction.payment_method.strip().lower() not in ["cash", "cash_offline"]:
                        if not transaction.bank_account_id:
                            raise HTTPException(
                                status_code=400,
                                detail="Bank account is required for bank payment methods when verifying a student payment."
                            )

                    verify_settlement_bank_id = (
                        resolve_student_fee_settlement_bank_account_id(
                            transaction.payment_method, transaction.bank_account_id
                        )
                    )
                    record_student_fee_credit(
                        db,
                        school_id=school_id,
                        bank_account_id=verify_settlement_bank_id,
                        credited_amount=credited_amount,
                        source_reference=f"student_payment_transaction:{transaction.id}",
                        description=(
                            f"Student fee approved student_id={student_id} class_id={class_id} "
                            f"txn={transaction.id}"
                        ),
                        recorded_by_user_id=current_user.id,
                    )

            else:  # cancel
                transaction.status = PaymentTransactionStatus.CANCEL.value
                transaction.rejection_reason = data.rejection_reason
                transaction.verified_at = datetime.utcnow()
                transaction.verified_by = current_user.id

            # ✅ Commit transaction atomically
            db.commit()
            db.refresh(transaction)
            db.refresh(payment)

            return {
                "detail": f"Payment request {data.status} successfully." + (" Amounts have been calculated and updated." if data.status == "done" else ""),
                "transaction_id": transaction.id,
                "status": transaction.status,
                "verified_at": transaction.verified_at.isoformat() if transaction.verified_at else None,
                "verified_by": current_user.id,
                "payment_summary": {
                    "course_fee_paid": float(payment.course_fee_paid),
                    "transport_fee_paid": float(payment.transport_fee_paid),
                    "tek_school_fee_paid": float(payment.tek_school_fee_paid),
                    "total_paid": round(
                        payment.course_fee_paid + payment.transport_fee_paid + payment.tek_school_fee_paid, 2
                    )
                } if data.status == "done" else None
            }

        except HTTPException:
            db.rollback()
            raise
        except Exception as e:
            db.rollback()
            raise HTTPException(
                status_code=500,
                detail=f"Failed to verify payment transaction: {str(e)}"
            )

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to verify payment: {str(e)}")

@router.post("/doubt/create")
def create_doubt(
    payload: CreateDoubtRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    student = db.query(Student).filter(Student.user_id == current_user.id).first()

    if not student:
        raise HTTPException(404, "Student not found")

    # ✅ max 5 teachers
    if len(payload.teacher_ids) > 5:
        raise HTTPException(400, "Max 5 teachers allowed")

    # ✅ remove duplicates
    teacher_ids = list(set(payload.teacher_ids))

    # ✅ validate teachers in same school
    teachers = db.query(Teacher).filter(
        Teacher.id.in_(teacher_ids),
        Teacher.school_id == student.school_id
    ).all()

    if len(teachers) != len(teacher_ids):
        raise HTTPException(400, "Invalid teachers selected")

    # ✅ create doubt
    doubt = Doubt(
        student_id=student.id,
        school_id=student.school_id,
        subject_id=payload.subject_id,
        class_id=student.class_id,
        section_id=student.section_id,
        chapter_name=payload.chapter_name,
        question=payload.question,
        key_points=payload.key_points,
        attachment=payload.attachment
    )

    db.add(doubt)
    db.flush()

    # ✅ assign teachers
    for teacher_id in teacher_ids:
        db.add(DoubtTeacher(doubt_id=doubt.id, teacher_id=teacher_id))

    db.commit()

    return {"message": "Doubt created"}

@router.get("/doubt/dashboard")
def student_dashboard(db: Session = Depends(get_db), current_user=Depends(get_current_user)):

    student = db.query(Student).filter(Student.user_id == current_user.id).first()

    if not student:
        raise HTTPException(404, "Student not found")

    total = db.query(func.count(Doubt.id)).filter(
        Doubt.student_id == student.id
    ).scalar()

    solved = db.query(func.count(Doubt.id)).filter(
        Doubt.student_id == student.id,
        Doubt.status == DoubtStatus.SOLVED
    ).scalar()

    pending = db.query(func.count(Doubt.id)).filter(
        Doubt.student_id == student.id,
        Doubt.status == DoubtStatus.PENDING
    ).scalar()

    return {
        "total": total,
        "solved": solved,
        "pending": pending,
        "unsolved": total - solved
    }
        
@router.get("/teacher/doubt/dashboard")
def teacher_dashboard(db: Session = Depends(get_db), current_user=Depends(get_current_user)):

    teacher = db.query(Teacher).filter(Teacher.user_id == current_user.id).first()

    if not teacher:
        raise HTTPException(404, "Teacher not found")

    total = db.query(func.count(DoubtTeacher.id)).filter(
        DoubtTeacher.teacher_id == teacher.id
    ).scalar()

    responded = db.query(func.count(DoubtResponse.id)).filter(
        DoubtResponse.teacher_id == teacher.id
    ).scalar()

    solved = db.query(func.count(DoubtResponse.id)).filter(
        DoubtResponse.teacher_id == teacher.id,
        DoubtResponse.action == ResponseAction.SOLVE
    ).scalar()

    return {
        "total_doubts": total,
        "responded": responded,
        "solved": solved,
        "solved_ratio": round((solved / total * 100), 2) if total else 0
    }

@router.post("/doubt/respond/{doubt_id}")
def respond_doubt(
    doubt_id: int,
    payload: RespondDoubtRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    teacher = db.query(Teacher).filter(
        Teacher.user_id == current_user.id
    ).first()

    if not teacher:
        raise HTTPException(404, "Teacher not found")

    doubt = db.query(Doubt).filter(Doubt.id == doubt_id).first()

    if not doubt:
        raise HTTPException(404, "Doubt not found")

    # ❗ Only one teacher can respond
    existing_response = db.query(DoubtResponse).filter(
        DoubtResponse.doubt_id == doubt_id
    ).first()

    if existing_response:
        raise HTTPException(400, "Already handled")

    # check assignment
    assigned = db.query(DoubtTeacher).filter(
        DoubtTeacher.doubt_id == doubt_id,
        DoubtTeacher.teacher_id == teacher.id
    ).first()

    if not assigned:
        raise HTTPException(403, "Not assigned")

    # create response
    response = DoubtResponse(
        doubt_id=doubt_id,
        teacher_id=teacher.id,
        answer=payload.answer,
        attachment=payload.attachment,
        action=payload.action
    )

    db.add(response)

    # update current teacher
    assigned.status = TeacherDoubtStatus.RESPONDED

    # lock others
    db.query(DoubtTeacher).filter(
        DoubtTeacher.doubt_id == doubt_id,
        DoubtTeacher.teacher_id != teacher.id
    ).update({"status": TeacherDoubtStatus.RESPONDED})

    # update doubt status
    doubt.status = DoubtStatus.SOLVED

    db.commit()

    return {"message": "Response submitted successfully"}

@router.get("/student/doubts", response_model=list[StudentDoubtListResponse])
def get_student_doubts(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    # ✅ Get student
    student = db.query(Student).filter(Student.user_id == current_user.id).first()

    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    # ✅ Fetch doubts with relations
    doubts = (
        db.query(Doubt)
        .options(
            joinedload(Doubt.subject),
            joinedload(Doubt.teachers).joinedload(DoubtTeacher.teacher)
        )
        .filter(Doubt.student_id == student.id)
        .order_by(Doubt.created_at.desc())
        .all()
    )

    # ✅ Format response
    result = []
    for doubt in doubts:
        teacher_list = [
            {
                "teacher_id": t.teacher.id,
                "teacher_name": f"{t.teacher.first_name} {t.teacher.last_name}"
            }
            for t in doubt.teachers
        ]

        result.append({
            "id": doubt.id,
            "subject": doubt.subject.name if doubt.subject else None,
            "chapter_name": doubt.chapter_name,
            "question": doubt.question,
            "teachers": teacher_list,
            "status": doubt.status,
            "created_at": doubt.created_at
        })

    return result

@router.get("/student/doubt/{doubt_id}")
def get_doubt_detail(
    doubt_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    # get student
    student = db.query(Student).filter(
        Student.user_id == current_user.id
    ).first()

    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    # get doubt
    doubt = db.query(Doubt).filter(
        Doubt.id == doubt_id,
        Doubt.student_id == student.id
    ).first()

    if not doubt:
        raise HTTPException(status_code=404, detail="Doubt not found")

    # assigned teachers
    assigned_teachers = (
        db.query(
            Teacher.id,
            Teacher.first_name,
            Teacher.last_name,
            DoubtTeacher.status
        )
        .join(DoubtTeacher, DoubtTeacher.teacher_id == Teacher.id)
        .filter(DoubtTeacher.doubt_id == doubt.id)
        .all()
    )

    # response (only one teacher can respond)
    response = (
        db.query(DoubtResponse, Teacher)
        .join(Teacher, Teacher.id == DoubtResponse.teacher_id)
        .filter(DoubtResponse.doubt_id == doubt.id)
        .first()
    )

    response_data = None
    if response:
        doubt_response, teacher = response

        response_data = {
            "teacher_id": teacher.id,
            "teacher_name": f"{teacher.first_name} {teacher.last_name}",
            "answer": doubt_response.answer,
            "attachment": doubt_response.attachment,
            "action": doubt_response.action.value,
            "responded_at": doubt_response.created_at,
        }

    return {
        "id": doubt.id,
        "subject": doubt.subject.name if doubt.subject else None,
        "chapter_name": doubt.chapter_name,
        "question": doubt.question,
        "key_points": doubt.key_points,
        "attachment": doubt.attachment,
        "status": doubt.status.value,
        "created_at": doubt.created_at,

        "assigned_teachers": [
            {
                "teacher_id": t.id,
                "teacher_name": f"{t.first_name} {t.last_name}",
                "status": t.status.value
            }
            for t in assigned_teachers
        ],

        "response": response_data
    }

@router.get("/teacher/doubts")
def get_teacher_doubts(
    pagination: PaginationParams = Depends(),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    # ✅ get teacher
    teacher = db.query(Teacher).filter(
        Teacher.user_id == current_user.id
    ).first()

    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher not found")

    # ✅ subquery → total doubts per student
    student_doubt_count = (
        db.query(
            Doubt.student_id,
            func.count(Doubt.id).label("total_doubts")
        )
        .group_by(Doubt.student_id)
        .subquery()
    )

    # ✅ subquery → latest response per doubt
    latest_response_subq = (
        db.query(
            DoubtResponse.doubt_id,
            func.max(DoubtResponse.created_at).label("latest_time")
        )
        .group_by(DoubtResponse.doubt_id)
        .subquery()
    )

    latest_response = (
        db.query(DoubtResponse)
        .join(
            latest_response_subq,
            (DoubtResponse.doubt_id == latest_response_subq.c.doubt_id) &
            (DoubtResponse.created_at == latest_response_subq.c.latest_time)
        )
        .subquery()
    )

    # ✅ main query
    query = (
        db.query(
            Doubt,
            Student,
            Class,
            Section,
            student_doubt_count.c.total_doubts,
            latest_response.c.answer.label("last_answer"),
            latest_response.c.action.label("last_action"),
            latest_response.c.created_at.label("last_response_date"),
        )
        .join(DoubtTeacher, DoubtTeacher.doubt_id == Doubt.id)
        .join(Student, Student.id == Doubt.student_id)
        .join(Class, Class.id == Doubt.class_id)
        .join(Section, Section.id == Doubt.section_id)
        .outerjoin(student_doubt_count, student_doubt_count.c.student_id == Student.id)
        .outerjoin(latest_response, latest_response.c.doubt_id == Doubt.id)
        .filter(DoubtTeacher.teacher_id == teacher.id)
        .order_by(Doubt.created_at.desc())
    )

    total_count = query.count()

    results = query.offset(pagination.offset()).limit(pagination.limit()).all()

    data = []
    for index, (
        doubt,
        student,
        class_,
        section,
        total_doubts,
        last_answer,
        last_action,
        last_response_date 
    ) in enumerate(results):

        data.append({
            "sl_no": index + 1 + pagination.offset(),

            "doubt_id": doubt.id,

            "student_name": f"{student.first_name} {student.last_name}",
            "roll_no": student.roll_no,

            "class_name": class_.name if class_ else None,
            "section_name": section.name if section else None,

            "total_requests_by_student": total_doubts or 0,

            "chapter_name": doubt.chapter_name,
            "question": doubt.question,

            "last_response": {
                "answer": last_answer,
                "action": last_action.value if last_action else None,
                "date": last_response_date.isoformat() if last_response_date else None
            } if last_answer else None,

            "status": doubt.status.value,
            "created_at": doubt.created_at
        })

    return pagination.format_response(data, total_count)