from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session,joinedload
from app.db.session import get_db
from app.models.admin import *
from app.models.school import School,StudentExamData,SchoolBoard,SchoolMedium,SchoolType,HomeAssignment
from app.models.users import User
from app.models.teachers import Teacher,TeacherClassSectionSubject
from app.models.students import Student,StudentStatus,SelfSignedStudent
from app.models.staff import Staff
from app.schemas.admin import *
from app.services.students import update_admin_exam_class_ranks
from app.models.admin import *
from sqlalchemy.exc import SQLAlchemyError
from app.utils.permission import require_roles
from app.schemas.users import UserRole
from sqlalchemy import func,cast, String,case,or_,and_
from collections import defaultdict
from app.core.dependencies import get_current_user
from typing import Optional, List
from app.services.pagination import PaginationParams
from datetime import datetime, timedelta
from app.utils.services import get_validity_days
router = APIRouter()


@router.post(
    "/admin/question-banks",
    status_code=status.HTTP_201_CREATED
)
def create_question_bank(
    data: QuestionBankCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(UserRole.ADMIN))
):
    # 🔒 Check if bank already exists
    existing_bank = db.query(QuestionBank).filter(
        QuestionBank.school_class_subject_id == data.school_class_subject_id,
        QuestionBank.chapter_id == data.chapter_id
    ).first()

    if existing_bank:
        raise HTTPException(
            status_code=400,
            detail="Question bank already exists for this chapter"
        )

    bank = QuestionBank(
        school_class_subject_id=data.school_class_subject_id,
        chapter_id=data.chapter_id,
        mcq_marks=data.marks_config.mcq,
        short_marks=data.marks_config.short,
        long_marks=data.marks_config.long,
        created_by=current_user.id
    )

    db.add(bank)
    db.commit()
    db.refresh(bank)

    return {
        "message": "Question bank created successfully",
        "question_bank_id": bank.id
    }

@router.get(
    "/admin/question-banks",
    response_model=dict
)
def list_question_banks(
    school_board: SchoolBoard | None = None,
    school_medium: SchoolMedium | None = None,
    class_name: str | None = None,
    subject: str | None = None,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(UserRole.ADMIN))
):
    query = (
        db.query(QuestionBank)
        .join(SchoolClassSubject)
        .join(Chapter)
    )

    # 🔍 Filters
    if school_board:
        query = query.filter(SchoolClassSubject.school_board == school_board)
    if school_medium:
        query = query.filter(SchoolClassSubject.school_medium == school_medium)
    if class_name:
        query = query.filter(SchoolClassSubject.class_name == class_name)
    if subject:
        query = query.filter(SchoolClassSubject.subject == subject)

    banks = query.all()

    results = []

    for bank in banks:
        questions = bank.questions

        counts = {
            "total": len(questions),
            "mcq": sum(q.question_type == QuestionType.mcq for q in questions),
            "short": sum(q.question_type == QuestionType.short for q in questions),
            "long": sum(q.question_type == QuestionType.long for q in questions),
        }

        results.append({
            "id": bank.id,
            "school_board": bank.school_class_subject.school_board,
            "school_medium": bank.school_class_subject.school_medium,
            "class_name": bank.school_class_subject.class_name,
            "subject": bank.school_class_subject.subject,
            "chapter": {
                "id": bank.chapter.id,
                "name": bank.chapter.title
            },
            "marks_config": {
                "mcq": bank.mcq_marks,
                "short": bank.short_marks,
                "long": bank.long_marks
            },
            "question_counts": counts,
            "created_at": bank.created_at
        })

    return {
        "total": len(results),
        "results": results
    }

@router.post(
    "/admin/question-banks/{question_bank_id}/questions",
    status_code=status.HTTP_201_CREATED
)
def add_questions_to_bank(
    question_bank_id: int,
    data: QuestionBulkCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(UserRole.ADMIN))
):
    question_bank = db.query(QuestionBank).filter(
        QuestionBank.id == question_bank_id
    ).first()

    if not question_bank:
        raise HTTPException(404, "Question bank not found")

    created_questions = []

    for q in data.questions:
        # assign marks
        if q.question_type == QuestionType.mcq:
            marks = question_bank.mcq_marks
        elif q.question_type == QuestionType.short:
            marks = question_bank.short_marks
        else:
            marks = question_bank.long_marks

        question = Question(
            question_bank_id=question_bank.id,
            question_type=q.question_type,
            marks=marks,
            question_text=q.question_text
        )
        db.add(question)
        db.flush()

        # MCQ
        if q.question_type == QuestionType.mcq:
            if not q.options or len(q.options) < 2:
                raise HTTPException(400, "MCQ must have at least 2 options")
            if sum(o.is_correct for o in q.options) != 1:
                raise HTTPException(400, "MCQ must have exactly one correct option")

            for opt in q.options:
                db.add(QuestionOption(
                    question_id=question.id,
                    option_text=opt.option_text,
                    is_correct=opt.is_correct
                ))

        # Answer
        if q.question_type in [QuestionType.short, QuestionType.long]:
            if not q.answer:
                raise HTTPException(400, "Answer required")

            db.add(QuestionAnswer(
                question_id=question.id,
                answer_text=q.answer.answer_text
            ))

        # Key points
        if q.question_type == QuestionType.long and q.key_points:
            for kp in q.key_points:
                db.add(AnswerKeyPoint(
                    question_id=question.id,
                    key_point=kp.key_point
                ))

        created_questions.append(question.id)

    db.commit()

    return {
        "message": "Questions added successfully",
        "total_added": len(created_questions),
        "question_ids": created_questions
    }

@router.get("/admin/question-banks/{question_bank_id}")
def get_question_bank_details(
    question_bank_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(UserRole.ADMIN))
):
    bank = (
        db.query(QuestionBank)
        .options(
            joinedload(QuestionBank.school_class_subject),
            joinedload(QuestionBank.chapter),
            joinedload(QuestionBank.questions)
            .joinedload(Question.options),
            joinedload(QuestionBank.questions)
            .joinedload(Question.answer),
            joinedload(QuestionBank.questions)
            .joinedload(Question.key_points),
        )
        .filter(QuestionBank.id == question_bank_id)
        .first()
    )

    if not bank:
        raise HTTPException(status_code=404, detail="Question bank not found")

    questions_data = []

    for q in bank.questions:
        question_payload = {
            "id": q.id,
            "question_type": q.question_type.value,
            "marks": q.marks,
            "question_text": q.question_text,
            "created_at": q.created_at,
        }

        # MCQ
        if q.question_type == QuestionType.mcq:
            question_payload["options"] = [
                {
                    "id": opt.id,
                    "option_text": opt.option_text,
                    "is_correct": opt.is_correct
                }
                for opt in q.options
            ]

        # Short / Long Answer
        if q.question_type in [QuestionType.short, QuestionType.long]:
            question_payload["answer"] = (
                {
                    "id": q.answer.id,
                    "answer_text": q.answer.answer_text
                }
                if q.answer else None
            )

        # Long answer key points
        if q.question_type == QuestionType.long:
            question_payload["key_points"] = [
                {
                    "id": kp.id,
                    "key_point": kp.key_point
                }
                for kp in q.key_points
            ]

        questions_data.append(question_payload)

    return {
        "question_bank": {
            "id": bank.id,
            "school_board": bank.school_class_subject.school_board,
            "school_medium": bank.school_class_subject.school_medium,
            "class_name": bank.school_class_subject.class_name,
            "subject": bank.school_class_subject.subject,
            "chapter": {
                "id": bank.chapter.id,
                "name": bank.chapter.title
            },
            "marks_config": {
                "mcq": bank.mcq_marks,
                "short": bank.short_marks,
                "long": bank.long_marks
            },
            "created_at": bank.created_at
        },
        "total_questions": len(questions_data),
        "questions": questions_data
    }

@router.get("/admin/question-banks/{question_bank_id}/questions-with-answers")
def list_questions_with_answers(
    question_bank_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(UserRole.ADMIN))
):
    question_bank = (
        db.query(QuestionBank)
        .options(
            joinedload(QuestionBank.questions)
            .joinedload(Question.options),
            joinedload(QuestionBank.questions)
            .joinedload(Question.answer),
            joinedload(QuestionBank.questions)
            .joinedload(Question.key_points),
        )
        .filter(QuestionBank.id == question_bank_id)
        .first()
    )

    if not question_bank:
        raise HTTPException(status_code=404, detail="Question bank not found")

    questions_response = []

    for q in question_bank.questions:
        question_data = {
            "question_id": q.id,
            "question_type": q.question_type.value,
            "marks": q.marks,
            "question_text": q.question_text,
        }

        # ✅ MCQ
        if q.question_type == QuestionType.mcq:
            question_data["options"] = [
                {
                    "id": opt.id,
                    "option_text": opt.option_text,
                    "is_correct": opt.is_correct
                }
                for opt in q.options
            ]

            correct_option = next(
                (opt.option_text for opt in q.options if opt.is_correct),
                None
            )
            question_data["correct_answer"] = correct_option

        # ✅ Short / Long Answer
        if q.question_type in [QuestionType.short, QuestionType.long]:
            question_data["answer"] = (
                q.answer.answer_text if q.answer else None
            )

        # ✅ Long answer key points
        if q.question_type == QuestionType.long:
            question_data["key_points"] = [
                kp.key_point for kp in q.key_points
            ]

        questions_response.append(question_data)

    return {
        "question_bank_id": question_bank.id,
        "total_questions": len(questions_response),
        "questions": questions_response
    }
