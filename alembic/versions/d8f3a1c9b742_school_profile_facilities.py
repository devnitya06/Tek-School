"""Add institution details and migrate school facilities to typed values.

Revision ID: d8f3a1c9b742
Revises: b7c8d9e0f123
Create Date: 2026-10-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "d8f3a1c9b742"
down_revision: Union[str, None] = "b7c8d9e0f123"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_type(column: str) -> str:
    return op.get_bind().execute(
        sa.text(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_schema = current_schema() "
            "AND table_name = 'schools' AND column_name = :column"
        ),
        {"column": column},
    ).scalar_one()


def _boolean_to_text(column: str, true_value: str, false_value: str) -> None:
    if "'" in true_value or "'" in false_value:
        raise ValueError("Boolean conversion labels must not contain single quotes")
    op.alter_column("schools", column, server_default=None)
    op.execute(
        f'ALTER TABLE schools ALTER COLUMN "{column}" TYPE VARCHAR(50) '
        f"USING CASE WHEN \"{column}\" IS TRUE THEN '{true_value}' "
        f"WHEN \"{column}\" IS FALSE THEN '{false_value}' ELSE NULL END"
    )


def _normalize_text_column(column: str, mapping: dict[str, str]) -> None:
    cases = " ".join(
        f"WHEN '{legacy}' THEN '{current}'" for legacy, current in mapping.items()
    )
    op.execute(
        sa.text(
            f'UPDATE schools SET "{column}" = CASE lower(btrim("{column}")) '
            f"{cases} ELSE NULL END WHERE \"{column}\" IS NOT NULL"
        )
    )


def _migrate_text_facility(
    column: str, mapping: dict[str, str], boolean_mapping: tuple[str, str]
) -> None:
    column_type = _column_type(column)
    if column_type == "boolean":
        _boolean_to_text(column, *boolean_mapping)
    elif column_type not in {"character varying", "text"}:
        raise RuntimeError(
            f"Unsupported type {column_type!r} for schools.{column}"
        )
    _normalize_text_column(column, mapping)


def _migrate_hostel() -> None:
    op.execute(
        """
        UPDATE schools AS school
        SET hostel = (
            SELECT CASE
                WHEN count(value) = 0 THEN NULL
                WHEN bool_or(value = 'not_available') AND count(value) > 1 THEN NULL
                ELSE array_agg(value ORDER BY value) FILTER (WHERE value IS NOT NULL)
            END
            FROM (
                SELECT DISTINCT CASE lower(btrim(selection))
                    WHEN 'boys' THEN 'boys'
                    WHEN 'boys hostel' THEN 'boys'
                    WHEN 'girls' THEN 'girls'
                    WHEN 'girls hostel' THEN 'girls'
                    WHEN 'both' THEN 'both'
                    WHEN 'not available' THEN 'not_available'
                    WHEN 'not_available' THEN 'not_available'
                    ELSE NULL
                END AS value
                FROM unnest(school.hostel) AS selections(selection)
            ) AS mapped
        )
        WHERE school.hostel IS NOT NULL
        """
    )
    op.execute(
        """
        UPDATE schools
        SET hostel = ARRAY['boys', 'girls']::varchar[]
        WHERE hostel @> ARRAY['both']::varchar[]
        """
    )


def _migrate_admission_process() -> None:
    column_type = _column_type("admission_process")
    if column_type in {"character varying", "text"}:
        op.alter_column(
            "schools",
            "admission_process",
            type_=postgresql.ARRAY(sa.String()),
            existing_type=sa.String(),
            postgresql_using="""
                CASE lower(btrim(admission_process))
                    WHEN 'direct' THEN ARRAY['direct']::varchar[]
                    WHEN 'entrance' THEN ARRAY['entrance_exam']::varchar[]
                    WHEN 'entrance exam' THEN ARRAY['entrance_exam']::varchar[]
                    WHEN 'entrance_exam' THEN ARRAY['entrance_exam']::varchar[]
                    WHEN 'merit/mark-based' THEN ARRAY['merit_mark_based']::varchar[]
                    WHEN 'merit' THEN ARRAY['merit_mark_based']::varchar[]
                    WHEN 'merit_mark_based' THEN ARRAY['merit_mark_based']::varchar[]
                    WHEN 'interview' THEN ARRAY['interview']::varchar[]
                    WHEN 'other' THEN ARRAY['other']::varchar[]
                    ELSE NULL
                END
            """,
        )
    elif column_type != "ARRAY":
        raise RuntimeError(
            f"Unsupported type {column_type!r} for schools.admission_process"
        )


def upgrade() -> None:
    existing_columns = {
        column["name"] for column in sa.inspect(op.get_bind()).get_columns("schools")
    }
    new_columns = (
        sa.Column("accreditation", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column("recognition_approval", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column("institution_type", sa.String(length=100), nullable=True),
        sa.Column("accommodation_type", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column("city", sa.String(length=100), nullable=True),
    )
    for column in new_columns:
        if column.name not in existing_columns:
            op.add_column("schools", column)

    _migrate_text_facility(
        "computer_lab",
        {"yes": "yes", "no": "no", "under_progress": "under_development",
         "under development": "under_development", "under_development": "under_development"},
        ("yes", "no"),
    )
    _migrate_text_facility(
        "library",
        {"yes": "yes", "no": "no", "under_progress": "under_development",
         "under development": "under_development", "under_development": "under_development"},
        ("yes", "no"),
    )
    _migrate_text_facility(
        "have_digital_board",
        {"yes": "yes", "no": "no", "under_progress": "under_development",
         "under development": "under_development", "under_development": "under_development"},
        ("yes", "no"),
    )
    _migrate_text_facility(
        "transportation_facility",
        {"yes": "available", "available": "available",
         "no": "not_available", "not available": "not_available",
         "not_applicable": "not_available",
         "temporarily unavailable": "temporarily_unavailable",
         "temporarily_unavailable": "temporarily_unavailable"},
        ("available", "not_available"),
    )
    _migrate_text_facility(
        "playground_facility",
        {"no": "none", "none": "none", "indoor_playground": "indoor",
         "indoor": "indoor", "outdoor": "outdoor", "both": "both"},
        ("", "none"),
    )
    _migrate_text_facility(
        "have_cctv_in_campus",
        {"yes": "available", "available": "available",
         "no": "not_available", "not available": "not_available",
         "only_where_required": "partial_coverage",
         "partial coverage": "partial_coverage", "partial_coverage": "partial_coverage"},
        ("available", "not_available"),
    )
    _migrate_text_facility(
        "lms_facility",
        {"integrated": "integrated", "not integrated": "not_integrated",
         "not_integrated": "not_integrated",
         "under implementation": "under_implementation",
         "under_implementation": "under_implementation"},
        ("integrated", "not_integrated"),
    )
    _migrate_text_facility(
        "have_scholarship_opportunities",
        {"available": "available", "not available": "not_available",
         "not_available": "not_available",
         "contact institution": "contact_institution",
         "contact_institution": "contact_institution"},
        ("available", "not_available"),
    )
    _migrate_text_facility(
        "have_extra_curricular_activities",
        {"available": "available", "not available": "not_available",
         "not_available": "not_available"},
        ("available", "not_available"),
    )

    _normalize_text_column(
        "medical_faculties",
        {
            "primary_aids": "first_aid",
            "first aid": "first_aid",
            "first_aid": "first_aid",
            "no_available": "not_available",
            "not available": "not_available",
            "not_available": "not_available",
            "medical room": "medical_room",
            "medical_room": "medical_room",
            "on-campus medical staff": "on_campus_medical_staff",
            "on_campus_medical_staff": "on_campus_medical_staff",
            "no_available": "not_available",
            "not available": "not_available",
        },
    )
    _migrate_hostel()
    _migrate_admission_process()


def downgrade() -> None:
    op.alter_column(
        "schools",
        "admission_process",
        type_=sa.String(),
        existing_type=postgresql.ARRAY(sa.String()),
        postgresql_using="array_to_string(admission_process, ',')",
    )
    op.execute(
        """
        UPDATE schools SET admission_process = CASE
            WHEN admission_process IS NULL OR btrim(admission_process) = '' THEN NULL
            WHEN lower(split_part(admission_process, ',', 1)) = 'direct' THEN 'direct'
            WHEN lower(split_part(admission_process, ',', 1)) = 'entrance_exam' THEN 'entrance'
            WHEN lower(split_part(admission_process, ',', 1)) = 'merit_mark_based' THEN 'merit'
            WHEN lower(split_part(admission_process, ',', 1)) = 'interview' THEN 'interview'
            WHEN lower(split_part(admission_process, ',', 1)) = 'other' THEN 'other'
            ELSE NULL
        END
        """
    )

    op.execute(
        """
        UPDATE schools SET hostel = ARRAY(
            SELECT DISTINCT CASE lower(selection)
                WHEN 'boys' THEN 'boys'
                WHEN 'girls' THEN 'girls'
                WHEN 'not_available' THEN 'not_available'
                ELSE NULL
            END
            FROM unnest(hostel) AS selections(selection)
            WHERE lower(selection) IN ('boys', 'girls', 'not_available')
        )::varchar[]
        WHERE hostel IS NOT NULL
        """
    )

    reverse_mappings = {
        "computer_lab": {"yes": "yes", "no": "no", "under_development": "under_progress"},
        "library": {"yes": "yes", "no": "no", "under_development": "under_progress"},
        "have_digital_board": {"yes": "yes", "no": "no", "under_development": "under_progress"},
        "transportation_facility": {"available": "yes", "not_available": "no",
                                    "temporarily_unavailable": "not_applicable"},
        "playground_facility": {"none": "no", "indoor": "indoor_playground"},
        "have_cctv_in_campus": {"available": "yes", "not_available": "no",
                                "partial_coverage": "only_where_required"},
    }
    for column, mapping in reverse_mappings.items():
        cases = " ".join(
            f"WHEN '{current.lower()}' THEN '{legacy}'"
            for current, legacy in mapping.items()
        )
        op.execute(
            sa.text(
                f'UPDATE schools SET "{column}" = CASE lower(btrim("{column}")) '
                f"{cases} ELSE NULL END WHERE \"{column}\" IS NOT NULL"
            )
        )

    for column, true_value, false_value, restore_false_default in (
        ("lms_facility", "integrated", "not_integrated", False),
        ("have_scholarship_opportunities", "available", "not_available", True),
        ("have_extra_curricular_activities", "available", "not_available", True),
    ):
        op.alter_column(
            "schools",
            column,
            type_=sa.Boolean(),
            existing_type=sa.String(length=50),
            postgresql_using=(
                f'CASE WHEN "{column}" = \'{true_value}\' THEN TRUE '
                f'WHEN "{column}" = \'{false_value}\' THEN FALSE ELSE NULL END'
            ),
        )
        if restore_false_default:
            op.alter_column(
                "schools",
                column,
                server_default=sa.text("false"),
            )

    op.execute(
        """
        UPDATE schools SET medical_faculties = CASE lower(btrim(medical_faculties))
            WHEN 'first_aid' THEN 'primary_aids'
            WHEN 'not_available' THEN 'no_available'
            ELSE NULL
        END WHERE medical_faculties IS NOT NULL
        """
    )

    op.drop_column("schools", "accommodation_type")
    op.drop_column("schools", "institution_type")
    op.drop_column("schools", "recognition_approval")
    op.drop_column("schools", "accreditation")
    op.drop_column("schools", "city")
