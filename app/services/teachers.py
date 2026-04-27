from sqlalchemy.orm import Session
from app.models.school import Exam
from app.models.teachers import RewardTransaction, TeacherWallet

def calculate_level(total_points: int) -> int:
    if total_points >= 1000:
        return 5
    elif total_points >= 500:
        return 4
    elif total_points >= 200:
        return 3
    elif total_points >= 50:
        return 2
    return 1

def reward_teacher_for_exam(db: Session, exam: Exam):
    if not exam.created_by:
        return

    teacher_id = exam.created_by

    wallet = db.query(TeacherWallet).filter_by(
        teacher_id=teacher_id
    ).first()

    if not wallet:
        wallet = TeacherWallet(teacher_id=teacher_id)
        db.add(wallet)
        db.flush()

    # 🔥 You can make this dynamic later
    points = 10

    wallet.total_earned += points
    wallet.balance += points
    wallet.level = calculate_level(wallet.total_earned)

    db.add(RewardTransaction(
        teacher_id=teacher_id,
        points=points,
        type="EARN",
        exam_id=exam.id
    ))