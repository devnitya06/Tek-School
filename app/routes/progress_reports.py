from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, or_, and_
from typing import List

from app.db.session import get_db
from app.models.users import User
from app.schemas.users import UserRole
from app.core.dependencies import get_current_user
from app.utils.permission import require_roles, verify_school_business_access
from app.models.students import Student
from app.models.school import Class, Section
from app.models.staff import Staff
from app.models.teachers import Teacher
from app.models.progress_reports import ProgressReport, ProgressReportStatus
from app.schemas.progress_reports import (
    ProgressReportCreate,
    ProgressReportUpdate,
    ProgressReportResponse,
    StudentProgressListResponse
)
from app.services.pagination import PaginationParams

router = APIRouter()

def get_user_school_id(current_user: User, db: Session) -> str:
    if current_user.role == UserRole.SCHOOL:
        verify_school_business_access(current_user, db)
        return current_user.school_profile.id
    elif current_user.role == UserRole.TEACHER:
        teacher = current_user.teacher_profile
        if not teacher:
            raise HTTPException(status_code=404, detail="Teacher profile not found")
        return teacher.school_id
    elif current_user.role == UserRole.STAFF:
        staff = db.query(Staff).filter(Staff.user_id == current_user.id).first()
        if not staff:
            raise HTTPException(status_code=404, detail="Staff profile not found")
        return staff.school_id
    else:
        raise HTTPException(status_code=403, detail="Invalid role for this operation")

@router.get("/students", response_model=dict, summary="Get students with progress report statistics")
def get_students_with_reports(
    pagination: PaginationParams = Depends(),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.SCHOOL, UserRole.TEACHER, UserRole.STAFF)),
    class_id: int | None = Query(None, description="Filter by class ID"),
    section_id: int | None = Query(None, description="Filter by section ID"),
    student_name: str | None = Query(None, description="Filter by student name")
):
    school_id = get_user_school_id(current_user, db)

    # Subqueries for reports count and latest report date
    reports_count_subquery = (
        db.query(
            ProgressReport.student_id,
            func.count(ProgressReport.id).label("no_of_reports"),
            func.max(ProgressReport.created_at).label("last_report_date")
        )
        .filter(ProgressReport.school_id == school_id)
        .group_by(ProgressReport.student_id)
        .subquery()
    )

    query = (
        db.query(
            Student,
            Class.name.label("class_name"),
            Section.name.label("section_name"),
            func.coalesce(reports_count_subquery.c.no_of_reports, 0).label("no_of_reports"),
            reports_count_subquery.c.last_report_date.label("last_report_date")
        )
        .join(Class, Student.class_id == Class.id)
        .join(Section, Student.section_id == Section.id)
        .outerjoin(reports_count_subquery, Student.id == reports_count_subquery.c.student_id)
        .filter(Student.school_id == school_id)
    )

    if class_id:
        query = query.filter(Student.class_id == class_id)
    if section_id:
        query = query.filter(Student.section_id == section_id)
    if student_name:
        query = query.filter(
            func.concat(Student.first_name, " ", Student.last_name).ilike(f"%{student_name}%")
        )

    # Pagination
    total_count = query.count()
    results = query.offset(pagination.offset()).limit(pagination.limit()).all()

    formatted_results = []
    for student, class_name, section_name, no_of_reports, last_report_date in results:
        formatted_results.append({
            "student_id": student.id,
            "student_name": f"{student.first_name} {student.last_name}",
            "class_name": class_name,
            "section_name": section_name,
            "roll_no": student.roll_no,
            "no_of_reports": no_of_reports,
            "last_report_date": last_report_date.date() if last_report_date else None,
            "student_status": student.status.value if student.status else None
        })

    return pagination.format_response(formatted_results, total_count)

@router.post("/", response_model=ProgressReportResponse, status_code=status.HTTP_201_CREATED)
def create_progress_report(
    data: ProgressReportCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.SCHOOL, UserRole.TEACHER))
):
    school_id = get_user_school_id(current_user, db)
    
    # Verify student exists in this school
    student = db.query(Student).filter(Student.id == data.student_id, Student.school_id == school_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found in your school")

    teacher_id = None
    if current_user.role == UserRole.TEACHER:
        teacher_id = current_user.teacher_profile.id

    report = ProgressReport(
        student_id=data.student_id,
        school_id=school_id,
        teacher_id=teacher_id,
        report_title=data.report_title,
        duration_from=data.duration_from,
        duration_to=data.duration_to,
        status=data.status,
        subjects=[s.dict() for s in data.subjects] if data.subjects else [],
        assessment_areas=[a.dict() for a in data.assessment_areas] if data.assessment_areas else [],
        key_needs_improvement=data.key_needs_improvement
    )

    db.add(report)
    db.commit()
    db.refresh(report)

    return report

@router.get("/my-reports", response_model=List[ProgressReportResponse])
def get_my_progress_reports(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.STUDENT))
):
    student = current_user.student_profile
    if not student:
        raise HTTPException(status_code=404, detail="Student profile not found")
        
    query = db.query(ProgressReport).filter(
        ProgressReport.student_id == student.id,
        ProgressReport.status == ProgressReportStatus.PUBLISHED
    ).order_by(desc(ProgressReport.created_at))
    
    return query.all()

@router.get("/student/{student_id}", response_model=List[ProgressReportResponse])
def list_student_progress_reports(
    student_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # School/Teacher/Staff must belong to student's school.
    # Student/Parent can view their own.
    if current_user.role in [UserRole.SCHOOL, UserRole.TEACHER, UserRole.STAFF]:
        school_id = get_user_school_id(current_user, db)
        student = db.query(Student).filter(Student.id == student_id, Student.school_id == school_id).first()
        if not student:
            raise HTTPException(status_code=404, detail="Student not found")
    elif current_user.role == UserRole.STUDENT:
        if current_user.student_profile.id != student_id:
            raise HTTPException(status_code=403, detail="Not authorized to view other student's reports")
    # For Parent, could check parent relationship here
    
    query = db.query(ProgressReport).filter(ProgressReport.student_id == student_id)
    
    # If student, only show published reports
    if current_user.role == UserRole.STUDENT:
        query = query.filter(ProgressReport.status == ProgressReportStatus.PUBLISHED)

    return query.order_by(desc(ProgressReport.created_at)).all()

@router.get("/{report_id}", response_model=ProgressReportResponse)
def get_progress_report(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    report = db.query(ProgressReport).filter(ProgressReport.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    if current_user.role in [UserRole.SCHOOL, UserRole.TEACHER, UserRole.STAFF]:
        school_id = get_user_school_id(current_user, db)
        if report.school_id != school_id:
            raise HTTPException(status_code=403, detail="Report belongs to another school")
    elif current_user.role == UserRole.STUDENT:
        if current_user.student_profile.id != report.student_id or report.status != ProgressReportStatus.PUBLISHED:
            raise HTTPException(status_code=403, detail="Not authorized to view this report")
            
    return report

@router.put("/{report_id}", response_model=ProgressReportResponse)
def update_progress_report(
    report_id: int,
    data: ProgressReportUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.SCHOOL, UserRole.TEACHER))
):
    school_id = get_user_school_id(current_user, db)
    
    report = db.query(ProgressReport).filter(ProgressReport.id == report_id, ProgressReport.school_id == school_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    if data.report_title is not None:
        report.report_title = data.report_title
    if data.duration_from is not None:
        report.duration_from = data.duration_from
    if data.duration_to is not None:
        report.duration_to = data.duration_to
    if data.status is not None:
        report.status = data.status
    if data.subjects is not None:
        report.subjects = [s.dict() for s in data.subjects]
    if data.assessment_areas is not None:
        report.assessment_areas = [a.dict() for a in data.assessment_areas]
    if data.key_needs_improvement is not None:
        report.key_needs_improvement = data.key_needs_improvement

    db.commit()
    db.refresh(report)
    return report
