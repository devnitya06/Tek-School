from fastapi import APIRouter, Depends, HTTPException, status, Query, Form, UploadFile, File, Request
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, and_
from typing import List, Optional, Dict
from datetime import datetime, timedelta
import json

from app.core.dependencies import get_current_user
from app.schemas.users import UserRole
from app.utils.s3 import upload_multipart_file_to_s3
from app.schemas.assignments.assignment import (
    AssignmentUpdate,
    AssignmentResponse,
    PublishConfigurationCreate,
    PublishConfigurationResponse,
    StudentAssignmentAttemptCreate,
    TeacherRatingCreate,
    ChapterFeedbackCreate,
    AssignmentDoubtCreate,
    AssignmentDoubtResponse,
    DoubtReplyCreate,
    DoubtReplyResponse,
    StudentAssignmentAttemptResponse,
    AssignmentReportCreate,
    AssignmentReportResponse,
    TeacherProfileResponse,
    FavoriteTeacherCreate,
    FavoriteTeacherResponse,
    FavoriteTeacherListResponse,
)
from app.models.assignments.assignment import (
    Assignment,
    AssignmentQuestion,
    AssignmentKeyPoint,
    AssignmentImage,
    AssignmentPDF,
    AssignmentVideoLink,
    PublishConfiguration,
    StudentAssignmentAttempt,
    ChapterFeedback,
    TeacherRating,
    DoubtStatus,
    AssignmentStatus,
    StudentAssignmentProgress,
    AssignmentDoubt,
    DoubtReply,
    AssignmentReport,
    FavoriteTeacher,
)
from app.models.users import User
from app.models.teachers import Teacher, SelfSignedTeacher, SelfSignedTeacherTeachingConfiguration, TeacherClassSectionSubject
from app.models.students import Student, SelfSignedStudent
from app.models.school import Class, Subject
from app.models.admin import SchoolClassSubject
from app.db.session import get_db

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


def _get_teacher_display_name(db: Session, teacher_id: str, teacher_type: str) -> Optional[str]:
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

    # Query assignments: published (and treat as active) and matching board/class/subject
    assignments = (
        db.query(Assignment)
        .filter(Assignment.status == AssignmentStatus.PUBLISHED)
        .filter(func.lower(func.coalesce(func.nullif(Assignment.board, ''), Assignment.board)) == b)
        .filter(func.lower(Assignment.class_name) == c)
        .filter(func.lower(Assignment.subject) == s)
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
    if current_user.role in [UserRole.TEACHER, UserRole.SELF_SIGNED_TEACHER]:
        teacher_obj = _get_teacher_for_user(db, current_user)
        if not teacher_obj:
            raise HTTPException(status_code=404, detail="Teacher profile not found.")

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

        class_group = None
        if getattr(student_obj, "select_class_id", None):
            class_group = db.query(SchoolClassSubject).filter(SchoolClassSubject.id == student_obj.select_class_id).first()

        if not class_group:
            return {"data": []}

        board_value = str(class_group.school_board.value if hasattr(class_group.school_board, 'value') else class_group.school_board)
        allowed_board_values = {board_value.lower()} if board_value else set()
        class_names_by_board = {board_value or "": {class_group.class_name}} if class_group.class_name else {}
        subject_names_by_class = {class_group.class_name: {class_group.subject}} if class_group.class_name and class_group.subject else {}

    else:
        raise HTTPException(status_code=403, detail="Only teachers and students may access this resource.")

    # Build base filter for published assignments
    base_filter = Assignment.status == AssignmentStatus.PUBLISHED

    # Aggregate totals grouped by board, class_name, subject
    agg_query = (
        db.query(
            func.coalesce(func.nullif(Assignment.board, ''), Assignment.board).label('board'),
            Assignment.class_name.label('class_name'),
            Assignment.subject.label('subject'),
            func.count(Assignment.id).label('total'),
        )
        .filter(base_filter)
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

    # Aggregate created_by_me counts
    me_query = (
        db.query(
            func.coalesce(func.nullif(Assignment.board, ''), Assignment.board).label('board'),
            Assignment.class_name.label('class_name'),
            Assignment.subject.label('subject'),
            func.count(Assignment.id).label('created_by_me'),
        )
        .filter(base_filter)
    )

    if allowed_board_values:
        me_query = me_query.filter(func.lower(Assignment.board).in_(list(allowed_board_values)))

    if class_conds and subject_conds:
        me_query = me_query.filter(and_(*class_conds), and_(*subject_conds))
    elif class_conds:
        me_query = me_query.filter(and_(*class_conds))
    elif subject_conds:
        me_query = me_query.filter(and_(*subject_conds))

    # created by me conditions: count only assignments where created_by_user_id == current_user.id
    # This avoids ambiguity with other creator fields and matches user's expectation
    created_cond = Assignment.created_by_user_id == current_user.id

    if created_cond is not False:
        me_query = me_query.filter(created_cond)
        me_query = me_query.group_by(Assignment.board, Assignment.class_name, Assignment.subject)
        # Normalize keys to avoid case/whitespace mismatches between queries
        me_counts = {}
        for r in me_query.all():
            kb = (r.board or '').strip().lower()
            kc = (r.class_name or '').strip().lower()
            ks = (r.subject or '').strip().lower()
            me_counts[(kb, kc, ks)] = r.created_by_me
    else:
        me_counts = {}

    # Build response grouped as Board -> Class -> Subjects
    response_map = {}
    for r in totals:
        board_key = r.board or ''
        class_key = r.class_name or ''
        subj_key = r.subject or ''
        subject_entry = {
            "subject_name": subj_key,
            "total_assignments": int(r.total or 0),
        }
        if current_user.role in [UserRole.TEACHER, UserRole.SELF_SIGNED_TEACHER]:
            lookup_key = ((r.board or '').strip().lower(), (r.class_name or '').strip().lower(), (r.subject or '').strip().lower())
            subject_entry["created_by_me"] = int(me_counts.get(lookup_key, 0) or 0)

        response_map.setdefault(board_key, {}).setdefault(class_key, []).append(subject_entry)

    # Convert to list form matching example
    data = []
    for board_name, classes in response_map.items():
        for class_name, subjects in classes.items():
            data.append({
                "board_name": board_name,
                "class_name": class_name,
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
    board: Optional[str] = Query(None),
    medium: Optional[str] = Query(None),
    class_name: Optional[str] = Query(None),
    class_id: Optional[int] = Query(None),
    subject: Optional[str] = Query(None),
    subject_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None, description="Filter by status: 'published' or 'unpublished' (defaults to both)"),
    chapter_number: Optional[int] = Query(None),
    teacher_id: Optional[int] = Query(None),
    school_name: Optional[str] = Query(None),
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
    if not assignment.topic_title:
        count += 1
    if not assignment.original_content:
        count += 1
    if not assignment.summarized_content:
        count += 1
    if not assignment.key_points:
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


def _validate_video_urls(video_urls: Optional[List[str]]) -> List[str]:
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


@router.post("/assignments", response_model=AssignmentResponse)
async def create_assignment(
    request: Request,
    assignment_data: str = Form(...),
    images: Optional[List[UploadFile]] = File(None),
    pdfs: Optional[List[UploadFile]] = File(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create assignment with multipart file uploads (images, PDFs, key point images) to S3.
    
    Form fields:
    - assignment_data: JSON string with assignment metadata
    - images: Optional file array (JPG/PNG/WEBP, ≤10MB each)
    - pdfs: Optional file array (PDF only, ≤10MB each)
    - Additional form fields for key point images (e.g., "kp1.jpg", "kp2.png") - optional per key point
    """
    
    if current_user.role not in [UserRole.TEACHER, UserRole.SELF_SIGNED_TEACHER]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only teachers may create assignments.")

    teacher_obj = _get_teacher_for_user(db, current_user)
    if not teacher_obj:
        raise HTTPException(status_code=404, detail="Teacher profile not found.")

    # Parse assignment_data JSON from form field
    try:
        data_dict = json.loads(assignment_data)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid assignment_data JSON")
    if not isinstance(data_dict, dict):
        raise HTTPException(status_code=400, detail="assignment_data must be a JSON object")
    
    # Validate required fields
    required_fields = ["board", "class_name", "subject", "chapter_number", "topic_title"]
    for field in required_fields:
        if field not in data_dict or not data_dict[field]:
            raise HTTPException(status_code=400, detail=f"Missing required field: {field}")

    board_value = str(data_dict.get("board")).strip()
    class_name_value = str(data_dict.get("class_name")).strip()
    subject_value = str(data_dict.get("subject")).strip()
    class_id_value = data_dict.get("class_id")
    subject_id_value = data_dict.get("subject_id")

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
    if "key_points" in data_dict and data_dict["key_points"] is not None and not isinstance(data_dict["key_points"], list):
        raise HTTPException(status_code=400, detail="key_points must be a list")
    if "questions" in data_dict and data_dict["questions"] is not None and not isinstance(data_dict["questions"], list):
        raise HTTPException(status_code=400, detail="questions must be a list")
    
    # Enforce chapter creation constraints:
    # 1) A single user cannot create more than one assignment for the same (board, class_name, chapter_number)
    # 2) Across all creators, a maximum of 10 assignments are allowed for the same (board, class_name, chapter_number)
    try:
        chapter_number_val = int(data_dict.get("chapter_number"))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid chapter_number value")

    kb = board_value.strip().lower()
    kc = class_name_value.strip().lower()

    # Per-user uniqueness check
    existing = (
        db.query(Assignment)
        .filter(func.coalesce(func.nullif(Assignment.board, ''), Assignment.board).ilike(board_value))
        .filter(func.lower(Assignment.class_name) == kc)
        .filter(Assignment.chapter_number == chapter_number_val)
        .filter(Assignment.created_by_user_id == current_user.id)
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="You have already created an assignment for this board/class/chapter number")

    # Global cap per chapter
    total_same_chapter = (
        db.query(func.count(Assignment.id))
        .filter(func.coalesce(func.nullif(Assignment.board, ''), Assignment.board).ilike(board_value))
        .filter(func.lower(Assignment.class_name) == kc)
        .filter(Assignment.chapter_number == chapter_number_val)
        .scalar() or 0
    )
    if total_same_chapter >= 10:
        raise HTTPException(status_code=400, detail="Maximum assignments for this board/class/chapter have been reached (10)")
    
    # Get all form data to find key point image files
    form_data = await request.form()
    kp_image_files: Dict[str, UploadFile] = {}
    
    # Extract key point image files (anything not in the known fields)
    known_fields = {"assignment_data", "images", "pdfs"}
    for field_name in form_data.keys():
        if field_name not in known_fields:
            file_item = form_data[field_name]
            if isinstance(file_item, UploadFile):
                kp_image_files[field_name] = file_item
    
    # Upload images to S3 and collect URLs
    image_urls = []
    if images:
        for img_file in images:
            if img_file.filename:  # Skip empty uploads
                _validate_image_file(img_file)
                url = upload_multipart_file_to_s3(
                    img_file,
                    f"assignments/teacher-{current_user.id}/images",
                    max_size=10 * 1024 * 1024
                )
                image_urls.append(url)
    
    # Upload PDFs to S3 and collect URLs
    pdf_urls = []
    if pdfs:
        for pdf_file in pdfs:
            if pdf_file.filename:  # Skip empty uploads
                _validate_pdf_file(pdf_file)
                url = upload_multipart_file_to_s3(
                    pdf_file,
                    f"assignments/teacher-{current_user.id}/pdfs",
                    max_size=10 * 1024 * 1024
                )
                pdf_urls.append(url)
    
    # Upload key point images and build a map of filename -> S3 URL
    kp_image_map: Dict[str, str] = {}
    for filename, kp_file in kp_image_files.items():
        if kp_file.filename:
            _validate_image_file(kp_file)
            url = upload_multipart_file_to_s3(
                kp_file,
                f"assignments/teacher-{current_user.id}/key-points",
                max_size=10 * 1024 * 1024
            )
            kp_image_map[filename] = url
    
    # Build denormalized teacher/school info
    denorm = _build_teacher_school_denorm(teacher_obj)
    
    # Create assignment record
    assignment_kwargs = {
        "created_by_user_id": current_user.id,
        "status": AssignmentStatus.DRAFT,
        "board": board_value,
        "class_name": class_name_value,
        "subject": subject_value,
        "chapter_number": data_dict.get("chapter_number"),
        "sub_chapter": data_dict.get("sub_chapter"),
        "topic_title": data_dict.get("topic_title"),
        "chapter_tagline": data_dict.get("chapter_tagline"),
        "original_content": data_dict.get("original_content"),
        "summarized_content": data_dict.get("summarized_content"),
        "activity_type": data_dict.get("assignment_type", "Academic"),
        "class_id": class_id_value,
        "subject_id": subject_id_value,
        "teacher_name": denorm["teacher_name"],
        "school_name": denorm["school_name"],
        "school_address": denorm["school_address"],
    }

    if current_user.role == UserRole.TEACHER:
        assignment_kwargs["created_by_teacher_id"] = teacher_obj.id
    elif current_user.role == UserRole.SELF_SIGNED_TEACHER:
        assignment_kwargs["created_by_self_signed_teacher_id"] = teacher_obj.id

    assignment = Assignment(**assignment_kwargs)
    
    # Parse and add key points with optional images
    if data_dict.get("key_points"):
        for kp_data in data_dict["key_points"]:
            key_point = AssignmentKeyPoint(
                step_number=kp_data.get("step_number"),
                text=kp_data.get("text"),
            )
            # If key point references an image file, map it to the S3 URL
            if kp_data.get("image") and kp_data["image"] in kp_image_map:
                key_point.image_url = kp_image_map[kp_data["image"]]
            assignment.key_points.append(key_point)
    
    # Parse and add questions
    if data_dict.get("questions"):
        for q_data in data_dict["questions"]:
            question = AssignmentQuestion(
                question_number=q_data.get("question_number"),
                question_text=q_data.get("question_text"),
                option_a=q_data.get("option_a"),
                option_b=q_data.get("option_b"),
                option_c=q_data.get("option_c"),
                option_d=q_data.get("option_d"),
                correct_option=q_data.get("correct_option"),
                solution_explanation=q_data.get("solution_explanation"),
            )
            assignment.questions.append(question)
    
    # Add image records
    for img_url in image_urls:
        assignment.images.append(AssignmentImage(url=img_url))
    
    # Add PDF records
    for pdf_url in pdf_urls:
        assignment.pdfs.append(AssignmentPDF(url=pdf_url))
    
    # Add video link records
    for video_url in video_urls:
        assignment.video_links.append(AssignmentVideoLink(url=video_url))
    
    # Set publish config fields if provided
    if data_dict.get("assignment_type"):
        assignment.activity_type = data_dict["assignment_type"]
    
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    return assignment


@router.put("/assignments/{assignment_id}", response_model=AssignmentResponse)
def update_assignment(
    assignment_id: int,
    data: AssignmentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in [UserRole.TEACHER, UserRole.SELF_SIGNED_TEACHER]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only teachers may edit assignments.")

    assignment = db.query(Assignment).filter(Assignment.id == assignment_id).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found.")
    if assignment.created_by_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the owning teacher may update this assignment.")
    if assignment.status in (AssignmentStatus.PUBLISHED, AssignmentStatus.UNPUBLISHED):
        raise HTTPException(status_code=400, detail="Published or unpublished assignments cannot be modified directly.")

    # Update scalar fields (exclude nested relationship fields)
    excluded_fields = {"key_points", "questions", "images", "pdfs", "video_links", "media_banners"}
    for field, value in data.model_dump(exclude_unset=True).items():
        if field not in excluded_fields and value is not None:
            setattr(assignment, field, value)

    # Update nested items only if explicitly provided
    if data.key_points is not None:
        db.query(AssignmentKeyPoint).filter(AssignmentKeyPoint.assignment_id == assignment.id).delete()
        new_key_points = [AssignmentKeyPoint(**kp.model_dump()) for kp in data.key_points]
        for kp in new_key_points:
            db.add(kp)
        assignment.key_points = new_key_points

    if data.questions is not None:
        db.query(AssignmentQuestion).filter(AssignmentQuestion.assignment_id == assignment.id).delete()
        new_questions = [AssignmentQuestion(**q.model_dump()) for q in data.questions]
        for q in new_questions:
            db.add(q)
        assignment.questions = new_questions

    db.commit()
    db.refresh(assignment)
    return assignment


@router.get("/assignments/{assignment_id}", response_model=AssignmentResponse)
def get_assignment(
    assignment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
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

    return assignment


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
    board: Optional[str] = Query(None),
    class_name: Optional[str] = Query(None),
    subject: Optional[str] = Query(None),
    teacher_id: Optional[int] = Query(None),
    school_name: Optional[str] = Query(None),
    chapter_number: Optional[int] = Query(None),
    appeared: Optional[str] = Query(None),
    sort: Optional[str] = Query(None),
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
        submitted_answers=data.submitted_answers,
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

    doubt = AssignmentDoubt(
        assignment_id=assignment_id,
        student_user_id=student_user_id,
        self_signed_student_id=self_signed_student_id,
        doubt_text=data.doubt_text,
        doubt_summary=data.doubt_summary,
        question_id=question_id,
        status=DoubtStatus.OPEN,
    )
    db.add(doubt)
    db.commit()
    db.refresh(doubt)
    return doubt


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

    doubts = db.query(AssignmentDoubt).filter(AssignmentDoubt.assignment_id == assignment_id).all()

    return doubts


@router.post("/assignments/doubts/{doubt_id}/reply", response_model=DoubtReplyResponse)
def reply_to_doubt(
    doubt_id: int,
    data: DoubtReplyCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in [UserRole.TEACHER, UserRole.SELF_SIGNED_TEACHER]:
        raise HTTPException(status_code=403, detail="Only teachers may reply to doubts.")

    doubt = db.query(AssignmentDoubt).filter(AssignmentDoubt.id == doubt_id).first()
    if not doubt:
        raise HTTPException(status_code=404, detail="Doubt not found.")

    # Create reply
    teacher_user_id = current_user.id if current_user.role == UserRole.TEACHER else None
    self_signed_teacher_id = current_user.id if current_user.role == UserRole.SELF_SIGNED_TEACHER else None

    reply = DoubtReply(
        doubt_id=doubt_id,
        teacher_user_id=teacher_user_id,
        self_signed_teacher_id=self_signed_teacher_id,
        reply_text=data.reply_text,
        file_url=data.file_url,
        step_solutions=json.dumps(data.step_solutions) if data.step_solutions is not None else None,
    )
    db.add(reply)

    # Mark doubt as resolved
    try:
        doubt.status = DoubtStatus.RESOLVED
        doubt.resolved_at = datetime.utcnow()
    except Exception:
        pass

    db.commit()
    db.refresh(reply)
    return reply


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
    return attempts


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
    return attempts


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
    assignment_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
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
