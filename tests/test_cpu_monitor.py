from app.utils.cpu_monitor import build_cpu_alert


def test_build_cpu_alert_includes_process_and_reason():
    alert = build_cpu_alert(
        system_cpu=82.5,
        threshold=70.0,
        process_name="celery",
        process_pid=1234,
        process_cpu=91.0,
        memory_percent=61.2,
        state="running",
        threads=25,
        cmdline="python -m celery worker --concurrency=8",
        reason="busy queue processing and retry loops",
    )

    assert "82.5%" in alert
    assert "celery" in alert
    assert "1234" in alert
    assert "91.0%" in alert
    assert "busy queue processing and retry loops" in alert
