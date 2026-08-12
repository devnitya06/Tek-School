from datetime import datetime, timedelta, timezone

from app.models.news import NewsStatus, NewsSubmission
from app.routes.news import _to_utc_datetime


def test_news_status_values_are_available():
    assert NewsStatus.PENDING.value == "pending"
    assert NewsStatus.APPROVED.value == "approved"
    assert NewsStatus.REJECTED.value == "rejected"

    submission = NewsSubmission(title="Test news", school_id="SCH-TEST")
    assert submission.status == NewsStatus.PENDING


def test_utc_normalization_handles_naive_and_aware_datetimes():
    naive = datetime.utcnow() + timedelta(minutes=10)
    aware = (datetime.now(timezone.utc) + timedelta(minutes=10)).astimezone(timezone.utc)

    assert _to_utc_datetime(naive).tzinfo is not None
    assert _to_utc_datetime(aware).tzinfo is not None
    assert _to_utc_datetime(naive) < _to_utc_datetime(aware) or _to_utc_datetime(naive) == _to_utc_datetime(aware)
