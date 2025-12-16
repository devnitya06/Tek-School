from app.models.students import Student, SelfSignedStudent
from app.models.admin import StudentAdminExamData
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

def update_admin_exam_class_ranks(db: Session, exam_id: str, class_name: str):
    results = (
        db.query(StudentAdminExamData)
        .join(SelfSignedStudent)
        .filter(
            StudentAdminExamData.exam_id == exam_id,
            SelfSignedStudent.select_class == class_name
        )
        .order_by(StudentAdminExamData.result.desc())
        .all()
    )

    for index, record in enumerate(results, start=1):
        record.class_rank = index

    db.commit()
