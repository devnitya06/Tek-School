from app.models.news import NewsStatus, NewsSubmission


def test_news_status_values_are_available():
    assert NewsStatus.PENDING.value == "pending"
    assert NewsStatus.APPROVED.value == "approved"
    assert NewsStatus.REJECTED.value == "rejected"

    submission = NewsSubmission(title="Test news", school_id="SCH-TEST")
    assert submission.status == NewsStatus.PENDING
