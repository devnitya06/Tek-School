from app.models.assignments.assignment import Assignment
from app.routes.assignments.assignment_routes import _build_assignment_file_usage_summary


def test_build_assignment_file_usage_summary_formats_storage_size():
    assignment = Assignment(total_file_size_bytes=1536, total_file_count=3)

    result = _build_assignment_file_usage_summary(assignment)

    assert result["assignment_id"] is None
    assert result["total_file_count"] == 3
    assert result["total_file_size_bytes"] == 1536
    assert result["total_file_size_kb"] == 1.5
    assert result["total_file_size_mb"] == 0.0015
    assert result["storage_label"] == "1.5 KB"
