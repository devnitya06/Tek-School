from app.db.session import Base
from app.models import tuition  # noqa: F401
from app.models.tuition import TuitionBatch, TuitionLessonPlan, TuitionLessonPlanBatch, generate_short_id
from app.services.tuition.lesson_plan import merge_lesson_plan_batches


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


def test_lesson_plan_batch_properties_use_batch_mappings():
    lesson_plan = TuitionLessonPlan(id="lesson-plan-1", batch_id="batch-1")
    batch_a = TuitionBatch(id="batch-1", batch_name="A", board_id="cbse", class_id=1, subject_id=1)
    batch_c = TuitionBatch(id="batch-2", batch_name="C", board_id="cbse", class_id=1, subject_id=1)

    lesson_plan.batch_mappings = [
        TuitionLessonPlanBatch(lesson_plan_id="lesson-plan-1", batch_id="batch-1"),
        TuitionLessonPlanBatch(lesson_plan_id="lesson-plan-1", batch_id="batch-2"),
    ]
    lesson_plan.batch_mappings[0].batch = batch_a
    lesson_plan.batch_mappings[1].batch = batch_c

    assert lesson_plan.batch_ids == ["batch-1", "batch-2"]
    assert [batch.batch_name for batch in lesson_plan.batches] == ["A", "C"]
    assert lesson_plan.board == "cbse"


def test_merge_lesson_plan_batches_adds_new_batch_to_existing_plan():
    lesson_plan = TuitionLessonPlan(id="lesson-plan-2", batch_id="batch-1", lesson_title="The Power 4th", status="draft")
    lesson_plan.batch_mappings = [
        TuitionLessonPlanBatch(lesson_plan_id="lesson-plan-2", batch_id="batch-1"),
    ]

    merged = merge_lesson_plan_batches(lesson_plan, ["batch-1", "batch-2"])

    assert merged.batch_id == "batch-1"
    assert [mapping.batch_id for mapping in merged.batch_mappings] == ["batch-1", "batch-2"]


def test_generate_short_id_returns_compact_identifier():
    short_id = generate_short_id()

    assert len(short_id) <= 10
    assert short_id.isalnum()
    assert short_id.startswith("ID")
