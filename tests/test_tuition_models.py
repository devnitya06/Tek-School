from app.db.session import Base
from app.models import tuition  # noqa: F401


def test_tuition_tables_are_registered():
    expected_tables = {
        "tuition_batches",
        "tuition_batch_student_mappings",
        "tuition_batch_schedules",
        "tuition_class_done_records",
        "tuition_lesson_plans",
        "tuition_lesson_topics",
        "tuition_teacher_earnings",
        "tuition_batch_approvals",
    }

    actual_tables = set(Base.metadata.tables.keys())
    assert expected_tables.issubset(actual_tables)
