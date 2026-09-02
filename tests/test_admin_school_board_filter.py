import pytest

from app.models.school import SchoolType
from app.routes.admin import (
    normalize_array_query_values,
    normalize_enum_values,
    normalize_school_board_values,
)


def test_normalize_school_board_values_lowercases_and_removes_blank_values():
    normalized = normalize_school_board_values([" CBSE ", "higher_education", "", "professional_education"])

    assert normalized == ["cbse", "higher_education", "professional_education"]


def test_normalize_school_board_values_rejects_unknown_board():
    with pytest.raises(ValueError):
        normalize_school_board_values(["cbse", "invalid_board"])


def test_normalize_school_type_values_supports_multiple_values():
    normalized = normalize_enum_values(SchoolType, [" PRIVATE ", "government"])

    assert normalized == ["private", "government"]


def test_normalize_array_query_values_supports_json_and_repeated_values():
    normalized = normalize_array_query_values(['["Nursery", "LKG"]', "UKG"])

    assert normalized == ["Nursery", "LKG", "UKG"]
