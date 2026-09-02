import pytest

from app.routes.admin import normalize_school_board_values


def test_normalize_school_board_values_lowercases_and_removes_blank_values():
    normalized = normalize_school_board_values([" CBSE ", "higher_education", "", "professional_education"])

    assert normalized == ["cbse", "higher_education", "professional_education"]


def test_normalize_school_board_values_rejects_unknown_board():
    with pytest.raises(ValueError):
        normalize_school_board_values(["cbse", "invalid_board"])
