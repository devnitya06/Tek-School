"""Shared helpers for resolving lesson-plan metadata in a teacher-role-aware way."""

from sqlalchemy.orm import Session

from app.models.admin import SchoolClassSubject
from app.models.school import Subject
from app.models.teachers import SelfSignedTeacherTeachingConfiguration, TeacherClassSectionSubject
from app.schemas.users import UserRole


def _resolve_self_signed_teacher_subject(db: Session, current_user, lesson_plan) -> str | None:
    """Return the subject name for a self-signed teacher, following their teaching configuration."""
    teacher = getattr(current_user, "self_signed_teacher_profile", None)
    if not teacher:
        return getattr(lesson_plan, "subject_name", None)

    configs = (
        db.query(SelfSignedTeacherTeachingConfiguration)
        .filter(
            SelfSignedTeacherTeachingConfiguration.self_signed_teacher_id == teacher.id,
            SelfSignedTeacherTeachingConfiguration.is_active.is_(True),
        )
        .all()
    )
    if not configs:
        return getattr(lesson_plan, "subject_name", None)

    preferred = configs[0]
    if len(configs) > 1:
        board_value = getattr(lesson_plan, "board", None)
        for cfg in configs:
            if cfg.board_id and board_value and str(cfg.board_id).lower() == str(board_value).lower():
                preferred = cfg
                break

    subject_name = None
    if preferred.subject_ids:
        subject_row = (
            db.query(SchoolClassSubject)
            .filter(SchoolClassSubject.id == preferred.subject_ids[0])
            .first()
        )
        subject_name = subject_row.subject if subject_row else None

    return subject_name or getattr(lesson_plan, "subject_name", None)


def _resolve_school_teacher_subject(db: Session, current_user, lesson_plan) -> str | None:
    """Return the subject name for a school teacher, following their class-section-subject mapping."""
    teacher = getattr(current_user, "teacher_profile", None)
    if not teacher:
        return getattr(lesson_plan, "subject_name", None)

    mapping = (
        db.query(TeacherClassSectionSubject)
        .join(Subject, TeacherClassSectionSubject.subject_id == Subject.id)
        .filter(TeacherClassSectionSubject.teacher_id == teacher.id)
        .first()
    )
    if not mapping:
        return getattr(lesson_plan, "subject_name", None)

    subj_name = mapping.subject.name if mapping.subject else None
    return subj_name or getattr(lesson_plan, "subject_name", None)


def resolve_lesson_plan_subject_name(db: Session, lesson_plan, current_user) -> str | None:
    """
    Resolve the correct subject_name for a lesson plan, taking the current user's role
    into account — mirroring the logic used by GET /tuition/lesson-plans/my.

    - SELF_SIGNED_TEACHER → reads from SelfSignedTeacherTeachingConfiguration
    - TEACHER             → reads from TeacherClassSectionSubject
    - Any other role      → falls back to lesson_plan.subject_name (batch-walk)
    """
    if lesson_plan is None:
        return None

    role = getattr(current_user, "role", None)
    if role == UserRole.SELF_SIGNED_TEACHER:
        return _resolve_self_signed_teacher_subject(db, current_user, lesson_plan)
    if role == UserRole.TEACHER:
        return _resolve_school_teacher_subject(db, current_user, lesson_plan)
    return getattr(lesson_plan, "subject_name", None)
