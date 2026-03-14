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

    existing_bank = db.query(QuestionBank).filter(
        QuestionBank.board == data.board,
        QuestionBank.medium == data.medium,
        QuestionBank.school_class_subject_id == data.school_class_subject_id
    ).first()

    if existing_bank:
        raise HTTPException(
            status_code=400,
            detail="Question bank already exists for this class"
        )

    bank = QuestionBank(
        board=data.board,
        medium=data.medium,
        school_class_subject_id=data.school_class_subject_id,
        subject_id=data.subject_id,
        created_by=current_user.id
    )

    db.add(bank)
    db.commit()
    db.refresh(bank)

    return {
        "message": "Question bank created successfully",
        "question_bank_id": bank.id,
        "mcq": bank.mcq_count,
        "short": bank.short_count,
        "long": bank.long_count
    }

@router.get(
    "/admin/question-banks",
    response_model=list[QuestionBankListResponse]
)
def list_question_banks(
    class_id: int | None = None,
    class_name: str | None = None,
    board: str | None = None,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(UserRole.ADMIN))
):

    query = db.query(QuestionBank)

    # Filter by board
    if board:
        query = query.filter(QuestionBank.board == board)

    # Filter by class_id
    if class_id:
        query = query.filter(
            QuestionBank.school_class_subject_id == class_id
        )

    # Filter by class_name
    if class_name:
        query = query.join(
            SchoolClassSubject,
            QuestionBank.school_class_subject_id == SchoolClassSubject.id
        ).filter(
            SchoolClassSubject.class_name.ilike(f"%{class_name}%")
        )

    banks = query.order_by(
        QuestionBank.created_at.desc()
    ).all()

    result = []

    for bank in banks:

        class_name_value = None
        subject_name = None

        if bank.school_class_subject:
            class_name_value = bank.school_class_subject.class_name

        if bank.subject:
            subject_name = bank.subject.subject

        total_questions = (
            (bank.mcq_count or 0) +
            (bank.short_count or 0) +
            (bank.long_count or 0)
        )

        result.append({
            "id": bank.id,
            "board": bank.board,
            "medium": bank.medium,
            "class_name": class_name_value,
            "subject_name": subject_name,
            "mcq_count": bank.mcq_count,
            "short_count": bank.short_count,
            "long_count": bank.long_count,
            "total_questions": total_questions,
            "created_by": bank.created_by,
            "created_at": bank.created_at,
            "updated_at": bank.updated_at
        })

    return result

@router.get(
    "/admin/question-banks/{question_bank_id}",
    response_model=QuestionBankDetailResponse
)
def get_question_bank_detail(
    question_bank_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(UserRole.ADMIN))
):

    bank = db.query(QuestionBank).filter(
        QuestionBank.id == question_bank_id
    ).first()

    if not bank:
        raise HTTPException(404, "Question bank not found")

    class_name = None
    subject_name = None

    if bank.school_class_subject:
        class_name = bank.school_class_subject.class_name

    if bank.subject:
        subject_name = bank.subject.subject

    total_questions = (
        (bank.mcq_count or 0) +
        (bank.short_count or 0) +
        (bank.long_count or 0)
    )

    return {
        "id": bank.id,
        "board": bank.board,
        "medium": bank.medium,
        "class_name": class_name,
        "subject_name": subject_name,
        "mcq_count": bank.mcq_count,
        "short_count": bank.short_count,
        "long_count": bank.long_count,
        "total_questions": total_questions,
        "created_by": bank.created_by,
        "created_at": bank.created_at,
        "updated_at": bank.updated_at
    }

@router.put("/admin/question-banks/{question_bank_id}")
def update_question_bank(
    question_bank_id: int,
    data: QuestionBankUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(UserRole.ADMIN))
):

    bank = db.query(QuestionBank).filter(
        QuestionBank.id == question_bank_id
    ).first()

    if not bank:
        raise HTTPException(404, "Question bank not found")

    if data.board is not None:
        bank.board = data.board

    if data.medium is not None:
        bank.medium = data.medium

    if data.school_class_subject_id is not None:
        bank.school_class_subject_id = data.school_class_subject_id

    if data.subject_id is not None:
        bank.subject_id = data.subject_id

    db.commit()
    db.refresh(bank)

    return {"message": "Question bank updated successfully"}

@router.delete("/admin/question-banks/{question_bank_id}")
def delete_question_bank(
    question_bank_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(UserRole.ADMIN))
):

    bank = db.query(QuestionBank).filter(
        QuestionBank.id == question_bank_id
    ).first()

    if not bank:
        raise HTTPException(404, "Question bank not found")

    db.delete(bank)
    db.commit()

    return {"message": "Question bank deleted successfully"}

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

        question = Question(
            question_bank_id=question_bank.id,
            chapter_id=q.chapter_id,
            question_type=q.question_type,
            marks=q.marks,
            question_text=q.question_text,
            image=q.image,
            source=q.source
        )

        db.add(question)
        db.flush()

        # Update question bank counts
        if q.question_type == QuestionType.mcq:
            question_bank.mcq_count += 1

        elif q.question_type == QuestionType.short:
            question_bank.short_count += 1

        elif q.question_type == QuestionType.long:
            question_bank.long_count += 1


        # MCQ validation
        if q.question_type == QuestionType.mcq:

            if not q.options or len(q.options) < 2:
                raise HTTPException(400, "MCQ must have at least 2 options")

            if sum(o.is_correct for o in q.options) != 1:
                raise HTTPException(400, "MCQ must have exactly one correct option")

            for opt in q.options:
                db.add(
                    QuestionOption(
                        question_id=question.id,
                        option_text=opt.option_text,
                        is_correct=opt.is_correct
                    )
                )

        # Short / Long answers
        if q.question_type in [QuestionType.short, QuestionType.long]:

            if not q.answer:
                raise HTTPException(400, "Answer required")

            db.add(
                QuestionAnswer(
                    question_id=question.id,
                    answer_text=q.answer.answer_text
                )
            )

        # Key points for long questions
        if q.question_type == QuestionType.long and q.key_points:

            for kp in q.key_points:
                db.add(
                    AnswerKeyPoint(
                        question_id=question.id,
                        key_point=kp.key_point
                    )
                )

        created_questions.append(question.id)

    db.commit()

    return {
        "message": "Questions added successfully",
        "total_added": len(created_questions),
        "question_ids": created_questions,
        "updated_counts": {
            "mcq": question_bank.mcq_count,
            "short": question_bank.short_count,
            "long": question_bank.long_count
        }
    }
@router.put("/admin/questions/{question_id}")
def update_question(
    question_id: int,
    data: QuestionCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(UserRole.ADMIN))
):

    question = db.query(Question).filter(
        Question.id == question_id
    ).first()

    if not question:
        raise HTTPException(404, "Question not found")

    # Update basic fields
    question.chapter_id = data.chapter_id
    question.question_type = data.question_type
    question.marks = data.marks
    question.question_text = data.question_text
    question.image = data.image
    question.source = data.source

    # ======================
    # MCQ Update
    # ======================
    if data.question_type == QuestionType.mcq:

        db.query(QuestionOption).filter(
            QuestionOption.question_id == question.id
        ).delete()

        if not data.options or len(data.options) < 2:
            raise HTTPException(400, "MCQ must have at least 2 options")

        if sum(o.is_correct for o in data.options) != 1:
            raise HTTPException(400, "MCQ must have exactly one correct option")

        for opt in data.options:
            option = QuestionOption(
                question_id=question.id,
                option_text=opt.option_text,
                is_correct=opt.is_correct
            )
            db.add(option)

    # ======================
    # Short / Long Answer
    # ======================
    if data.question_type in [QuestionType.short, QuestionType.long]:

        db.query(QuestionAnswer).filter(
            QuestionAnswer.question_id == question.id
        ).delete()

        if not data.answer:
            raise HTTPException(400, "Answer required")

        answer = QuestionAnswer(
            question_id=question.id,
            answer_text=data.answer.answer_text
        )
        db.add(answer)

    # ======================
    # Key Points for Long
    # ======================
    if data.question_type == QuestionType.long:

        db.query(AnswerKeyPoint).filter(
            AnswerKeyPoint.question_id == question.id
        ).delete()

        if data.key_points:
            for kp in data.key_points:
                keypoint = AnswerKeyPoint(
                    question_id=question.id,
                    key_point=kp.key_point
                )
                db.add(keypoint)

    db.commit()

    return {"message": "Question updated successfully"}

@router.delete("/admin/questions/{question_id}")
def delete_question(
    question_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(UserRole.ADMIN))
):

    question = db.query(Question).filter(
        Question.id == question_id
    ).first()

    if not question:
        raise HTTPException(404, "Question not found")

    question_bank = db.query(QuestionBank).filter(
        QuestionBank.id == question.question_bank_id
    ).first()

    # Decrease count
    if question.question_type == QuestionType.mcq:
        question_bank.mcq_count -= 1

    elif question.question_type == QuestionType.short:
        question_bank.short_count -= 1

    elif question.question_type == QuestionType.long:
        question_bank.long_count -= 1

    db.delete(question)
    db.commit()

    return {"message": "Question deleted successfully"}

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
            "source":q.source,
            "image":q.image,
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
