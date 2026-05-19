# pyrefly: ignore [missing-import]
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_, desc
from typing import List, Optional
from datetime import date

from app.db.session import get_db
from app.models.academic_results import AcademicResultDefinition, AcademicStudentResult, AcademicResultType
from app.models.school import School, Section, Class
from app.models.students import Student
from app.models.users import User
from app.schemas.academic_results import (
    AcademicResultDefinitionCreate,
    AcademicResultDefinitionResponse,
    AcademicStudentResultCreate,
    AcademicStudentResultResponse,
    StudentAcademicResultListResponse,
    StudentAcademicResultListItem,
    AcademicResultHistoryResponse,
    AcademicResultHistoryItem
)
from app.utils.permission import require_roles
from app.schemas.users import UserRole

router = APIRouter()

@router.post("/definitions", response_model=AcademicResultDefinitionResponse)
def create_academic_result_definition(
    data: AcademicResultDefinitionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.SCHOOL, UserRole.TEACHER))
):
    school_id = current_user.school_profile.id if current_user.role == UserRole.SCHOOL else current_user.teacher_profile.school_id

    # Create definition
    definition = AcademicResultDefinition(
        school_id=school_id,
        class_id=data.class_id,
        result_type=data.result_type,
        exam_date=data.exam_date,
        subject_marks=[item.model_dump() for item in data.subject_marks],
        grade_percentages=data.grade_percentages.model_dump(),
        created_by=current_user.id
    )
    
    db.add(definition)
    db.flush()
    
    # Add sections
    for sec_id in data.sections:
        db.execute(
            AcademicResultDefinition.sections.property.secondary.insert().values(
                definition_id=definition.id,
                section_id=sec_id
            )
        )
    
    db.commit()
    db.refresh(definition)
    
    return definition

@router.get("/definitions", response_model=List[AcademicResultDefinitionResponse])
def get_academic_result_definitions(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.SCHOOL, UserRole.TEACHER))
):
    school_id = current_user.school_profile.id if current_user.role == UserRole.SCHOOL else current_user.teacher_profile.school_id
    
    definitions = db.query(AcademicResultDefinition).filter(
        AcademicResultDefinition.school_id == school_id
    ).order_by(desc(AcademicResultDefinition.created_at)).all()
    
    return definitions

@router.post("/definitions/{definition_id}/students/{student_id}", response_model=AcademicStudentResultResponse)
def add_student_academic_result(
    definition_id: int,
    student_id: int,
    data: AcademicStudentResultCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.SCHOOL, UserRole.TEACHER))
):
    definition = db.query(AcademicResultDefinition).filter(AcademicResultDefinition.id == definition_id).first()
    if not definition:
        raise HTTPException(status_code=404, detail="Definition not found")
        
    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
        
    # Calculate total full marks and total secured marks
    total_full_marks = sum(subj.get("full_marks", 0) for subj in definition.subject_marks)
    total_secure_mark = sum(subj.secure_mark for subj in data.secure_marks)
    
    percentage = (total_secure_mark / total_full_marks * 100) if total_full_marks > 0 else 0
    
    # Calculate grade
    grade = "Failed"
    gp = definition.grade_percentages
    if percentage >= gp.get("excellent", 90):
        grade = "Excellent"
    elif percentage >= gp.get("very_good", 80):
        grade = "Very Good"
    elif percentage >= gp.get("good", 70):
        grade = "Good"
    elif percentage >= gp.get("average", 50):
        grade = "Average"
    elif percentage >= gp.get("poor", 33):
        grade = "Poor"
        
    # Check if exists
    existing = db.query(AcademicStudentResult).filter(
        AcademicStudentResult.definition_id == definition_id,
        AcademicStudentResult.student_id == student_id
    ).first()
    
    if existing:
        existing.secure_marks = [item.model_dump() for item in data.secure_marks]
        existing.total_secure_mark = total_secure_mark
        existing.grade = grade
        existing.last_result_day = data.last_result_day or definition.exam_date
        db.commit()
        db.refresh(existing)
        return existing
    else:
        new_result = AcademicStudentResult(
            definition_id=definition_id,
            student_id=student_id,
            secure_marks=[item.model_dump() for item in data.secure_marks],
            total_secure_mark=total_secure_mark,
            grade=grade,
            last_result_day=data.last_result_day or definition.exam_date,
            created_by=current_user.id
        )
        db.add(new_result)
        db.commit()
        db.refresh(new_result)
        return new_result

@router.get("/students", response_model=StudentAcademicResultListResponse)
def get_students_academic_results(
    class_id: Optional[int] = None,
    section_id: Optional[int] = None,
    result_type: Optional[AcademicResultType] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.SCHOOL, UserRole.TEACHER))
):
    school_id = current_user.school_profile.id if current_user.role == UserRole.SCHOOL else current_user.teacher_profile.school_id
    
    # Base query for students in the school
    query = db.query(
        Student,
        AcademicStudentResult,
        AcademicResultDefinition,
        Class,
        Section
    ).outerjoin(
        AcademicStudentResult, AcademicStudentResult.student_id == Student.id
    ).outerjoin(
        AcademicResultDefinition, AcademicResultDefinition.id == AcademicStudentResult.definition_id
    ).outerjoin(
        Class, Class.id == Student.class_id
    ).outerjoin(
        Section, Section.id == Student.section_id
    ).filter(
        Student.school_id == school_id
    )

    if class_id:
        query = query.filter(Student.class_id == class_id)
    if section_id:
        query = query.filter(Student.section_id == section_id)
    if result_type:
        query = query.filter(AcademicResultDefinition.result_type == result_type)
    if start_date:
        query = query.filter(AcademicResultDefinition.exam_date >= start_date)
    if end_date:
        query = query.filter(AcademicResultDefinition.exam_date <= end_date)
        
    results = query.all()
    
    items = []
    for std, res, defn, cls, sec in results:
        items.append(StudentAcademicResultListItem(
            student_id=std.id,
            student_name=f"{std.first_name} {std.last_name}",
            roll_no=std.roll_no,
            class_name=cls.name if cls else None,
            section_name=sec.name if sec else None,
            result_type=defn.result_type if defn else None,
            secure_mark=res.total_secure_mark if res else None,
            grade=res.grade if res else None,
            last_result_day=res.last_result_day if res else None,
            result_id=res.id if res else None,
            definition_id=defn.id if defn else None
        ))

    return {"items": items, "total_count": len(items)}

@router.get("/students/{student_id}/history", response_model=AcademicResultHistoryResponse)
def get_student_academic_history(
    student_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.SCHOOL, UserRole.TEACHER))
):
    school_id = current_user.school_profile.id if current_user.role == UserRole.SCHOOL else current_user.teacher_profile.school_id
    
    student = db.query(Student).filter(Student.id == student_id, Student.school_id == school_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    history = db.query(
        AcademicStudentResult,
        AcademicResultDefinition,
        Class
    ).join(
        AcademicResultDefinition, AcademicResultDefinition.id == AcademicStudentResult.definition_id
    ).join(
        Class, Class.id == AcademicResultDefinition.class_id
    ).filter(
        AcademicStudentResult.student_id == student_id
    ).order_by(desc(AcademicResultDefinition.exam_date)).all()
    
    items = []
    for res, defn, cls in history:
        items.append(AcademicResultHistoryItem(
            result_id=res.id,
            definition_id=defn.id,
            result_type=defn.result_type,
            exam_date=defn.exam_date,
            class_name=cls.name,
            secure_marks=res.secure_marks,
            total_secure_mark=res.total_secure_mark,
            grade=res.grade,
            last_result_day=res.last_result_day
        ))
        
    return {"items": items}

@router.get("/my-results", response_model=AcademicResultHistoryResponse)
def get_my_academic_results(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.STUDENT))
):
    student_id = current_user.student_profile.id
    
    history = db.query(
        AcademicStudentResult,
        AcademicResultDefinition,
        Class
    ).join(
        AcademicResultDefinition, AcademicResultDefinition.id == AcademicStudentResult.definition_id
    ).join(
        Class, Class.id == AcademicResultDefinition.class_id
    ).filter(
        AcademicStudentResult.student_id == student_id
    ).order_by(desc(AcademicResultDefinition.exam_date)).all()
    
    items = []
    for res, defn, cls in history:
        items.append(AcademicResultHistoryItem(
            result_id=res.id,
            definition_id=defn.id,
            result_type=defn.result_type,
            exam_date=defn.exam_date,
            class_name=cls.name,
            secure_marks=res.secure_marks,
            total_secure_mark=res.total_secure_mark,
            grade=res.grade,
            last_result_day=res.last_result_day
        ))
        
    return {"items": items}

@router.get("/my-results/{result_id}", response_model=AcademicResultHistoryItem)
def get_my_academic_result_detail(
    result_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.STUDENT))
):
    student_id = current_user.student_profile.id
    
    result = db.query(
        AcademicStudentResult,
        AcademicResultDefinition,
        Class
    ).join(
        AcademicResultDefinition, AcademicResultDefinition.id == AcademicStudentResult.definition_id
    ).join(
        Class, Class.id == AcademicResultDefinition.class_id
    ).filter(
        AcademicStudentResult.student_id == student_id,
        AcademicStudentResult.id == result_id
    ).first()
    
    if not result:
        raise HTTPException(status_code=404, detail="Result not found")
        
    res, defn, cls = result
    
    return AcademicResultHistoryItem(
        result_id=res.id,
        definition_id=defn.id,
        result_type=defn.result_type,
        exam_date=defn.exam_date,
        class_name=cls.name,
        secure_marks=res.secure_marks,
        total_secure_mark=res.total_secure_mark,
        grade=res.grade,
        last_result_day=res.last_result_day
    )
