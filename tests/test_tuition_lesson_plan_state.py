import pytest

from app.models.school import BusinessInquiry
from app.models.tuition import TuitionLessonPlan


def test_lesson_plan_status_values_are_supported():
    assert TuitionLessonPlan.__table__.columns['status'].default.arg == 'active'


def test_business_inquiry_has_extended_fields():
    fields = {column.name for column in BusinessInquiry.__table__.columns}
    required = {
        "gender",
        "previous_institution",
        "relationship_with",
        "prefer_days",
        "who_is_this",
    }
    assert required.issubset(fields)
