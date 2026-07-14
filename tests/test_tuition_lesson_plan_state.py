import pytest

from app.models.tuition import TuitionLessonPlan


def test_lesson_plan_status_values_are_supported():
    assert TuitionLessonPlan.__table__.columns['status'].default.arg == 'draft'
