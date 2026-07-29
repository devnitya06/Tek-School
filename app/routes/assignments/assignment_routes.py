import json
from datetime import datetime, timedelta
from typing import Dict, List

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models.admin import SchoolClassSubject
from app.models.assignments.assignment import (
    Assignment,
    AssignmentDoubt,
    AssignmentImage,
    AssignmentKeyPoint,
    AssignmentPDF,
    AssignmentQuestion,
    AssignmentReport,
    AssignmentStatus,
    AssignmentVideoLink,
    ChapterFeedback,
    DoubtReply,
    DoubtStatus,
    FavoriteTeacher,
    PublishConfiguration,
    StudentAssignmentAttempt,
    StudentAssignmentProgress,
    TeacherRating,
)
from app.models.school import Class, Subject, class_subjects
from app.models.students import SelfSignedStudent, Student
from app.models.teachers import (
    SelfSignedTeacher,
    SelfSignedTeacherTeachingConfiguration,
    Teacher,
    TeacherClassSectionSubject,
)
from app.models.users import User
from app.schemas.assignments.assignment import (
    AssignmentCreate,
    AssignmentDoubtCreate,
    AssignmentDoubtResponse,
    AssignmentFileCreate,
    AssignmentFileResponse,
    AssignmentFileUploadPayload,
    AssignmentFileUsageSummary,
    AssignmentPatchBody,
    AssignmentQuestionBatchCreate,
    AssignmentQuestionPatch,
    AssignmentQuestionResponse,
    AssignmentReportCreate,
    AssignmentReportResponse,
    AssignmentResponse,
    AssignmentUpdate,
    ChapterFeedbackCreate,
    DoubtReplyCreate,
    DoubtReplyResponse,
    FavoriteTeacherCreate,
    FavoriteTeacherListResponse,
    FavoriteTeacherResponse,
    PublishConfigurationCreate,
    PublishConfigurationResponse,
    StudentAssignmentAttemptCreate,
    StudentAssignmentAttemptResponse,
    TeacherProfileResponse,
    TeacherRatingCreate,
)
from app.schemas.users import UserRole
from app.utils.s3 import upload_multipart_file_to_s3

router = APIRouter()


def _get_teacher_for_user(db: Session, user: User):
    if user.role == UserRole.TEACHER:
        return db.query(Teacher).filter(Teacher.user_id == user.id).first()
    if user.role == UserRole.SELF_SIGNED_TEACHER:
        return db.query(SelfSignedTeacher).filter(SelfSignedTeacher.user_id == user.id).first()
    return None


def _get_student_for_user(db: Session, user: User):
    if user.role == UserRole.STUDENT:
        return db.query(Student).filter(Student.user_id == user.id).first()
    if user.role == UserRole.SELF_SIGNED_STUDENT:
        return db.query(SelfSignedStudent).filter(SelfSignedStudent.user_id == user.id).first()
    return None


def _build_self_signed_teacher_school_info(teacher_obj: SelfSignedTeacher) -> dict:
    school_name = teacher_obj.institution_name or None
    address_parts = [
        teacher_obj.landmark,
        teacher_obj.division,
        teacher_obj.district,
        teacher_obj.state,
        teacher_obj.institution_pin_code,
    ]
    school_address = ", ".join(filter(None, [part.strip() for part in address_parts if part])) if any(address_parts) else None
    return {
        "school_name": school_name,
        "school_address": school_address,
    }


def _resolve_teacher_profile_by_id(db: Session, teacher_id: str):
    teacher_obj = db.query(Teacher).filter(Teacher.id == teacher_id).first()
    if teacher_obj:
        return teacher_obj, "teacher"

    if teacher_id.isdigit():
        self_signed_teacher = db.query(SelfSignedTeacher).filter(SelfSignedTeacher.id == int(teacher_id)).first()
        if self_signed_teacher:
            return self_signed_teacher, "self_signed_teacher"

    return None, None


def _get_teacher_display_name(db: Session, teacher_id: str, teacher_type: str) -> str | None:
    if teacher_type == "teacher":
        teacher_obj = db.query(Teacher).filter(Teacher.id == teacher_id).first()
        if teacher_obj:
            return f"{teacher_obj.first_name} {teacher_obj.last_name}".strip()
    elif teacher_type == "self_signed_teacher" and teacher_id.isdigit():
        teacher_obj = db.query(SelfSignedTeacher).filter(SelfSignedTeacher.id == int(teacher_id)).first()
        if teacher_obj:
            return f"{teacher_obj.first_name} {teacher_obj.last_name}".strip()
    return None


def _get_favorite_teacher_count(db: Session, teacher_id: str, teacher_type: str) -> int:
    return (
        db.query(func.count(FavoriteTeacher.id))
        .filter(FavoriteTeacher.teacher_id == str(teacher_id))
        .filter(FavoriteTeacher.teacher_type == teacher_type)
        .scalar()
        or 0
    )


def _get_student_display_name(db: Session, doubt: AssignmentDoubt) -> str | None:
    if doubt.student_user_id is not None:
        student = db.query(Student).filter(Student.user_id == doubt.student_user_id).first()
        if student:
            full_name = " ".join(filter(None, [getattr(student, "first_name", None), getattr(student, "last_name", None)])).strip()
            if full_name:
                return full_name

        user = db.query(User).filter(User.id == doubt.student_user_id).first()
        if user:
            full_name = " ".join(filter(None, [getattr(user, "name", None)])).strip()
            return full_name or getattr(user, "email", None) or getattr(user, "username", None)

    if doubt.self_signed_student_id is not None:
        student = db.query(SelfSignedStudent).filter(SelfSignedStudent.id == doubt.self_signed_student_id).first()
        if student:
            full_name = " ".join(filter(None, [getattr(student, "first_name", None), getattr(student, "last_name", None)])).strip()
            return full_name or getattr(student, "email", None)

    return None


def _resolve_class_subject_ids(
    db: Session,
    class_name: str | None,
    subject_name: str | None,
    board_name: str | None = None,
    school_id: str | None = None,
) -> tuple[int | None, int | None]:
    class_id = None
    subject_id = None

    normalized_class = (class_name or "").strip().lower()
    normalized_subject = (subject_name or "").strip().lower()

    # Prefer the canonical school class table for `class_id`.
    if normalized_class and school_id:
        class_row = (
            db.query(Class)
            .filter(
                func.lower(func.coalesce(Class.name, "")) == normalized_class,
                Class.school_id == school_id,
            )
            .order_by(Class.id)
            .first()
        )
        if class_row:
            class_id = class_row.id

    if normalized_subject:
        if class_id is not None and school_id:
            subject_row = (
                db.query(Subject)
                .join(class_subjects, class_subjects.c.subject_id == Subject.id)
                .filter(
                    func.lower(func.coalesce(Subject.name, "")) == normalized_subject,
                    class_subjects.c.class_id == class_id,
                    class_subjects.c.school_id == school_id,
                )
                .order_by(Subject.id)
                .first()
            )
            if subject_row:
                subject_id = subject_row.id

        if subject_id is None and school_id:
            subject_row = (
                db.query(Subject)
                .filter(
                    func.lower(func.coalesce(Subject.name, "")) == normalized_subject,
                    Subject.school_id == school_id,
                )
                .order_by(Subject.id)
                .first()
            )
            if subject_row:
                subject_id = subject_row.id

    return class_id, subject_id


def _build_profile_scope_response(
    db: Session,
    class_names_by_board: Dict[str, set],
    subject_names_by_class: Dict[str, set],
    school_id: str | None = None,
) -> Dict[str, List[Dict[str, object]]]:
    data = []
    for board_name, class_names in class_names_by_board.items():
        for class_name in sorted(class_names or set()):
            class_id, _ = _resolve_class_subject_ids(db, class_name, None, board_name, school_id=school_id)
            seen_subject_keys = set()
            subjects = []
            for subject_name in sorted(subject_names_by_class.get(class_name, set()) or set()):
                normalized_subject_key = (subject_name or "").strip().lower()
                if normalized_subject_key in seen_subject_keys:
                    continue
                seen_subject_keys.add(normalized_subject_key)
                _, subject_id = _resolve_class_subject_ids(db, class_name, subject_name, board_name, school_id=school_id)
                subjects.append({
                    "subject_name": subject_name,
                    "subject_id": subject_id,
                    "total_assignments": 0,
                })
            data.append({
                "board_name": board_name,
                "class_name": class_name,
                "class_id": class_id,
                "subjects": subjects,
            })
    return {"data": data}


def _calculate_attempt_percentage(assignment: Assignment, attempt: StudentAssignmentAttempt | None) -> float | None:
    if not assignment or not attempt:
        return None

    try:
        submitted = json.loads(attempt.submitted_answers) if attempt.submitted_answers else {}
    except Exception:
        submitted = {}

    q_by_id = {q.id: q.correct_option for q in assignment.questions} if assignment.questions else {}
    q_by_number = {q.question_number: q.correct_option for q in assignment.questions} if assignment.questions else {}

    correct = 0
    incorrect = 0
    for key, ans in (submitted or {}).items():
        matched = False

        try:
            ik = int(key)
        except Exception:
            ik = None

        if ik is not None and ik in q_by_id:
            matched = True
            if str(ans).strip().upper() == str(q_by_id[ik]).strip().upper():
                correct += 1
            else:
                incorrect += 1

        if not matched:
            try:
                num = int(''.join(filter(str.isdigit, str(key)))) if any(c.isdigit() for c in str(key)) else None
            except Exception:
                num = None
            if num is not None and num in q_by_number:
                if str(ans).strip().upper() == str(q_by_number[num]).strip().upper():
                    correct += 1
                else:
                    incorrect += 1

    total_questions = len(assignment.questions) if assignment.questions else max(correct + incorrect, 0)
    return round((correct / total_questions) * 100, 2) if total_questions > 0 else 0.0


def _serialize_doubt_response(db: Session, doubt: AssignmentDoubt) -> AssignmentDoubtResponse:
    messages = []
    if doubt.student_user_id is not None:
        initial_sender_type = "student"
    elif doubt.self_signed_student_id is not None:
        initial_sender_type = "self_signed_student"
    else:
        initial_sender_type = "student"

    messages.append({
        "sender_type": initial_sender_type,
        "message": doubt.doubt_text,
        "created_at": doubt.created_at,
    })

    for reply in sorted(doubt.replies, key=lambda r: r.created_at or datetime.min):
        reply_sender_type = getattr(reply, "sender_type", None) or "student"
        messages.append({
            "sender_type": reply_sender_type,
            "message": reply.reply_text,
            "created_at": reply.created_at,
        })

    assignment = db.query(Assignment).filter(Assignment.id == doubt.assignment_id).first()
    student_id = doubt.student_user_id
    if student_id is None and doubt.self_signed_student_id is not None:
        student_id = doubt.self_signed_student_id

    attempts = (
        db.query(StudentAssignmentAttempt)
        .filter(StudentAssignmentAttempt.assignment_id == doubt.assignment_id)
        .filter(StudentAssignmentAttempt.student_user_id == student_id)
        .order_by(StudentAssignmentAttempt.submission_date.desc())
        .all()
    ) if student_id is not None else []

    latest_attempt = attempts[0] if attempts else None
    result = _calculate_attempt_percentage(assignment, latest_attempt) if assignment and latest_attempt else None

    return AssignmentDoubtResponse(
        id=doubt.id,
        assignment_id=doubt.assignment_id,
        student_user_id=doubt.student_user_id,
        self_signed_student_id=doubt.self_signed_student_id,
        student_name=_get_student_display_name(db, doubt),
        status=doubt.status,
        created_at=doubt.created_at,
        resolved_at=doubt.resolved_at,
        number_of_attempts=len(attempts),
        last_attempt_date=latest_attempt.submission_date if latest_attempt else None,
        result=result,
        replies=messages,
    )


def _get_existing_student_doubt(
    db: Session,
    assignment_id: int,
    student_user_id: int | None = None,
    self_signed_student_id: int | None = None,
) -> AssignmentDoubt | None:
    query = db.query(AssignmentDoubt).filter(AssignmentDoubt.assignment_id == assignment_id)

    if student_user_id is not None:
        query = query.filter(AssignmentDoubt.student_user_id == student_user_id)
    elif self_signed_student_id is not None:
        query = query.filter(AssignmentDoubt.self_signed_student_id == self_signed_student_id)
    else:
        return None

    return query.order_by(AssignmentDoubt.created_at.desc()).first()


@router.post("/my/favorite-teachers", response_model=FavoriteTeacherResponse)
def add_favorite_teacher(
    data: FavoriteTeacherCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in [UserRole.STUDENT, UserRole.SELF_SIGNED_STUDENT]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only students may manage favorite teachers.")

    teacher_obj, teacher_type = _resolve_teacher_profile_by_id(db, data.teacher_id)
    if not teacher_obj:
        raise HTTPException(status_code=404, detail="Teacher not found.")

    favorite = (
        db.query(FavoriteTeacher)
        .filter(FavoriteTeacher.student_user_id == current_user.id)
        .filter(FavoriteTeacher.teacher_id == str(data.teacher_id))
        .filter(FavoriteTeacher.teacher_type == teacher_type)
        .first()
    )
    if favorite:
        return FavoriteTeacherResponse(teacher_id=str(data.teacher_id), is_favorite=True)

    favorite = FavoriteTeacher(
        student_user_id=current_user.id,
        teacher_id=str(data.teacher_id),
        teacher_type=teacher_type,
    )
    db.add(favorite)
    db.commit()
    db.refresh(favorite)
    return FavoriteTeacherResponse(teacher_id=str(data.teacher_id), is_favorite=True)


@router.get("/my/favorite-teachers", response_model=List[FavoriteTeacherListResponse])
def list_favorite_teachers(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in [UserRole.STUDENT, UserRole.SELF_SIGNED_STUDENT]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only students may view favorite teachers.")

    favorites = (
        db.query(FavoriteTeacher)
        .filter(FavoriteTeacher.student_user_id == current_user.id)
        .all()
    )

    results = []
    for fav in favorites:
        results.append(
            FavoriteTeacherListResponse(
                teacher_id=fav.teacher_id,
                teacher_name=_get_teacher_display_name(db, fav.teacher_id, fav.teacher_type),
                teacher_type=fav.teacher_type,
                is_favorite=True,
            )
        )
    return results


@router.get("/my/favorite-teachers/{teacher_id}", response_model=FavoriteTeacherResponse)
def check_favorite_teacher(
    teacher_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in [UserRole.STUDENT, UserRole.SELF_SIGNED_STUDENT]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only students may view favorite teachers.")

    teacher_obj, teacher_type = _resolve_teacher_profile_by_id(db, teacher_id)
    if not teacher_obj:
        raise HTTPException(status_code=404, detail="Teacher not found.")

    favorite_exists = (
        db.query(FavoriteTeacher)
        .filter(FavoriteTeacher.student_user_id == current_user.id)
        .filter(FavoriteTeacher.teacher_id == str(teacher_id))
        .filter(FavoriteTeacher.teacher_type == teacher_type)
        .first()
    ) is not None

    return FavoriteTeacherResponse(teacher_id=str(teacher_id), is_favorite=favorite_exists)


@router.delete("/my/favorite-teachers/{teacher_id}", response_model=FavoriteTeacherResponse)
def remove_favorite_teacher(
    teacher_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in [UserRole.STUDENT, UserRole.SELF_SIGNED_STUDENT]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only students may manage favorite teachers.")

    teacher_obj, teacher_type = _resolve_teacher_profile_by_id(db, teacher_id)
    if not teacher_obj:
        raise HTTPException(status_code=404, detail="Teacher not found.")

    favorite = (
        db.query(FavoriteTeacher)
        .filter(FavoriteTeacher.student_user_id == current_user.id)
        .filter(FavoriteTeacher.teacher_id == str(teacher_id))
        .filter(FavoriteTeacher.teacher_type == teacher_type)
        .first()
    )
    if not favorite:
        raise HTTPException(status_code=404, detail="Favorite teacher not found.")

    db.delete(favorite)
    db.commit()
    return FavoriteTeacherResponse(teacher_id=str(teacher_id), is_favorite=False)


@router.get("/assignments/catalog", response_model=List[AssignmentResponse])
def get_assignments_catalog(
    board: str = Query(..., description="Board name (e.g., cbse, icse)"),
    class_name: str = Query(..., description="Class name (e.g., standard-2)"),
    subject: str = Query(..., description="Subject name (e.g., Eng, Math)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Browse and retrieve published assignments for a given board/class/subject.

    - `board`, `class_name`, `subject` are required query parameters.
    - Validates that the logged-in user has access to the requested board/class/subject.
    - Returns detailed assignment list with computed counts (participants, doubts, made_ideal).
    - Results sorted by `created_at` descending (newest first).
    - Supports all user roles: Teacher, Self-Signed Teacher, Student, Self-Signed Student.
    """
    # Validate and normalize parameters
    if not board or not class_name or not subject:
        raise HTTPException(status_code=400, detail="board, class_name and subject are required")

    b = board.strip().lower()
    c = class_name.strip().lower()
    s = subject.strip().lower()

    # Role-based access validation
    # Also track whether the requester is a teacher (to include their own drafts later)
    is_teacher_role = current_user.role in [UserRole.TEACHER, UserRole.SELF_SIGNED_TEACHER]

    if current_user.role == UserRole.TEACHER:
        teacher_obj = _get_teacher_for_user(db, current_user)
        if not teacher_obj:
            raise HTTPException(status_code=404, detail="Teacher profile not found.")

        school = getattr(teacher_obj, "school", None)
        teacher_board = None
        if school and getattr(school, "school_board", None):
            teacher_board = str(school.school_board.value if hasattr(school.school_board, "value") else school.school_board).strip().lower()
        if teacher_board and teacher_board != b:
            raise HTTPException(status_code=403, detail="Teacher does not have access to this board")

        valid = (
            db.query(TeacherClassSectionSubject)
            .join(Class, TeacherClassSectionSubject.class_id == Class.id)
            .join(Subject, TeacherClassSectionSubject.subject_id == Subject.id)
            .filter(
                TeacherClassSectionSubject.teacher_id == teacher_obj.id,
                func.lower(Class.name) == c,
                func.lower(Subject.name) == s,
            )
            .first()
        )
        if not valid:
            raise HTTPException(status_code=403, detail="Teacher is not assigned to this class/subject")

    elif current_user.role == UserRole.SELF_SIGNED_TEACHER:
        teacher_obj = _get_teacher_for_user(db, current_user)
        if not teacher_obj:
            raise HTTPException(status_code=404, detail="Teacher profile not found.")

        configs = (
            db.query(SelfSignedTeacherTeachingConfiguration)
            .filter(SelfSignedTeacherTeachingConfiguration.self_signed_teacher_id == teacher_obj.id, SelfSignedTeacherTeachingConfiguration.is_active)
            .all()
        )
        allowed = False
        for cfg in configs:
            if str(cfg.board_id).strip().lower() != b:
                continue
            class_group = db.query(SchoolClassSubject).filter(SchoolClassSubject.id == cfg.class_id).first()
            if not class_group or (class_group.class_name or '').strip().lower() != c:
                continue
            if cfg.subject_ids:
                subjects = db.query(SchoolClassSubject).filter(SchoolClassSubject.id.in_(cfg.subject_ids)).all()
                if any((srow.subject or '').strip().lower() == s and (srow.class_name or '').strip().lower() == c for srow in subjects):
                    allowed = True
                    break
            else:
                # No specific subjects configured — grant access to all subjects in this class
                allowed = True
                break
        if not allowed:
            raise HTTPException(status_code=403, detail="Self-signed teacher not configured for this class/subject")

    elif current_user.role in [UserRole.STUDENT, UserRole.SELF_SIGNED_STUDENT]:
        student_obj = _get_student_for_user(db, current_user)
        if not student_obj:
            raise HTTPException(status_code=404, detail="Student profile not found.")
        if not getattr(student_obj, "select_class_id", None):
            raise HTTPException(status_code=403, detail="Student has no selected class configured")
        class_group = db.query(SchoolClassSubject).filter(SchoolClassSubject.id == student_obj.select_class_id).first()
        if not class_group:
            raise HTTPException(status_code=403, detail="Student class mapping not found")
        if (str(class_group.school_board.value if hasattr(class_group.school_board, "value") else class_group.school_board).strip().lower() != b
            or (class_group.class_name or '').strip().lower() != c
            or (class_group.subject or '').strip().lower() != s):
            raise HTTPException(status_code=403, detail="Student does not have access to this board/class/subject")

    else:
        raise HTTPException(status_code=403, detail="Unauthorized role")

    # Query assignments: all published for this board/class/subject,
    # PLUS the teacher's own drafts if the requester is a teacher.
    board_class_subject_filter = (
        func.lower(func.coalesce(func.nullif(Assignment.board, ''), Assignment.board)) == b,
        func.lower(Assignment.class_name) == c,
        func.lower(Assignment.subject) == s,
    )
    if is_teacher_role:
        # Teachers see: all PUBLISHED assignments + their own assignments in any status
        assignments = (
            db.query(Assignment)
            .filter(*board_class_subject_filter)
            .filter(
                or_(
                    Assignment.status == AssignmentStatus.PUBLISHED,
                    Assignment.created_by_user_id == current_user.id,
                )
            )
            .order_by(Assignment.created_at.desc())
            .all()
        )
    else:
        # Students only see published assignments
        assignments = (
            db.query(Assignment)
            .filter(Assignment.status == AssignmentStatus.PUBLISHED)
            .filter(*board_class_subject_filter)
            .order_by(Assignment.created_at.desc())
            .all()
        )

    # Compute participants_count, doubts_count, made_ideal_count in bulk
    assignment_ids = [a.id for a in assignments]
    if assignment_ids:
        parts_q = (
            db.query(StudentAssignmentProgress.assignment_id, func.count(StudentAssignmentProgress.id))
            .filter(StudentAssignmentProgress.assignment_id.in_(assignment_ids))
            .group_by(StudentAssignmentProgress.assignment_id)
            .all()
        )
        parts_map = {r[0]: int(r[1]) for r in parts_q}

        doubts_q = (
            db.query(AssignmentDoubt.assignment_id, func.count(AssignmentDoubt.id))
            .filter(AssignmentDoubt.assignment_id.in_(assignment_ids))
            .group_by(AssignmentDoubt.assignment_id)
            .all()
        )
        doubts_map = {r[0]: int(r[1]) for r in doubts_q}

        made_ideal_q = (
            db.query(StudentAssignmentProgress.assignment_id, func.count(StudentAssignmentProgress.id))
            .filter(StudentAssignmentProgress.assignment_id.in_(assignment_ids))
            .filter(StudentAssignmentProgress.status == AssignmentStatus.COMPLETED)
            .group_by(StudentAssignmentProgress.assignment_id)
            .all()
        )
        made_map = {r[0]: int(r[1]) for r in made_ideal_q}

        for a in assignments:
            setattr(a, "participants_count", parts_map.get(a.id, 0))
            setattr(a, "doubts_count", doubts_map.get(a.id, 0))
            setattr(a, "made_ideal_count", made_map.get(a.id, 0))

    return assignments


# Backward-compatible aliases for renamed endpoints
@router.get("/assignments/subjects", response_model=List[AssignmentResponse])
def get_assignments_by_subject_legacy(
    board_name: str = Query(..., description="(Legacy) Use 'board' in /assignments/catalog instead"),
    class_name: str = Query(..., description="(Legacy) Use 'class_name' in /assignments/catalog instead"),
    subject_name: str = Query(..., description="(Legacy) Use 'subject' in /assignments/catalog instead"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """[DEPRECATED] Use GET /assignments/catalog instead.
    
    This endpoint is maintained for backward compatibility only.
    New clients should use GET /assignments/catalog with standardized parameter names.
    """
    return get_assignments_catalog(
        board=board_name,
        class_name=class_name,
        subject=subject_name,
        db=db,
        current_user=current_user
    )


@router.get("/me/assignments")
def get_my_assignments(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get personalized assignment summary for the logged-in user.

    Returns a hierarchical summary (Board → Class → Subjects) of assignments relevant to the user:
    - **Teachers & Self-Signed Teachers**: See assignments for their taught/configured classes/subjects
    - **Students & Self-Signed Students**: See assignments for their selected class
    - Includes both published and unpublished assignments (based on user role)
    - Provides counts: total_assignments and created_by_me (for teachers)
    - Optimized with aggregation queries to avoid N+1 problems
    """
    scope_school_id = None

    if current_user.role in [UserRole.TEACHER, UserRole.SELF_SIGNED_TEACHER]:
        teacher_obj = _get_teacher_for_user(db, current_user)
        if not teacher_obj:
            raise HTTPException(status_code=404, detail="Teacher profile not found.")

        scope_school_id = getattr(getattr(teacher_obj, "school", None), "id", None)

        # Build allowed mappings depending on teacher type
        allowed_board_values = set()
        class_names_by_board = {}
        subject_names_by_class = {}

        if current_user.role == UserRole.TEACHER:
            # School teacher: board comes from teacher's school, classes/subjects from TeacherClassSectionSubject
            school = getattr(teacher_obj, "school", None)
            board_value = None
            if school and getattr(school, "school_board", None):
                board_value = str(school.school_board.value if hasattr(school.school_board, 'value') else school.school_board)
                allowed_board_values.add(board_value.lower())

            assignments_map = db.query(TeacherClassSectionSubject).filter(TeacherClassSectionSubject.teacher_id == teacher_obj.id).all()
            for a in assignments_map:
                cls_name = a.class_.name if a.class_ else None
                subj_name = a.subject.name if a.subject else None
                if not cls_name or not subj_name:
                    continue
                class_names_by_board.setdefault(board_value or "", set()).add(cls_name)
                subject_names_by_class.setdefault(cls_name, set()).add(subj_name)

        else:
            # Self-signed teacher: use teaching configurations
            configs = (
                db.query(SelfSignedTeacherTeachingConfiguration)
                .filter(SelfSignedTeacherTeachingConfiguration.self_signed_teacher_id == teacher_obj.id, SelfSignedTeacherTeachingConfiguration.is_active)
                .all()
            )
            for cfg in configs:
                board_val = cfg.board_id
                if board_val:
                    allowed_board_values.add(str(board_val).lower())
                # class_id references SchoolClassSubject
                class_group = db.query(SchoolClassSubject).filter(SchoolClassSubject.id == cfg.class_id).first()
                cls_name = class_group.class_name if class_group else None
                if cls_name:
                    class_names_by_board.setdefault(cfg.board_id or "", set()).add(cls_name)
                # subject_ids are school_classes_subjects ids; fetch their subject names
                if cfg.subject_ids:
                    subjects = db.query(SchoolClassSubject).filter(SchoolClassSubject.id.in_(cfg.subject_ids)).all()
                    for s in subjects:
                        if s and s.subject and cls_name and s.class_name == cls_name:
                            subject_names_by_class.setdefault(cls_name, set()).add(s.subject)

    elif current_user.role in [UserRole.STUDENT, UserRole.SELF_SIGNED_STUDENT]:
        student_obj = _get_student_for_user(db, current_user)
        if not student_obj:
            raise HTTPException(status_code=404, detail="Student profile not found.")

        board_value = None
        class_name = None
        if current_user.role == UserRole.STUDENT:
            school = getattr(student_obj, "school", None)
            scope_school_id = getattr(school, "id", None)
            if school and getattr(school, "school_board", None):
                board_value = str(school.school_board.value if hasattr(school.school_board, 'value') else school.school_board)
            class_obj = getattr(student_obj, "classes", None)
            class_name = getattr(class_obj, "name", None) or getattr(student_obj, "class_id", None)
        else:
            if getattr(student_obj, "select_class_id", None):
                class_group = db.query(SchoolClassSubject).filter(SchoolClassSubject.id == student_obj.select_class_id).first()
                if class_group:
                    board_value = str(class_group.school_board.value if hasattr(class_group.school_board, 'value') else class_group.school_board)
                    class_name = class_group.class_name
            if not board_value and getattr(student_obj, "select_board", None):
                board_value = str(student_obj.select_board)

        if not board_value or not class_name:
            return {"data": []}

        allowed_board_values = {board_value.lower()} if board_value else set()
        class_names_by_board = {board_value or "": {class_name}} if class_name else {}

        subject_rows = (
            db.query(Subject)
            .join(class_subjects, class_subjects.c.subject_id == Subject.id)
            .join(Class, Class.id == class_subjects.c.class_id)
            .filter(
                Class.school_id == scope_school_id,
                func.lower(func.coalesce(Class.name, "")) == str(class_name).strip().lower(),
            )
            .all()
        )
        subject_names_by_class = {}
        if class_name:
            subject_names_by_class[class_name] = set()
        for subject_row in subject_rows:
            if subject_row.name and class_name:
                subject_names_by_class.setdefault(class_name, set()).add(subject_row.name)

    else:
        raise HTTPException(status_code=403, detail="Only teachers and students may access this resource.")

    # For students: only count published assignments.
    # For teachers: count ALL their own assignments (draft, published, etc.)
    is_teacher = current_user.role in [UserRole.TEACHER, UserRole.SELF_SIGNED_TEACHER]

    if is_teacher:
        # teacher sees their own assignments in any status
        base_filter = Assignment.created_by_user_id == current_user.id
    else:
        # students only see published
        base_filter = Assignment.status == AssignmentStatus.PUBLISHED

    # Aggregate totals grouped by board, class_name, subject
    # Exclude tuition-linked assignments — they appear in the tuition section, not here
    agg_query = (
        db.query(
            func.coalesce(func.nullif(Assignment.board, ''), Assignment.board).label('board'),
            Assignment.class_name.label('class_name'),
            Assignment.subject.label('subject'),
            func.count(Assignment.id).label('total'),
        )
        .filter(base_filter)
        .filter(Assignment.tuition_setup_id.is_(None))
        .filter(Assignment.tuition_date.is_(None))
    )


    # Apply board filter if known
    if allowed_board_values:
        agg_query = agg_query.filter(func.lower(Assignment.board).in_(list(allowed_board_values)))

    # Apply class/subject filters if present
    class_conds = []
    subject_conds = []
    all_class_names = set()
    all_subject_names = set()
    for cls_set in class_names_by_board.values():
        all_class_names.update(cls_set)
    for subj_set in subject_names_by_class.values():
        all_subject_names.update(subj_set)

    if all_class_names:
        class_conds.append(Assignment.class_name.in_(list(all_class_names)))
    if all_subject_names:
        subject_conds.append(Assignment.subject.in_(list(all_subject_names)))

    if class_conds and subject_conds:
        agg_query = agg_query.filter(and_(*class_conds), and_(*subject_conds))
    elif class_conds:
        agg_query = agg_query.filter(and_(*class_conds))
    elif subject_conds:
        agg_query = agg_query.filter(and_(*subject_conds))

    agg_query = agg_query.group_by(Assignment.board, Assignment.class_name, Assignment.subject)
    totals = agg_query.all()

    # Build counts lookup: (class_name_lower, subject_lower) -> total assignment count
    counts_map = {}
    for r in totals:
        kc = (r.class_name or '').strip().lower()
        ks = (r.subject or '').strip().lower()
        counts_map[(kc, ks)] = int(r.total or 0)

    # Build a per-subject lookup for the current teacher's own assignments.
    my_counts_map = {}
    if is_teacher:
        my_totals_query = (
            db.query(
                Assignment.class_name.label('class_name'),
                Assignment.subject.label('subject'),
                func.count(Assignment.id).label('my_total'),
            )
            .filter(base_filter)
            .filter(Assignment.tuition_setup_id.is_(None))
            .filter(Assignment.tuition_date.is_(None))
        )
        if allowed_board_values:
            my_totals_query = my_totals_query.filter(func.lower(Assignment.board).in_(list(allowed_board_values)))
        if class_conds and subject_conds:
            my_totals_query = my_totals_query.filter(and_(*class_conds), and_(*subject_conds))
        elif class_conds:
            my_totals_query = my_totals_query.filter(and_(*class_conds))
        elif subject_conds:
            my_totals_query = my_totals_query.filter(and_(*subject_conds))
        my_totals_query = my_totals_query.group_by(Assignment.class_name, Assignment.subject)
        for r in my_totals_query.all():
            kc = (r.class_name or '').strip().lower()
            ks = (r.subject or '').strip().lower()
            my_counts_map[(kc, ks)] = int(r.my_total or 0)

    # Pre-fetch SchoolClassSubject rows for efficient ID resolution
    # class_id  = SchoolClassSubject.id matched by (board + class_name) — any subject row for that class
    # subject_id = SchoolClassSubject.id matched by (board + class_name + subject)
    def _admin_class_id(board: str, class_name: str) -> int | None:
        row = (
            db.query(SchoolClassSubject.id)
            .filter(func.lower(func.coalesce(SchoolClassSubject.class_name, '')) == class_name.strip().lower())
            .order_by(SchoolClassSubject.id)
            .first()
        )
        return row[0] if row else None

    def _admin_subject_id(board: str, class_name: str, subject_name: str) -> int | None:
        row = (
            db.query(SchoolClassSubject.id)
            .filter(func.lower(func.coalesce(SchoolClassSubject.class_name, '')) == class_name.strip().lower())
            .filter(func.lower(func.coalesce(SchoolClassSubject.subject, '')) == subject_name.strip().lower())
            .order_by(SchoolClassSubject.id)
            .first()
        )
        return row[0] if row else None

    # Always show ALL subjects from the teacher's profile, including those with 0 assignments.
    data = []
    for board_name, class_names in class_names_by_board.items():
        for class_name in sorted(class_names or set()):
            class_id = _admin_class_id(board_name, class_name)
            seen_subject_keys = set()
            subjects = []
            for subject_name in sorted(subject_names_by_class.get(class_name, set()) or set()):
                normalized_subject_key = (subject_name or '').strip().lower()
                if normalized_subject_key in seen_subject_keys:
                    continue
                seen_subject_keys.add(normalized_subject_key)
                subject_id = _admin_subject_id(board_name, class_name, subject_name)
                count = counts_map.get((class_name.strip().lower(), normalized_subject_key), 0)
                subjects.append({
                    "subject_name": subject_name,
                    "subject_id": subject_id,
                    "my_assignments": my_counts_map.get((class_name.strip().lower(), normalized_subject_key), 0),
                    "total_assignments": count,
                })
            data.append({
                "board_name": board_name,
                "class_name": class_name,
                "class_id": class_id,
                "subjects": subjects,
            })

    return {"data": data}



@router.get("/assignments/my-assignments")
def my_assignments_summary_legacy(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """[DEPRECATED] Use GET /me/assignments instead.
    
    This endpoint is maintained for backward compatibility only.
    New clients should use GET /me/assignments for clearer intent and RESTful compliance.
    """
    return get_my_assignments(db=db, current_user=current_user)


@router.get("/assignments")
def get_all_assignments(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    board: str | None = Query(None),
    medium: str | None = Query(None),
    class_name: str | None = Query(None),
    class_id: int | None = Query(None),
    subject: str | None = Query(None),
    subject_id: int | None = Query(None),
    status: str | None = Query(None, description="Filter by status: 'published' or 'unpublished' (defaults to both)"),
    chapter_number: int | None = Query(None),
    teacher_id: int | None = Query(None),
    school_name: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
):
    """List assignments with role-based filtering and advanced search options.
    
    **Access Control:**
    - **Teachers:** See their own assignments + published assignments for their assigned classes/subjects
    - **Self-Signed Teachers:** See their own assignments + published for their teaching configuration
    - **Students:** See published assignments for their selected class
    - **Self-Signed Students:** See published assignments for their selected class
    
    **Query Parameters:**
    - `board`: Filter by board name (e.g., cbse, icse)
    - `medium`: Filter by medium/activity type
    - `class_name`: Filter by class name
    - `class_id`: Filter by class ID (normalized FK)
    - `subject`: Filter by subject name
    - `subject_id`: Filter by subject ID (normalized FK)
    - `chapter_number`: Filter by chapter number
    - `teacher_id`: Filter by creator teacher ID
    - `school_name`: Filter by school name (partial match)
    - `skip`: Pagination offset (default 0)
    - `limit`: Results per page (default 20, max 100)
    
    **Response:** Paginated list of published assignments sorted by published_at desc, then created_at desc.
    """
    query = db.query(Assignment)

    # Determine statuses to include for published/unpublished filter (drafts excluded).
    # Teachers can still see their own drafts via the created_by_* conditions.
    if status is None:
        statuses_to_include = [AssignmentStatus.PUBLISHED, AssignmentStatus.UNPUBLISHED]
    elif isinstance(status, str) and status.lower() == "published":
        statuses_to_include = [AssignmentStatus.PUBLISHED]
    elif isinstance(status, str) and status.lower() == "unpublished":
        statuses_to_include = [AssignmentStatus.UNPUBLISHED]
    else:
        raise HTTPException(status_code=400, detail="Invalid status filter. Use 'published' or 'unpublished'")
    
    # Apply role-based filtering
    if current_user.role == UserRole.TEACHER:
        teacher_obj = _get_teacher_for_user(db, current_user)
        if not teacher_obj:
            raise HTTPException(status_code=404, detail="Teacher profile not found.")
        
        school = getattr(teacher_obj, "school", None)
        teacher_board = None
        if school and getattr(school, "school_board", None):
            teacher_board = str(school.school_board.value if hasattr(school.school_board, "value") else school.school_board).strip()
        
        assignments_map = db.query(TeacherClassSectionSubject).filter(TeacherClassSectionSubject.teacher_id == teacher_obj.id).all()
        allowed_classes = {a.class_.name for a in assignments_map if a.class_}
        allowed_subjects = {a.subject.name for a in assignments_map if a.subject}
        
        # Own assignments + published for authorized classes/subjects
        query = query.filter(
            or_(
                Assignment.created_by_user_id == current_user.id,
                and_(
                    Assignment.status.in_(statuses_to_include),
                    Assignment.class_name.in_(list(allowed_classes)) if allowed_classes else False,
                    Assignment.subject.in_(list(allowed_subjects)) if allowed_subjects else False,
                    Assignment.board == teacher_board if teacher_board else True,
                ),
            )
        )
    
    elif current_user.role == UserRole.SELF_SIGNED_TEACHER:
        teacher_obj = _get_teacher_for_user(db, current_user)
        if not teacher_obj:
            raise HTTPException(status_code=404, detail="Teacher profile not found.")
        
        configs = (
            db.query(SelfSignedTeacherTeachingConfiguration)
            .filter(
                SelfSignedTeacherTeachingConfiguration.self_signed_teacher_id == teacher_obj.id,
                SelfSignedTeacherTeachingConfiguration.is_active,
            )
            .all()
        )
        
        allowed_boards = set()
        allowed_class_subjects = []
        for cfg in configs:
            allowed_boards.add(str(cfg.board_id).strip().lower())
            class_group = db.query(SchoolClassSubject).filter(SchoolClassSubject.id == cfg.class_id).first()
            if class_group:
                allowed_class_subjects.append((cfg.board_id, class_group.class_name))
            if cfg.subject_ids:
                subjects = db.query(SchoolClassSubject).filter(SchoolClassSubject.id.in_(cfg.subject_ids)).all()
                for s in subjects:
                    if s:
                        allowed_class_subjects.append((cfg.board_id, s.class_name, s.subject))
        
        query = query.filter(
            or_(
                Assignment.created_by_self_signed_teacher_id == teacher_obj.id,
                and_(
                    Assignment.status.in_(statuses_to_include),
                    func.lower(Assignment.board).in_(list(allowed_boards)) if allowed_boards else False,
                ),
            )
        )
    
    elif current_user.role == UserRole.STUDENT:
        student_obj = _get_student_for_user(db, current_user)
        if not student_obj:
            raise HTTPException(status_code=404, detail="Student profile not found.")
        
        class_group = None
        if getattr(student_obj, "select_class_id", None):
            class_group = db.query(SchoolClassSubject).filter(SchoolClassSubject.id == student_obj.select_class_id).first()
        
        if class_group:
            # Students always see only published assignments regardless of the status filter
            query = query.filter(
                Assignment.status == AssignmentStatus.PUBLISHED,
                Assignment.class_name == class_group.class_name,
                Assignment.board == (class_group.school_board.value if hasattr(class_group.school_board, "value") else class_group.school_board),
            )
        elif board and class_name:
            query = query.filter(
                Assignment.status == AssignmentStatus.PUBLISHED,
                func.lower(Assignment.board) == board.lower(),
                func.lower(Assignment.class_name) == class_name.lower(),
            )
        else:
            return {"data": [], "total": 0, "skip": skip, "limit": limit}
    
    elif current_user.role == UserRole.SELF_SIGNED_STUDENT:
        student_obj = _get_student_for_user(db, current_user)
        if not student_obj:
            raise HTTPException(status_code=404, detail="Student profile not found.")

        class_group = None
        if getattr(student_obj, "select_class_id", None):
            class_group = db.query(SchoolClassSubject).filter(SchoolClassSubject.id == student_obj.select_class_id).first()
        
        if class_group:
            # Self-signed students also see only published assignments
            query = query.filter(
                Assignment.status == AssignmentStatus.PUBLISHED,
                Assignment.class_name == class_group.class_name,
                Assignment.board == (class_group.school_board.value if hasattr(class_group.school_board, "value") else class_group.school_board),
            )
        elif board and class_name:
            query = query.filter(
                Assignment.status == AssignmentStatus.PUBLISHED,
                func.lower(Assignment.board) == board.lower(),
                func.lower(Assignment.class_name) == class_name.lower(),
            )
        else:
            return {"data": [], "total": 0, "skip": skip, "limit": limit}
    
    else:
        raise HTTPException(status_code=403, detail="Unauthorized role.")
    
    # Apply optional query parameter filters
    if board:
        query = query.filter(func.lower(Assignment.board) == board.lower())
    if medium:
        query = query.filter(func.lower(Assignment.activity_type) == medium.lower())
    if class_name:
        query = query.filter(func.lower(Assignment.class_name) == class_name.lower())
    if class_id is not None:
        query = query.filter(Assignment.class_id == class_id)
    if subject:
        query = query.filter(func.lower(Assignment.subject) == subject.lower())
    if subject_id is not None:
        query = query.filter(Assignment.subject_id == subject_id)
    if chapter_number is not None:
        query = query.filter(Assignment.chapter_number == chapter_number)
    if teacher_id is not None:
        query = query.filter(Assignment.created_by_user_id == teacher_id)
    if school_name:
        query = query.filter(func.lower(Assignment.school_name).ilike(f"%{school_name.lower()}%"))
    
    total = query.count()
    assignments = query.order_by(Assignment.published_at.desc(), Assignment.created_at.desc()).offset(skip).limit(limit).all()
    
    return {
        "data": assignments,
        "total": total,
        "skip": skip,
        "limit": limit,
    }


def _build_teacher_school_denorm(teacher_obj):
    if not teacher_obj:
        return {
            "teacher_name": None,
            "school_name": None,
            "school_address": None,
        }
    school = getattr(teacher_obj, "school", None)
    if school:
        # School model uses `school_name` and address fields like `school_location`, `district`, `state`, `pin_code`
        school_name = getattr(school, "school_name", None)
        address_parts = [
            getattr(school, "school_location", None),
            getattr(school, "district", None),
            getattr(school, "state", None),
            getattr(school, "pin_code", None),
        ]
        school_address = ", ".join(filter(None, [str(p).strip() for p in address_parts if p])) or None
    else:
        school_name = None
        school_address = None

    teacher_name = f"{teacher_obj.first_name} {teacher_obj.last_name}"
    return {
        "teacher_name": teacher_name,
        "school_name": school_name,
        "school_address": school_address,
    }


def _pending_tasks_count(assignment: Assignment) -> int:
    count = 0
    if not assignment.chapter_name:
        count += 1
    if not assignment.sub_chapters:
        count += 1
    if not assignment.questions:
        count += 1
    return count


def _compute_teacher_stats(db: Session, teacher_obj) -> dict:
    if isinstance(teacher_obj, Teacher):
        assignment_count = (
            db.query(func.count(Assignment.id))
            .filter(Assignment.created_by_teacher_id == teacher_obj.id)
            .scalar()
            or 0
        )
        participant_count = (
            db.query(func.count(StudentAssignmentAttempt.id))
            .join(Assignment, Assignment.id == StudentAssignmentAttempt.assignment_id)
            .filter(Assignment.created_by_teacher_id == teacher_obj.id)
            .scalar()
            or 0
        )
    elif isinstance(teacher_obj, SelfSignedTeacher):
        assignment_count = (
            db.query(func.count(Assignment.id))
            .filter(Assignment.created_by_self_signed_teacher_id == teacher_obj.id)
            .scalar()
            or 0
        )
        participant_count = (
            db.query(func.count(StudentAssignmentAttempt.id))
            .join(Assignment, Assignment.id == StudentAssignmentAttempt.assignment_id)
            .filter(Assignment.created_by_self_signed_teacher_id == teacher_obj.id)
            .scalar()
            or 0
        )
    else:
        assignment_count = 0
        participant_count = 0

    return {
        "total_exams_count": 0,
        "total_assignments_count": assignment_count,
        "total_participants_count": participant_count,
        "average_rating": 0.0,
    }


def _validate_image_file(file: UploadFile) -> str:
    """Validate image file type and size (max 10MB). Returns file extension or raises HTTPException."""
    allowed_types = {"image/jpeg", "image/png", "image/webp"}
    allowed_exts = {"jpg", "jpeg", "png", "webp"}
    
    ext = file.filename.split(".")[-1].lower() if file.filename else ""
    if ext not in allowed_exts or (file.content_type and file.content_type not in allowed_types):
        raise HTTPException(status_code=400, detail="Invalid image type. Allowed: JPG, PNG, WEBP")
    
    file.file.seek(0, 2)
    size = file.file.tell()
    file.file.seek(0)
    if size > 10 * 1024 * 1024:  # 10 MB
        raise HTTPException(status_code=413, detail="Image file exceeds 10MB limit")
    
    return ext


def _get_upload_file_size(file: UploadFile) -> int:
    if not file or not getattr(file, "file", None):
        return 0
    try:
        file.file.seek(0, 2)
        size = file.file.tell()
        file.file.seek(0)
        return size
    except Exception:
        return 0


def _update_assignment_file_stats(assignment: Assignment, file_size_bytes: int, count: int = 1) -> None:
    assignment.total_file_size_bytes = (assignment.total_file_size_bytes or 0) + file_size_bytes
    assignment.total_file_count = (assignment.total_file_count or 0) + count


def _build_assignment_file_usage_summary(assignment: Assignment | None) -> AssignmentFileUsageSummary:
    if assignment is None:
        return AssignmentFileUsageSummary()

    total_size = int(assignment.total_file_size_bytes or 0)
    total_count = int(assignment.total_file_count or 0)
    size_kb = round(total_size / 1024, 2) if total_size else 0.0
    size_mb = round(size_kb / 1024, 4) if size_kb else 0.0

    if size_mb >= 1:
        numeric_label = f"{size_mb:.2f}".rstrip('0').rstrip('.')
        storage_label = f"{numeric_label} MB"
    elif size_kb >= 1:
        numeric_label = f"{size_kb:.2f}".rstrip('0').rstrip('.')
        storage_label = f"{numeric_label} KB"
    else:
        storage_label = f"{total_size} bytes"

    return AssignmentFileUsageSummary(
        assignment_id=assignment.id,
        total_file_count=total_count,
        total_file_size_bytes=total_size,
        total_file_size_kb=size_kb,
        total_file_size_mb=size_mb,
        storage_label=storage_label,
    )


def _validate_pdf_file(file: UploadFile) -> str:
    """Validate PDF file type and size (max 10MB). Returns 'pdf' or raises HTTPException."""
    if file.content_type != "application/pdf" and not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="File must be a PDF")
    
    file.file.seek(0, 2)
    size = file.file.tell()
    file.file.seek(0)
    if size > 10 * 1024 * 1024:  # 10 MB
        raise HTTPException(status_code=413, detail="PDF file exceeds 10MB limit")
    
    return "pdf"


def _validate_video_urls(video_urls: list[str] | None) -> List[str]:
    """Validate video URLs: max 3, HTTPS only. Raise HTTPException on validation failure."""
    if video_urls is None:
        return []
    if not isinstance(video_urls, list):
        raise HTTPException(status_code=400, detail="video_links must be a list of HTTPS URLs")
    
    if len(video_urls) > 3:
        raise HTTPException(status_code=400, detail="Maximum 3 video URLs allowed per assignment")
    
    for url in video_urls:
        if not isinstance(url, str) or not url.startswith("https://"):
            raise HTTPException(status_code=400, detail="Video URLs must be HTTPS strings")
    
    return video_urls


@router.post("/assignments", response_model=AssignmentResponse, summary="Create Assignment", tags=["Assignments"])
async def create_assignment(
    payload: AssignmentCreate = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    **Create a new assignment.**

    - Status is always set to `draft` automatically.
    - Upload files separately via `POST /assignments/{id}/files` after creation.
    - Add questions separately via `POST /assignments/{id}/questions`.
    """

    if current_user.role not in [UserRole.TEACHER, UserRole.SELF_SIGNED_TEACHER]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only teachers may create assignments.")

    teacher_obj = _get_teacher_for_user(db, current_user)
    if not teacher_obj:
        raise HTTPException(status_code=404, detail="Teacher profile not found.")

    data_dict = payload.model_dump(exclude_unset=True)

    # Validate required fields
    required_fields = ["board", "class_name", "subject", "chapter_number", "chapter_name"]
    for field in required_fields:
        if field not in data_dict or not data_dict[field]:
            raise HTTPException(status_code=400, detail=f"Missing required field: {field}")

    board_value = str(data_dict.get("board")).strip()
    class_name_value = str(data_dict.get("class_name")).strip()
    subject_value = str(data_dict.get("subject")).strip()
    class_id_value = data_dict.get("class_id")
    subject_id_value = data_dict.get("subject_id")

    # ── Admin-list validation ──────────────────────────────────────────────
    # The board + class_name + subject combination MUST exist in the admin-
    # configured school_classes_subjects table.
    admin_combo = (
        db.query(SchoolClassSubject)
        .filter(func.lower(func.coalesce(SchoolClassSubject.class_name, "")) == class_name_value.lower())
        .filter(func.lower(func.coalesce(SchoolClassSubject.subject, "")) == subject_value.lower())
        .first()
    )
    if not admin_combo:
        # Build a helpful list of valid classes & subjects for this board
        valid_rows = (
            db.query(SchoolClassSubject.class_name, SchoolClassSubject.subject)
            .filter(SchoolClassSubject.class_name.isnot(None))
            .order_by(SchoolClassSubject.class_name, SchoolClassSubject.subject)
            .distinct()
            .limit(20)
            .all()
        )
        valid_list = ", ".join(
            f"{r.class_name}/{r.subject}" for r in valid_rows if r.class_name and r.subject
        ) or "None configured yet"
        raise HTTPException(
            status_code=400,
            detail=(
                f"The combination class_name='{class_name_value}' and subject='{subject_value}' "
                f"is not in the admin list. Valid pairs: {valid_list}"
            )
        )

    if (class_id_value in (None, "", 0)) and class_name_value:
        class_lookup = (
            db.query(SchoolClassSubject)
            .filter(func.lower(func.coalesce(SchoolClassSubject.class_name, "")) == class_name_value.strip().lower())
            .first()
        )
        if class_lookup:
            class_id_value = class_lookup.id

    if (subject_id_value in (None, "", 0)) and subject_value:
        subject_lookup = (
            db.query(SchoolClassSubject)
            .filter(func.lower(func.coalesce(SchoolClassSubject.subject, "")) == subject_value.strip().lower())
            .first()
        )
        if subject_lookup:
            subject_id_value = subject_lookup.id

    if current_user.role == UserRole.TEACHER:
        school = getattr(teacher_obj, "school", None)
        if not school or not getattr(school, "school_board", None):
            raise HTTPException(status_code=403, detail="Teacher school board is not configured.")

        teacher_board = str(school.school_board.value if hasattr(school.school_board, "value") else school.school_board).strip()
        if teacher_board.lower() != board_value.lower():
            raise HTTPException(status_code=403, detail="Board value must match the teacher's school board.")

        valid_assignment = (
            db.query(TeacherClassSectionSubject)
            .join(Class, TeacherClassSectionSubject.class_id == Class.id)
            .join(Subject, TeacherClassSectionSubject.subject_id == Subject.id)
            .filter(
                TeacherClassSectionSubject.teacher_id == teacher_obj.id,
                Class.name == class_name_value,
                Subject.name == subject_value,
            )
            .first()
        )
        if not valid_assignment:
            raise HTTPException(status_code=403, detail="Teacher is not assigned to this class and subject.")

    else:
        # SELF_SIGNED_TEACHER
        configs = (
            db.query(SelfSignedTeacherTeachingConfiguration)
            .filter(
                SelfSignedTeacherTeachingConfiguration.self_signed_teacher_id == teacher_obj.id,
                SelfSignedTeacherTeachingConfiguration.is_active,
            )
            .all()
        )
        if not configs:
            raise HTTPException(status_code=403, detail="No active teaching configuration found.")

        allowed = False
        for cfg in configs:
            if str(cfg.board_id).strip().lower() != board_value.lower():
                continue

            class_group = db.query(SchoolClassSubject).filter(SchoolClassSubject.id == cfg.class_id).first()
            if not class_group or class_group.class_name != class_name_value:
                continue

            subject_rows = db.query(SchoolClassSubject).filter(SchoolClassSubject.id.in_(cfg.subject_ids)).all()
            if any(row.subject == subject_value and row.class_name == class_name_value for row in subject_rows):
                allowed = True
                break

        if not allowed:
            # Validation disabled: allow creation even if not present in the teaching configuration.
            # Previously this returned HTTP 403; keeping a no-op now to permit assignment creation.
            pass

    # class_id vs class_name strict matching validation removed per request.
    # If provided, `class_id` will be stored but not required to match the `class_name` string.

    # subject_id strict matching validation removed per request.
    # If provided, `subject_id` will be stored but not required to match the `subject` string.

    # Validate video URLs if provided
    video_urls = _validate_video_urls(data_dict.get("video_links", []))
    if "sub_chapters" in data_dict and data_dict["sub_chapters"] is not None and not isinstance(data_dict["sub_chapters"], list):
        raise HTTPException(status_code=400, detail="sub_chapters must be a list")
    if "questions" in data_dict and data_dict["questions"] is not None and not isinstance(data_dict["questions"], list):
        raise HTTPException(status_code=400, detail="questions must be a list")
    
    # Validate and enforce chapter number constraints
    try:
        chapter_number_val = int(data_dict.get("chapter_number"))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid chapter_number value")

    # Rule 1: chapter_number must be between 1 and 15
    if not (1 <= chapter_number_val <= 15):
        raise HTTPException(
            status_code=400,
            detail=f"chapter_number must be between 1 and 15 (got {chapter_number_val})"
        )

    kb = board_value.strip().lower()
    kc = class_name_value.strip().lower()
    ks = subject_value.strip().lower()

    # Rule 2: A teacher can only have ONE assignment per (board, class, subject, chapter_number)
    existing = (
        db.query(Assignment)
        .filter(func.lower(Assignment.board) == kb)
        .filter(func.lower(Assignment.class_name) == kc)
        .filter(func.lower(Assignment.subject) == ks)
        .filter(Assignment.chapter_number == chapter_number_val)
        .filter(Assignment.created_by_user_id == current_user.id)
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"You already have an assignment for chapter {chapter_number_val} "
                   f"({board_value} / {class_name_value} / {subject_value}). "
                   f"Each teacher can only create one assignment per chapter."
        )

    # Rule 3: Global cap — max 5 assignments per (board, class, subject, chapter_number) across ALL teachers
    # Exclude tuition-linked assignments because they are independent and should not consume the global chapter quota.
    global_count = (
        db.query(func.count(Assignment.id))
        .filter(func.lower(Assignment.board) == kb)
        .filter(func.lower(Assignment.class_name) == kc)
        .filter(func.lower(Assignment.subject) == ks)
        .filter(Assignment.chapter_number == chapter_number_val)
        .filter(Assignment.tuition_setup_id.is_(None))
        .filter(Assignment.tuition_date.is_(None))
        .scalar() or 0
    )
    if global_count >= 5:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Chapter {chapter_number_val} ({board_value} / {class_name_value} / {subject_value}) "
                f"already has the maximum of 5 assignments. No more teachers can create an assignment for this chapter."
            )
        )

    
    # Build denormalized teacher/school info
    denorm = _build_teacher_school_denorm(teacher_obj)
    
    # Create assignment record
    sub_chapters_payload = data_dict.get("sub_chapters")
    if sub_chapters_payload is not None:
        normalized_sub_chapters = []
        for item in sub_chapters_payload:
            if hasattr(item, "model_dump"):
                normalized_sub_chapters.append(item.model_dump())
            else:
                normalized_sub_chapters.append(item)
        sub_chapters_payload = normalized_sub_chapters

    assignment_kwargs = {
        "created_by_user_id": current_user.id,
        "status": AssignmentStatus.PUBLISHED,
        "board": board_value,
        "class_name": class_name_value,
        "subject": subject_value,
        "title": data_dict.get("title"),
        "chapter_number": data_dict.get("chapter_number"),
        "chapter_name": data_dict.get("chapter_name"),
        "chapter_description": data_dict.get("chapter_description"),
        "sub_chapters": sub_chapters_payload,
        "chapter_tagline": data_dict.get("chapter_tagline"),
        "teacher_name": denorm["teacher_name"],
        "school_name": denorm["school_name"],
        "school_address": denorm["school_address"],
        "tuition_setup_id": data_dict.get("tuition_setup_id"),
        "tuition_date": data_dict.get("tuition_date"),
    }


    if current_user.role == UserRole.TEACHER:
        assignment_kwargs["created_by_teacher_id"] = teacher_obj.id
    elif current_user.role == UserRole.SELF_SIGNED_TEACHER:
        assignment_kwargs["created_by_self_signed_teacher_id"] = teacher_obj.id


    assignment = Assignment(**assignment_kwargs)
    
    # Parse and add questions
    if data_dict.get("questions"):
        for q_data in data_dict["questions"]:
            if hasattr(q_data, "model_dump"):
                q_payload = q_data.model_dump()
            else:
                q_payload = q_data
            question = AssignmentQuestion(
                question_number=q_payload.get("question_number"),
                question_text=q_payload.get("question_text"),
                option_a=q_payload.get("option_a"),
                option_b=q_payload.get("option_b"),
                option_c=q_payload.get("option_c"),
                option_d=q_payload.get("option_d"),
                correct_option=q_payload.get("correct_option"),
                solution_explanation=q_payload.get("solution_explanation"),
            )
            assignment.questions.append(question)
    
    # Add video link records
    for video_url in video_urls:
        assignment.video_links.append(AssignmentVideoLink(url=video_url))
    
    # Set publish config fields if provided
    if data_dict.get("assignment_type"):
        pass
    
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    assignment_response = AssignmentResponse.model_validate(assignment)
    assignment_response.file_usage = _build_assignment_file_usage_summary(assignment)
    return assignment_response


@router.post("/assignments/{assignment_id}/questions", response_model=List[AssignmentQuestionResponse], summary="Add Questions", tags=["Assignments"])
def add_assignment_questions(
    assignment_id: int,
    data: AssignmentQuestionBatchCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    **Add MCQ questions to an existing assignment.**

    - Send one or more questions in the `questions` array.
    - Questions are appended; existing questions are preserved.
    - Only the assignment owner (teacher) can add questions.
    """
    if current_user.role not in [UserRole.TEACHER, UserRole.SELF_SIGNED_TEACHER]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only teachers may add questions.")

    assignment = db.query(Assignment).filter(Assignment.id == assignment_id).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found.")
    if assignment.created_by_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the owning teacher may update this assignment.")

    created_questions = []
    for q_data in data.questions:
        question = AssignmentQuestion(
            assignment_id=assignment.id,
            question_number=q_data.question_number,
            question_text=q_data.question_text,
            option_a=q_data.option_a,
            option_b=q_data.option_b,
            option_c=q_data.option_c,
            option_d=q_data.option_d,
            correct_option=q_data.correct_option,
            solution_explanation=q_data.solution_explanation,
        )
        db.add(question)
        created_questions.append(question)

    db.commit()
    for q in created_questions:
        db.refresh(q)
    return created_questions


@router.patch(
    "/assignments/{assignment_id}/questions/{question_id}",
    response_model=AssignmentQuestionResponse,
    summary="Edit Question",
    tags=["Assignments"],
)
def edit_assignment_question(
    assignment_id: int,
    question_id: int,
    data: AssignmentQuestionPatch,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    **Edit an existing MCQ question on an assignment.**

    - Send only the fields you want to change — all are optional.
    - Only the assignment owner (teacher) can edit questions.
    """
    if current_user.role not in [UserRole.TEACHER, UserRole.SELF_SIGNED_TEACHER]:
        raise HTTPException(status_code=403, detail="Only teachers may edit questions.")

    assignment = db.query(Assignment).filter(Assignment.id == assignment_id).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found.")
    if assignment.created_by_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the owning teacher may edit questions.")

    question = db.query(AssignmentQuestion).filter(
        AssignmentQuestion.id == question_id,
        AssignmentQuestion.assignment_id == assignment_id,
    ).first()
    if not question:
        raise HTTPException(status_code=404, detail="Question not found on this assignment.")

    patch = data.model_dump(exclude_unset=True)
    for field, value in patch.items():
        setattr(question, field, value)

    db.commit()
    db.refresh(question)
    return question


@router.delete(
    "/assignments/{assignment_id}/questions/{question_id}",
    summary="Delete Question",
    tags=["Assignments"],
)
def delete_assignment_question(
    assignment_id: int,
    question_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    **Delete a question from an assignment.**

    - Only the assignment owner (teacher) can delete questions.
    """
    if current_user.role not in [UserRole.TEACHER, UserRole.SELF_SIGNED_TEACHER]:
        raise HTTPException(status_code=403, detail="Only teachers may delete questions.")

    assignment = db.query(Assignment).filter(Assignment.id == assignment_id).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found.")
    if assignment.created_by_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the owning teacher may delete questions.")

    question = db.query(AssignmentQuestion).filter(
        AssignmentQuestion.id == question_id,
        AssignmentQuestion.assignment_id == assignment_id,
    ).first()
    if not question:
        raise HTTPException(status_code=404, detail="Question not found on this assignment.")

    db.delete(question)
    db.commit()
    return {"detail": "Question deleted.", "question_id": question_id, "assignment_id": assignment_id}


@router.post("/assignments/{assignment_id}/files", response_model=List[AssignmentFileResponse], summary="Upload Files & Images", tags=["Assignments"])
async def upload_assignment_files(
    assignment_id: int,
    files: List[UploadFile] = File(...),
    metadata_json: str | None = Form(None, description='JSON string matching AssignmentFileUploadPayload, e.g. {"files":[{"sub_chapter_name":"Place Value","file_name":"worksheet.pdf","file_type":"pdf","usage":"subchapter_file"}]}'),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    **Upload PDF or image files for an assignment.**

    - Multipart form: `files` = actual file(s), `metadata_json` = JSON metadata per file.
    - `usage` values: `subchapter_file` | `key_point_image`.
    - Files are stored in S3; max 10 MB each.
    """
    if current_user.role not in [UserRole.TEACHER, UserRole.SELF_SIGNED_TEACHER]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only teachers may upload assignment files.")

    assignment = db.query(Assignment).filter(Assignment.id == assignment_id).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found.")
    if assignment.created_by_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the owning teacher may update this assignment.")

    payload = AssignmentFileUploadPayload(files=[])
    if metadata_json:
        try:
            payload = AssignmentFileUploadPayload.model_validate_json(metadata_json)
        except Exception:
            raise HTTPException(status_code=400, detail="metadata_json must be a valid JSON array of file metadata")

    created_records = []
    for index, uploaded_file in enumerate(files):
        metadata = payload.files[index] if index < len(payload.files) else AssignmentFileCreate()
        filename = metadata.file_name or uploaded_file.filename or f"file_{index + 1}"
        inferred_type = (metadata.file_type or "").lower() or (uploaded_file.content_type or "file")
        if inferred_type.startswith("image/") or inferred_type in {"image", "jpg", "jpeg", "png", "webp", "gif"}:
            file_type = "image"
        elif inferred_type == "application/pdf" or filename.lower().endswith(".pdf"):
            file_type = "pdf"
        else:
            file_type = inferred_type or "file"

        if metadata.usage and metadata.usage.lower() in {"key_point_image", "key_point"}:
            usage = metadata.usage.lower()
        else:
            usage = "subchapter_file"

        # Capture size BEFORE uploading to S3 — the upload consumes the stream
        file_size = _get_upload_file_size(uploaded_file)

        if file_type == "pdf":
            url = upload_multipart_file_to_s3(uploaded_file, f"assignments/teacher-{current_user.id}/files", max_size=10 * 1024 * 1024)
            record = AssignmentPDF(
                assignment_id=assignment.id,
                url=url,
                file_name=filename,
                file_type=file_type,
                usage=usage,
                sub_chapter_name=metadata.sub_chapter_name,
                step_number=metadata.step_number,
                file_size_bytes=file_size,
                s3_key=f"assignments/{assignment.id}/{filename}",
            )
            db.add(record)
            created_records.append(record)
        else:
            url = upload_multipart_file_to_s3(uploaded_file, f"assignments/teacher-{current_user.id}/files", max_size=10 * 1024 * 1024)
            record = AssignmentImage(
                assignment_id=assignment.id,
                url=url,
                file_name=filename,
                file_type=file_type,
                usage=usage,
                sub_chapter_name=metadata.sub_chapter_name,
                step_number=metadata.step_number,
                file_size_bytes=file_size,
                s3_key=f"assignments/{assignment.id}/{filename}",
            )
            db.add(record)
            created_records.append(record)

        _update_assignment_file_stats(assignment, file_size)


    db.commit()
    for record in created_records:
        db.refresh(record)

    return created_records


@router.delete(
    "/assignments/{assignment_id}/files/{file_id}",
    summary="Delete Assignment File",
    tags=["Assignments"],
)
def delete_assignment_file(
    assignment_id: int,
    file_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    **Delete a file (image or PDF) from an assignment.**

    - Removes the file record from the database.
    - Subtracts the file's size from `total_file_size_bytes`.
    - Decrements `total_file_count` by 1.
    - Only the assignment owner (teacher) can delete files.
    """
    if current_user.role not in [UserRole.TEACHER, UserRole.SELF_SIGNED_TEACHER]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only teachers may delete assignment files.")

    assignment = db.query(Assignment).filter(Assignment.id == assignment_id).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found.")
    if assignment.created_by_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the owning teacher may delete files from this assignment.")

    # Search in images first, then PDFs
    file_record = db.query(AssignmentImage).filter(
        AssignmentImage.id == file_id,
        AssignmentImage.assignment_id == assignment_id,
    ).first()

    if not file_record:
        file_record = db.query(AssignmentPDF).filter(
            AssignmentPDF.id == file_id,
            AssignmentPDF.assignment_id == assignment_id,
        ).first()

    if not file_record:
        raise HTTPException(status_code=404, detail="File not found on this assignment.")

    # Subtract size and count from assignment stats
    removed_size = int(file_record.file_size_bytes or 0)
    assignment.total_file_size_bytes = max(0, (assignment.total_file_size_bytes or 0) - removed_size)
    assignment.total_file_count = max(0, (assignment.total_file_count or 1) - 1)

    db.delete(file_record)
    db.commit()

    return {
        "detail": "File deleted successfully.",
        "file_id": file_id,
        "assignment_id": assignment_id,
        "removed_bytes": removed_size,
        "total_file_size_bytes": assignment.total_file_size_bytes,
        "total_file_count": assignment.total_file_count,
    }


@router.get("/assignments/me", response_model=List[AssignmentResponse], summary="Get My Assignments", tags=["Assignments"])
def get_my_assignments_list(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    **Get all assignments created by the logged-in teacher.**

    - Returns all assignments regardless of status (draft, published, etc.).
    - Ordered by creation date descending (newest first).
    - Only accessible by teachers.
    """
    if current_user.role not in [UserRole.TEACHER, UserRole.SELF_SIGNED_TEACHER]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only teachers may access their assignments.")

    assignments = (
        db.query(Assignment)
        .filter(Assignment.created_by_user_id == current_user.id)
        .order_by(Assignment.created_at.desc())
        .all()
    )

    results = []
    for a in assignments:
        response = AssignmentResponse.model_validate(a)
        response.file_usage = _build_assignment_file_usage_summary(a)
        results.append(response)
    return results


@router.patch("/assignments/{assignment_id}", response_model=AssignmentResponse, summary="Update Assignment", tags=["Assignments"])
def update_assignment(
    assignment_id: int,
    data: AssignmentPatchBody,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    **Partially update an assignment.**

    - Only the fields provided will be updated (all fields are optional).
    - Updatable fields: `title`, `status`, `tuition_setup_id`, `tuition_date`.
    - Setting `status` to `published` will also record the `published_at` timestamp.
    - Only the assignment owner (teacher) can update.
    """
    if current_user.role not in [UserRole.TEACHER, UserRole.SELF_SIGNED_TEACHER]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only teachers may edit assignments.")

    assignment = db.query(Assignment).filter(Assignment.id == assignment_id).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found.")
    if assignment.created_by_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the owning teacher may update this assignment.")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if value is not None:
            setattr(assignment, field, value)

    # Record published_at timestamp when status becomes published
    if data.status == AssignmentStatus.PUBLISHED and not assignment.published_at:
        assignment.published_at = datetime.utcnow()

    db.commit()
    db.refresh(assignment)
    response = AssignmentResponse.model_validate(assignment)
    response.file_usage = _build_assignment_file_usage_summary(assignment)
    return response


@router.get("/assignments/{assignment_id}", response_model=AssignmentResponse, summary="Get Assignment Details", tags=["Assignments"])
def get_assignment(
    assignment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    **Get full details of a single assignment.**

    - The assignment owner can view it in any status.
    - Other users can only view published assignments.
    """
    assignment = db.query(Assignment).filter(Assignment.id == assignment_id).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found.")

    if current_user.id != assignment.created_by_user_id and assignment.status != AssignmentStatus.PUBLISHED:
        raise HTTPException(status_code=403, detail="Assignment is not visible.")

    # Backfill teacher ID from user ID for legacy assignments
    if assignment.created_by_teacher_id is None and assignment.created_by_user_id is not None:
        teacher = db.query(Teacher).filter(Teacher.user_id == assignment.created_by_user_id).first()
        if teacher:
            assignment.created_by_teacher_id = teacher.id
            if not assignment.teacher_name:
                assignment.teacher_name = f"{teacher.first_name} {teacher.last_name}".strip()
            if not assignment.school_name and teacher.school is not None:
                assignment.school_name = teacher.school.school_name
            if not assignment.school_address and teacher.school is not None:
                assignment.school_address = assignment.school_address or ", ".join(filter(None, [
                    teacher.school.school_location,
                    teacher.school.district,
                    teacher.school.state,
                    teacher.school.pin_code,
                ]))

    if assignment.created_by_self_signed_teacher_id is None and assignment.created_by_user_id is not None:
        self_signed_teacher = db.query(SelfSignedTeacher).filter(SelfSignedTeacher.user_id == assignment.created_by_user_id).first()
        if self_signed_teacher:
            assignment.created_by_self_signed_teacher_id = self_signed_teacher.id
            if not assignment.teacher_name:
                assignment.teacher_name = f"{self_signed_teacher.first_name} {self_signed_teacher.last_name}".strip()

    # Add creator favorite count to assignment response payload
    creator_teacher_id = assignment.created_by_teacher_id or assignment.created_by_self_signed_teacher_id
    if creator_teacher_id is not None:
        creator_type = "teacher" if assignment.created_by_teacher_id is not None else "self_signed_teacher"
        assignment.creator_favorite_count = _get_favorite_teacher_count(db, str(creator_teacher_id), creator_type)
    else:
        assignment.creator_favorite_count = 0

    response = AssignmentResponse.model_validate(assignment)
    response.file_usage = _build_assignment_file_usage_summary(assignment)
    return response


@router.post("/assignments/{assignment_id}/publish", response_model=PublishConfigurationResponse)
def publish_assignment(
    assignment_id: int,
    data: PublishConfigurationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    assignment = db.query(Assignment).filter(Assignment.id == assignment_id).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found.")
    if assignment.created_by_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the owner can publish this assignment.")

    if not data.improvement_categories:
        raise HTTPException(status_code=400, detail="At least one improvement category is required to publish.")
    if not data.assignment_type:
        raise HTTPException(status_code=400, detail="Assignment type is required to publish.")

    if not assignment.questions:
        raise HTTPException(status_code=400, detail="Assignment must contain at least one question before publishing.")

    publish = db.query(PublishConfiguration).filter(PublishConfiguration.assignment_id == assignment.id).first()
    if not publish:
        # Serialize improvement_categories to JSON if needed
        publish_data = data.model_dump()
        if isinstance(publish_data.get("improvement_categories"), list):
            publish_data["improvement_categories"] = json.dumps([cat.value if hasattr(cat, 'value') else cat for cat in publish_data["improvement_categories"]])
        publish = PublishConfiguration(assignment_id=assignment.id, **publish_data)
        db.add(publish)
    else:
        for field, value in data.model_dump(exclude_unset=True).items():
            if field == "improvement_categories" and isinstance(value, list):
                value = json.dumps([cat.value if hasattr(cat, 'value') else cat for cat in value])
            setattr(publish, field, value)

    assignment.status = AssignmentStatus.PUBLISHED
    assignment.published_at = datetime.utcnow()
    db.commit()
    db.refresh(publish)
    return publish


@router.post("/assignments/{assignment_id}/unpublish")
def unpublish_assignment(
    assignment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    assignment = db.query(Assignment).filter(Assignment.id == assignment_id).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found.")
    if assignment.created_by_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the owner can unpublish this assignment.")

    assignment.status = AssignmentStatus.UNPUBLISHED
    db.commit()
    return {"detail": "Assignment unpublished."}


@router.get("/students/{student_id}/assignments")
def list_student_assignments(
    student_id: int,
    board: str | None = Query(None),
    class_name: str | None = Query(None),
    subject: str | None = Query(None),
    teacher_id: int | None = Query(None),
    school_name: str | None = Query(None),
    chapter_number: int | None = Query(None),
    appeared: str | None = Query(None),
    sort: str | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in [UserRole.STUDENT, UserRole.SELF_SIGNED_STUDENT]:
        raise HTTPException(status_code=403, detail="Only students may view student assignments.")

    student = _get_student_for_user(db, current_user)
    if not student:
        raise HTTPException(status_code=404, detail="Student profile not found.")
    if student.id != student_id:
        raise HTTPException(status_code=403, detail="Cannot view assignments for another student.")

    query = db.query(Assignment).filter(Assignment.status == AssignmentStatus.PUBLISHED)
    if board:
        query = query.filter(Assignment.board == board)
    if class_name:
        query = query.filter(Assignment.class_name == class_name)
    if subject:
        query = query.filter(Assignment.subject == subject)
    if teacher_id:
        query = query.filter(Assignment.created_by_user_id == teacher_id)
    if school_name:
        query = query.filter(Assignment.school_name == school_name)
    if chapter_number:
        query = query.filter(Assignment.chapter_number == chapter_number)

    assignments = query.order_by(Assignment.published_at.desc()).all()
    return assignments


@router.get("/teachers/{teacher_id}/profile", response_model=TeacherProfileResponse)
def get_teacher_profile(
    teacher_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    teacher_user = db.query(User).filter(User.id == teacher_id, User.role.in_([UserRole.TEACHER, UserRole.SELF_SIGNED_TEACHER])).first()
    teacher_obj = None

    if teacher_user:
        teacher_obj = _get_teacher_for_user(db, teacher_user)

    if not teacher_obj:
        teacher_obj = db.query(Teacher).filter(Teacher.id == teacher_id).first()
        if teacher_obj:
            teacher_user = teacher_obj.user

    if not teacher_obj and teacher_id.isdigit():
        self_signed_teacher = db.query(SelfSignedTeacher).filter(SelfSignedTeacher.id == int(teacher_id)).first()
        if self_signed_teacher:
            teacher_obj = self_signed_teacher
            teacher_user = self_signed_teacher.user

    if not teacher_obj:
        raise HTTPException(status_code=404, detail="Teacher not found.")

    stats = _compute_teacher_stats(db, teacher_obj)
    school_info = {
        "school_name": None,
        "school_address": None,
    }
    if isinstance(teacher_obj, Teacher) and hasattr(teacher_obj, "school") and teacher_obj.school:
        school_info["school_name"] = teacher_obj.school.name
        school_info["school_address"] = ", ".join(filter(None, [
            teacher_obj.school.address,
            teacher_obj.school.city,
            teacher_obj.school.state,
        ]))
    elif isinstance(teacher_obj, SelfSignedTeacher):
        school_info = _build_self_signed_teacher_school_info(teacher_obj)

    # Compute rating aggregates from persisted TeacherRating rows to ensure correctness
    rating_stats = (
        db.query(func.count(TeacherRating.id).label("rating_count"), func.avg(TeacherRating.rating).label("average_rating"))
        .filter(TeacherRating.teacher_user_id == (teacher_user.id if teacher_user is not None else None))
        .first()
    )

    rating_count = int(rating_stats.rating_count or 0) if rating_stats else 0
    average_rating = float(round(rating_stats.average_rating, 2)) if rating_stats and rating_stats.average_rating is not None else 0.0

    return {
        "teacher_id": int(teacher_id) if teacher_id.isdigit() else teacher_id,
        "teacher_name": f"{teacher_obj.first_name} {teacher_obj.last_name}",
        "school_name": school_info["school_name"],
        "school_address": school_info["school_address"],
        "average_rating": average_rating,
        "rating_count": rating_count,
        "total_exams_count": stats["total_exams_count"],
        "total_assignments_count": stats["total_assignments_count"],
        "total_participants_count": stats["total_participants_count"],
    }


@router.post("/teachers/{teacher_id}/ratings")
def rate_teacher(
    teacher_id: int,
    data: TeacherRatingCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in [UserRole.STUDENT, UserRole.SELF_SIGNED_STUDENT]:
        raise HTTPException(status_code=403, detail="Only students may rate teachers.")

    # Resolve teacher identifier: accept User.id (for school teachers), Teacher.id (string), or SelfSignedTeacher.id (int)
    teacher_user = db.query(User).filter(User.id == teacher_id, User.role.in_([UserRole.TEACHER, UserRole.SELF_SIGNED_TEACHER])).first()
    teacher_obj = None
    if teacher_user:
        # teacher_user found (user-based teacher)
        teacher_obj = _get_teacher_for_user(db, teacher_user)

    if not teacher_obj:
        # Try resolving by Teacher.id (string primary key)
        teacher_obj = db.query(Teacher).filter(Teacher.id == str(teacher_id)).first()
        if teacher_obj:
            teacher_user = teacher_obj.user

    if not teacher_obj and str(teacher_id).isdigit():
        # Try self-signed teacher by numeric id
        self_signed_teacher = db.query(SelfSignedTeacher).filter(SelfSignedTeacher.id == int(teacher_id)).first()
        if self_signed_teacher:
            teacher_obj = self_signed_teacher
            teacher_user = self_signed_teacher.user

    if not teacher_obj and not teacher_user:
        raise HTTPException(status_code=404, detail="Teacher not found.")

    # Ensure the teacher has a linked `User` to attach the rating to
    if not teacher_user:
        raise HTTPException(status_code=400, detail="This teacher cannot be rated (no linked user account).")

    # Create or update a single rating per student per teacher (last rating wins)
    rating = db.query(TeacherRating).filter(TeacherRating.teacher_user_id == teacher_user.id, TeacherRating.student_user_id == current_user.id).first()
    if not rating:
        rating = TeacherRating(teacher_user_id=teacher_user.id, student_user_id=current_user.id, rating=data.rating)
        db.add(rating)
    else:
        rating.rating = data.rating

    db.commit()

    # Recompute aggregates from TeacherRating rows
    rating_stats = (
        db.query(func.count(TeacherRating.id).label("rating_count"), func.avg(TeacherRating.rating).label("average_rating"))
        .filter(TeacherRating.teacher_user_id == teacher_user.id)
        .first()
    )

    if rating_stats:
        count = int(rating_stats.rating_count or 0)
        avg = float(rating_stats.average_rating) if rating_stats.average_rating is not None else 0.0

        # Persist aggregates to school Teacher model if applicable
        if isinstance(teacher_obj, Teacher):
            teacher_obj.avg_rating = avg
            teacher_obj.rating_count = count
            db.commit()
        # For SelfSignedTeacher we currently do not persist avg/count columns; they will be computed on read

    return {"detail": "Rating submitted successfully."}


@router.post("/assignments/{assignment_id}/attempts")
def submit_assignment_attempt(
    assignment_id: int,
    data: StudentAssignmentAttemptCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in [UserRole.STUDENT, UserRole.SELF_SIGNED_STUDENT]:
        raise HTTPException(status_code=403, detail="Only students may submit assignment attempts.")

    assignment = db.query(Assignment).filter(Assignment.id == assignment_id, Assignment.status == AssignmentStatus.PUBLISHED).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found or not published.")

    # Enforce per-teacher daily doubt limit (max 10 doubts per teacher per UTC day)
    try:
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow_start = today_start + timedelta(days=1)

        # Count doubts for school teacher owner if present
        if getattr(assignment, "created_by_teacher_id", None):
            owner_tid = assignment.created_by_teacher_id
            doubts_today = (
                db.query(func.count(AssignmentDoubt.id))
                .join(Assignment, Assignment.id == AssignmentDoubt.assignment_id)
                .filter(Assignment.created_by_teacher_id == owner_tid)
                .filter(AssignmentDoubt.created_at >= today_start)
                .filter(AssignmentDoubt.created_at < tomorrow_start)
                .scalar()
            ) or 0
            if doubts_today >= 10:
                raise HTTPException(status_code=403, detail="This teacher has reached the daily doubt limit (10). Please try again tomorrow.")

        # Count doubts for self-signed teacher owner if present
        if getattr(assignment, "created_by_self_signed_teacher_id", None):
            owner_sid = assignment.created_by_self_signed_teacher_id
            doubts_today = (
                db.query(func.count(AssignmentDoubt.id))
                .join(Assignment, Assignment.id == AssignmentDoubt.assignment_id)
                .filter(Assignment.created_by_self_signed_teacher_id == owner_sid)
                .filter(AssignmentDoubt.created_at >= today_start)
                .filter(AssignmentDoubt.created_at < tomorrow_start)
                .scalar()
            ) or 0
            if doubts_today >= 10:
                raise HTTPException(status_code=403, detail="This self-signed teacher has reached the daily doubt limit (10). Please try again tomorrow.")
    except Exception:
        # Fail-open: if quota check fails for any reason, allow the doubt to be created
        pass

    attempt_count = db.query(func.count(StudentAssignmentAttempt.id)).filter(StudentAssignmentAttempt.assignment_id == assignment_id, StudentAssignmentAttempt.student_user_id == current_user.id).scalar() or 0
    if attempt_count >= 3:
        raise HTTPException(status_code=400, detail="Maximum 3 attempts allowed.")

    attempt = StudentAssignmentAttempt(
        student_user_id=current_user.id,
        assignment_id=assignment_id,
        attempt_number=attempt_count + 1,
        submitted_answers=json.dumps(data.submitted_answers),
        score=data.score,
        time_taken_seconds=data.time_taken_seconds,
    )
    db.add(attempt)
    db.commit()
    db.refresh(attempt)
    return attempt


@router.post("/assignments/{assignment_id}/feedback")
def assignment_feedback(
    assignment_id: int,
    data: ChapterFeedbackCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in [UserRole.STUDENT, UserRole.SELF_SIGNED_STUDENT]:
        raise HTTPException(status_code=403, detail="Only students may submit feedback.")

    assignment = db.query(Assignment).filter(Assignment.id == assignment_id, Assignment.status == AssignmentStatus.PUBLISHED).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found or not published.")

    feedback = db.query(ChapterFeedback).filter(ChapterFeedback.assignment_id == assignment_id, ChapterFeedback.student_user_id == current_user.id).first()
    if not feedback:
        feedback = ChapterFeedback(assignment_id=assignment_id, student_user_id=current_user.id, is_helpful=data.is_helpful)
        db.add(feedback)
    else:
        feedback.is_helpful = data.is_helpful

    db.commit()
    return {"detail": "Feedback submitted."}


@router.post("/assignments/{assignment_id}/doubts", response_model=AssignmentDoubtResponse)
def submit_assignment_doubt(
    assignment_id: int,
    data: AssignmentDoubtCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in [UserRole.STUDENT, UserRole.SELF_SIGNED_STUDENT]:
        raise HTTPException(status_code=403, detail="Only students may submit doubts.")

    assignment = db.query(Assignment).filter(Assignment.id == assignment_id, Assignment.status == AssignmentStatus.PUBLISHED).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found or not published.")

    # Determine if it's a regular student or self-signed student
    student_user_id = current_user.id if current_user.role == UserRole.STUDENT else None
    self_signed_student_id = current_user.id if current_user.role == UserRole.SELF_SIGNED_STUDENT else None

    question_id = None
    if data.question_id is not None:
        question = db.query(AssignmentQuestion).filter(
            AssignmentQuestion.id == data.question_id,
            AssignmentQuestion.assignment_id == assignment_id,
        ).first()
        if question:
            question_id = data.question_id

    existing_doubt = _get_existing_student_doubt(
        db,
        assignment_id,
        student_user_id=student_user_id,
        self_signed_student_id=self_signed_student_id,
    )

    if existing_doubt is not None:
        if existing_doubt.question_id is None and question_id is not None:
            existing_doubt.question_id = question_id
        existing_doubt.status = DoubtStatus.OPEN
        existing_doubt.resolved_at = None

        reply = DoubtReply(
            doubt_id=existing_doubt.id,
            reply_text=data.doubt_text,
        )
        db.add(reply)
        db.commit()
        db.refresh(existing_doubt)
        return _serialize_doubt_response(db, existing_doubt)

    doubt_payload = {
        "assignment_id": assignment_id,
        "student_user_id": student_user_id,
        "self_signed_student_id": self_signed_student_id,
        "doubt_text": data.doubt_text,
        "question_id": question_id,
        "status": DoubtStatus.OPEN,
    }
    doubt = AssignmentDoubt(**doubt_payload)
    db.add(doubt)
    db.commit()
    db.refresh(doubt)

    return _serialize_doubt_response(db, doubt)


@router.get("/assignments/{assignment_id}/doubts", response_model=List[AssignmentDoubtResponse])
def get_assignment_doubts(
    assignment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    assignment = db.query(Assignment).filter(Assignment.id == assignment_id, Assignment.status == AssignmentStatus.PUBLISHED).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found or not published.")

    # Only the owner of the assignment or the student who created the doubt, or an admin can view doubts.
    # For simplicity, allowing all roles to view published assignment doubts as per user story. 
    # A more granular permission system could be implemented here.

    doubts = (
        db.query(AssignmentDoubt)
        .filter(AssignmentDoubt.assignment_id == assignment_id)
        .order_by(AssignmentDoubt.created_at.desc())
        .all()
    )

    seen_students = set()
    unique_doubts = []
    for doubt in doubts:
        identity = (doubt.student_user_id, doubt.self_signed_student_id)
        if identity in seen_students:
            continue
        seen_students.add(identity)
        unique_doubts.append(doubt)

    return [
        _serialize_doubt_response(db, doubt)
        for doubt in unique_doubts
    ]


@router.post("/assignments/doubts/{doubt_id}/reply", response_model=DoubtReplyResponse)
def reply_to_doubt(
    doubt_id: int,
    data: DoubtReplyCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in [UserRole.TEACHER, UserRole.SELF_SIGNED_TEACHER, UserRole.STUDENT, UserRole.SELF_SIGNED_STUDENT]:
        raise HTTPException(status_code=403, detail="Only teachers and the original student may reply to doubts.")

    doubt = db.query(AssignmentDoubt).filter(AssignmentDoubt.id == doubt_id).first()
    if not doubt:
        raise HTTPException(status_code=404, detail="Doubt not found.")

    teacher_user_id = None
    self_signed_teacher_id = None

    if current_user.role == UserRole.TEACHER:
        teacher_user_id = current_user.id
    elif current_user.role == UserRole.SELF_SIGNED_TEACHER:
        self_signed_teacher_id = current_user.id
    elif current_user.role == UserRole.STUDENT:
        if doubt.student_user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Students may only reply to their own doubts.")
    elif current_user.role == UserRole.SELF_SIGNED_STUDENT:
        if doubt.self_signed_student_id != current_user.id:
            raise HTTPException(status_code=403, detail="Students may only reply to their own doubts.")

    reply_payload = {
        "doubt_id": doubt_id,
        "teacher_user_id": teacher_user_id,
        "self_signed_teacher_id": self_signed_teacher_id,
        "reply_text": data.reply_text,
        "file_url": data.file_url,
        "step_solutions": json.dumps(data.step_solutions) if data.step_solutions is not None else None,
    }
    reply = DoubtReply(**reply_payload)
    db.add(reply)

    # If a student follows up on a resolved thread, reopen it.
    if current_user.role in [UserRole.STUDENT, UserRole.SELF_SIGNED_STUDENT]:
        doubt.status = DoubtStatus.OPEN
        doubt.resolved_at = None

    db.commit()
    db.refresh(reply)
    return reply


def _serialize_attempt(attempt: StudentAssignmentAttempt) -> dict:
    student_name = None
    if attempt.student_user is not None:
        student_name = attempt.student_user.name
    elif getattr(attempt, 'student_user_id', None) is not None:
        student = attempt.student_user
        if student is not None:
            student_name = student.name

    return {
        "id": attempt.id,
        "student_user_id": attempt.student_user_id,
        "assignment_id": attempt.assignment_id,
        "attempt_number": attempt.attempt_number,
        "submitted_answers": json.loads(attempt.submitted_answers) if attempt.submitted_answers else {},
        "score": attempt.score,
        "time_taken_seconds": attempt.time_taken_seconds,
        "submission_date": attempt.submission_date,
        "student_name": student_name,
    }


@router.get("/assignments/attempts/history", response_model=List[StudentAssignmentAttemptResponse])
def get_my_attempts_history(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in [UserRole.STUDENT, UserRole.SELF_SIGNED_STUDENT]:
        raise HTTPException(status_code=403, detail="Only students may view attempt history.")

    attempts = (
        db.query(StudentAssignmentAttempt)
        .filter(StudentAssignmentAttempt.student_user_id == current_user.id)
        .order_by(StudentAssignmentAttempt.submission_date.desc())
        .all()
    )
    return [_serialize_attempt(attempt) for attempt in attempts]


@router.get("/assignments/{assignment_id}/my-results")
def get_my_results(
    assignment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in [UserRole.STUDENT, UserRole.SELF_SIGNED_STUDENT]:
        raise HTTPException(status_code=403, detail="Only students may view their results.")

    assignment = db.query(Assignment).filter(Assignment.id == assignment_id).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found.")

    attempt = (
        db.query(StudentAssignmentAttempt)
        .filter(StudentAssignmentAttempt.assignment_id == assignment_id, StudentAssignmentAttempt.student_user_id == current_user.id)
        .order_by(StudentAssignmentAttempt.submission_date.desc())
        .first()
    )
    if not attempt:
        return {"detail": "No attempts found."}

    # Parse submitted answers
    try:
        submitted = json.loads(attempt.submitted_answers) if attempt.submitted_answers else {}
    except Exception:
        submitted = {}

    # Build question maps
    q_by_id = {q.id: q.correct_option for q in assignment.questions} if assignment.questions else {}
    q_by_number = {q.question_number: q.correct_option for q in assignment.questions} if assignment.questions else {}

    correct = 0
    incorrect = 0
    for key, ans in (submitted or {}).items():
        matched = False
        # try numeric key
        try:
            ik = int(key)
        except Exception:
            ik = None
        if ik is not None and ik in q_by_id:
            matched = True
            if str(ans).strip().upper() == str(q_by_id[ik]).strip().upper():
                correct += 1
            else:
                incorrect += 1
        else:
            # try question number match
            try:
                num = int(''.join(filter(str.isdigit, str(key)))) if any(c.isdigit() for c in str(key)) else None
            except Exception:
                num = None
            if num is not None and num in q_by_number:
                matched = True
                if str(ans).strip().upper() == str(q_by_number[num]).strip().upper():
                    correct += 1
                else:
                    incorrect += 1

    total_questions = len(assignment.questions) if assignment.questions else max(correct + incorrect, 0)
    percentage = round((correct / total_questions) * 100, 2) if total_questions > 0 else 0.0

    return {
        "assignment_id": assignment_id,
        "attempt_number": attempt.attempt_number,
        "score": attempt.score,
        "time_taken_seconds": attempt.time_taken_seconds,
        "correct": correct,
        "incorrect": incorrect,
        "total_questions": total_questions,
        "percentage": percentage,
        "submission_date": attempt.submission_date,
    }


@router.get("/assignments/{assignment_id}/attempts", response_model=List[StudentAssignmentAttemptResponse])
def list_assignment_attempts_for_teacher(
    assignment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in [UserRole.TEACHER, UserRole.SELF_SIGNED_TEACHER]:
        raise HTTPException(status_code=403, detail="Only teachers may view all attempts for an assignment.")

    assignment = db.query(Assignment).filter(Assignment.id == assignment_id).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found.")

    # Ownership check: teacher must be the creator
    owner_ok = False
    if assignment.created_by_user_id == current_user.id:
        owner_ok = True
    if current_user.role == UserRole.SELF_SIGNED_TEACHER and assignment.created_by_self_signed_teacher_id == current_user.id:
        owner_ok = True
    if not owner_ok:
        raise HTTPException(status_code=403, detail="Not authorized to view attempts for this assignment.")

    attempts = db.query(StudentAssignmentAttempt).filter(StudentAssignmentAttempt.assignment_id == assignment_id).order_by(StudentAssignmentAttempt.submission_date.desc()).all()
    return [_serialize_attempt(attempt) for attempt in attempts]


@router.post("/assignments/{assignment_id}/report", response_model=AssignmentReportResponse)
def report_assignment_issue(
    assignment_id: int,
    data: AssignmentReportCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in [UserRole.STUDENT, UserRole.SELF_SIGNED_STUDENT]:
        raise HTTPException(status_code=403, detail="Only students may report assignment issues.")

    assignment = db.query(Assignment).filter(Assignment.id == assignment_id).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found.")

    report = AssignmentReport(
        assignment_id=assignment_id,
        student_user_id=current_user.id if current_user.role == UserRole.STUDENT else None,
        self_signed_student_id=current_user.id if current_user.role == UserRole.SELF_SIGNED_STUDENT else None,
        category=data.category,
        reason=data.reason,
        comment=data.comment,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


@router.get("/assignments/{assignment_id}/reports", response_model=List[AssignmentReportResponse])
def get_assignment_reports(
    assignment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
):
    """Get reports for a specific assignment.

    - Admins and superadmins can view any assignment reports.
    - Teachers can view reports for assignments they created.
    """
    if current_user.role in [UserRole.SUPERADMIN, UserRole.ADMIN]:
        pass
    elif current_user.role in [UserRole.TEACHER, UserRole.SELF_SIGNED_TEACHER]:
        assignment = db.query(Assignment).filter(Assignment.id == assignment_id).first()
        if not assignment:
            raise HTTPException(status_code=404, detail="Assignment not found.")
        owner_ok = False
        if assignment.created_by_user_id == current_user.id:
            owner_ok = True
        if current_user.role == UserRole.SELF_SIGNED_TEACHER and assignment.created_by_self_signed_teacher_id == current_user.id:
            owner_ok = True
        if not owner_ok:
            raise HTTPException(status_code=403, detail="Not authorized to view reports for this assignment.")
    else:
        raise HTTPException(status_code=403, detail="Not authorized to view reports.")

    reports = (
        db.query(AssignmentReport)
        .filter(AssignmentReport.assignment_id == assignment_id)
        .order_by(AssignmentReport.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return reports


@router.get("/assignments/reports")
def list_reports_admin(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    assignment_id: int | None = Query(None),
    status: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
):
    """Admin endpoint to list assignment reports with optional filters."""
    if current_user.role not in [UserRole.SUPERADMIN, UserRole.ADMIN]:
        raise HTTPException(status_code=403, detail="Only admins may list reports.")

    q = db.query(AssignmentReport)
    if assignment_id is not None:
        q = q.filter(AssignmentReport.assignment_id == assignment_id)
    if status is not None:
        try:
            from app.models.assignments.assignment import ReportStatus

            q = q.filter(AssignmentReport.status == ReportStatus(status))
        except Exception:
            # If invalid status provided, return empty
            return {"data": [], "total": 0, "skip": skip, "limit": limit}

    total = q.count()
    reports = q.order_by(AssignmentReport.created_at.desc()).offset(skip).limit(limit).all()
    return {"data": reports, "total": total, "skip": skip, "limit": limit}
