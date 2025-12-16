from datetime import time
from sqlalchemy.orm import Session
from app.models.school import McqBank
from app.schemas.school import McqBulkCreate
from app.utils.s3 import upload_base64_to_s3
from fastapi import HTTPException
from app.models.admin import PlanDuration
def is_time_overlap(start1: time, end1: time, start2: time, end2: time) -> bool:
    return max(start1, start2) < min(end1, end2)



def create_mcq(db: Session, exam_id: str, mcq_bulk: McqBulkCreate):
    created_mcqs = []

    for mcq in mcq_bulk.mcqs:  # Loop through each question
        # validation based on mcq_type
        if mcq.mcq_type == "1" and len(mcq.correct_option) > 1:
            raise ValueError("Single correct MCQ can only have one correct option")
        if mcq.mcq_type == "2" and len(mcq.correct_option) < 2:
            raise ValueError("Multiple correct MCQ must have at least two correct options")
        
        image_url = None
        if mcq.image:
            try:
                print("🔹 Uploading MCQ image to S3...")
                image_url = upload_base64_to_s3(
                    base64_string=mcq.image,
                    filename_prefix="exam_mcq"
                )
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Image upload failed: {str(e)}")

        new_mcq = McqBank(
            exam_id=exam_id,
            question=mcq.question,
            mcq_type=mcq.mcq_type,
            image=image_url,
            option_a=mcq.option_a,
            option_b=mcq.option_b,
            option_c=mcq.option_c,
            option_d=mcq.option_d,
            correct_option=mcq.correct_option,
        )
        db.add(new_mcq)
        created_mcqs.append(new_mcq)

    db.commit()
    for mcq in created_mcqs:
        db.refresh(mcq)

    return created_mcqs


def get_mcqs_by_exam(db: Session, exam_id: int):
    return db.query(McqBank).filter(McqBank.exam_id == exam_id).all()

def delete_mcq(db: Session, mcq_id: int):
    db_mcq = db.query(McqBank).filter(McqBank.id == mcq_id).first()
    if not db_mcq:
        return False
    db.delete(db_mcq)
    db.commit()
    return True

def evaluate_exam(db: Session, exam_id: str, answers: dict):
    """Check student's answers and return score + pass/fail"""
    total_questions = db.query(McqBank).filter(McqBank.exam_id == exam_id).count()
    correct_count = 0

    for qid, selected_option in answers.items():
        question = db.query(McqBank).filter(
            McqBank.id == qid,
            McqBank.exam_id == exam_id
        ).first()

        if question and question.correct_option == selected_option:
            correct_count += 1

    # simple rule: pass if 40% or more correct
    percentage = (correct_count / total_questions) * 100 if total_questions > 0 else 0
    status = "pass" if percentage >= 40 else "fail"

    return {
        "total": total_questions,
        "correct": correct_count,
        "percentage": percentage,
        "status": status
    }

def get_validity_days(duration: PlanDuration) -> int:
    if duration == PlanDuration.MONTHLY:
        return 30
    if duration == PlanDuration.QUARTERLY:
        return 90
    if duration == PlanDuration.YEARLY:
        return 365
