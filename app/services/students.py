from app.models.students import Student
from app.models.school import StudentExamData
from sqlalchemy.orm import Session
def update_class_ranks(db: Session, exam_id: str, class_id: int):
    # Get results for this exam in this class
    results = (
        db.query(StudentExamData)
        .join(Student, StudentExamData.student_id == Student.id)
        .filter(Student.class_id == class_id, StudentExamData.exam_id == exam_id)
        .order_by(StudentExamData.result.desc())
        .all()
    )