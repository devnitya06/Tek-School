import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import ARRAY, Boolean, String

from app.models.school import School
from app.routes import school as school_routes
from app.schemas.school import SchoolProfileUpdate


def _school():
    return SimpleNamespace(
        id="SCH-123459",
        user_id=1,
        school_name="Jupiter International School",
        school_type=None,
        school_medium=None,
        school_board=None,
        profile_pic_url=None,
        banner_pic_url=None,
        establishment_year=None,
        establishment_month=None,
        register_no=None,
        pin_code=None,
        block_division=None,
        city=None,
        district=None,
        state=None,
        country=None,
        school_email="school@example.com",
        school_phone="9999999999",
        school_alt_phone=None,
        school_website=None,
        school_other_email=None,
        school_location=None,
        principal_name=None,
        principal_designation=None,
        principal_email=None,
        principal_phone=None,
        is_active=True,
        is_verified=True,
        account_type=None,
        is_business_approved=False,
        is_promotion_pending=False,
        created_at=None,
        institution_categories=None,
        accreditation=["nba"],
        recognition_approval=None,
        institution_type=None,
        accommodation_type=None,
        hostel=None,
        computer_lab=None,
        medical_faculties=None,
        job_assurance=None,
        admission_process=None,
        internship=None,
        lms_facility=None,
        alumni_network=None,
        institution_class=None,
        library=None,
        available_classes=None,
        have_digital_board="no",
        have_cctv_in_campus=None,
        have_scholarship_opportunities=None,
        have_extra_curricular_activities=None,
        total_teachers=None,
        total_students=None,
        class_from=None,
        class_to=None,
        due_installment_type=None,
        transportation_facility=None,
        playground_facility=None,
        teaching_method=None,
        default_settlement_channel=None,
        created_by_admin=False,
        claim_status="unclaimed",
        claim_completed_at=None,
        attendance_qr_mark_in_token=None,
        attendance_qr_mark_out_token=None,
        followup_enabled=False,
        followup_days=0,
        followup_status="inactive",
        followup_note=None,
        followup_last_sent_at=None,
        followup_completed_at=None,
    )


def _rating_stats():
    categories = (
        "infrastructure",
        "value_for_fee",
        "teaching_quality",
        "academic_results",
        "placement_support",
        "industrial_training",
        "extracurricular",
        "student_alumni",
        "hostel_and_foods",
        "transportation",
        "safety_and_discipline",
        "management",
    )
    return SimpleNamespace(
        rating_count=0,
        average_rating=None,
        **{category: None for category in categories},
        **{f"cnt_{category}": 0 for category in categories},
    )


class _Query:
    def filter(self, *_args, **_kwargs):
        return self

    def first(self):
        return _rating_stats()


class _Database:
    def query(self, *_args, **_kwargs):
        return _Query()

    def commit(self):
        pass

    def refresh(self, _school):
        pass


class _OwnershipQuery:
    def __init__(self, model, school, agent_profile):
        self.model = model
        self.school = school
        self.agent_profile = agent_profile

    def filter(self, *_args, **_kwargs):
        return self

    def first(self):
        if self.model is school_routes.AgentProfile:
            return self.agent_profile
        return self.school


class _OwnershipDatabase:
    def __init__(self, school, agent_profile):
        self.school = school
        self.agent_profile = agent_profile

    def query(self, model):
        return _OwnershipQuery(model, self.school, self.agent_profile)


class _AgentEligibilityQuery:
    def __init__(self, model):
        self.model = model

    def filter(self, *_args, **_kwargs):
        return self

    def first(self):
        if self.model is school_routes.AgentProfile:
            return SimpleNamespace(id=4)
        return SimpleNamespace(idp_is_enabled=True)


class _AgentEligibilityDatabase:
    def query(self, model):
        return _AgentEligibilityQuery(model)


class _Request:
    def __init__(self, body):
        self.body = body

    async def json(self):
        return self.body


def test_school_profile_facility_columns_use_string_and_array_storage():
    assert isinstance(School.__table__.c.city.type, String)
    assert School.__table__.c.city.nullable

    for column in (
        "computer_lab",
        "library",
        "have_digital_board",
        "have_cctv_in_campus",
        "transportation_facility",
        "playground_facility",
        "medical_faculties",
        "lms_facility",
        "have_scholarship_opportunities",
        "have_extra_curricular_activities",
    ):
        assert isinstance(School.__table__.c[column].type, String)
        assert not isinstance(School.__table__.c[column].type, Boolean)

    for column in (
        "accreditation",
        "recognition_approval",
        "accommodation_type",
        "admission_process",
        "hostel",
    ):
        assert isinstance(School.__table__.c[column].type, ARRAY)


def test_update_schema_accepts_allowed_facility_values_and_multi_selects():
    update = SchoolProfileUpdate(
        accreditation=["naac", "nirf"],
        recognition_approval=["ugc", "aicte"],
        institution_type="school",
        accommodation_type=["day_general", "day_boarding"],
        have_digital_board="yes",
        computer_lab="under_development",
        library="no",
        transportation_facility="temporarily_unavailable",
        playground_facility="both",
        have_cctv_in_campus="partial_coverage",
        admission_process=["direct", "merit_mark_based"],
        medical_faculties="first_aid",
        have_scholarship_opportunities="contact_institution",
        have_extra_curricular_activities="available",
        lms_facility="integrated",
        hostel=["boys", "girls"],
    )

    assert update.admission_process == ["direct", "merit_mark_based"]
    assert update.accommodation_type == ["day_general", "day_boarding"]
    assert update.have_digital_board.value == "yes"


@pytest.mark.parametrize(
    "values",
    [
        {"institution_type": "Unknown"},
        {"computer_lab": "Almost Ready"},
        {"transportation_facility": "Sometimes"},
        {"admission_process": "direct"},
        {"recognition_approval": ["INVALID"]},
        {"have_scholarship_opportunities": True},
    ],
)
def test_update_schema_rejects_invalid_facility_values(values):
    with pytest.raises(ValidationError):
        SchoolProfileUpdate(**values)


def test_update_schema_requires_lowercase_snake_case_option_values():
    with pytest.raises(ValidationError):
        SchoolProfileUpdate(computer_lab="Under Development")
    assert SchoolProfileUpdate(computer_lab="under_development").computer_lab.value == (
        "under_development"
    )


def test_hostel_both_normalizes_to_boys_and_girls_and_rejects_contradictions():
    assert SchoolProfileUpdate(hostel=["both"]).hostel == ["boys", "girls"]
    with pytest.raises(ValidationError, match="cannot be selected"):
        SchoolProfileUpdate(hostel=["not_available", "boys"])


def test_partial_update_preserves_omitted_values_and_empty_arrays_clear():
    omitted = SchoolProfileUpdate(computer_lab="yes")
    assert omitted.model_fields_set == {"computer_lab"}
    assert omitted.accreditation is None

    clear = SchoolProfileUpdate(accreditation=[], admission_process=[], hostel=[])
    assert clear.accreditation == []
    assert clear.admission_process == []
    assert clear.hostel == []


def test_agent_school_ownership_check_remains_enforced():
    school = _school()
    school.created_by_agent_profile_id = 7
    agent = SimpleNamespace(role=school_routes.UserRole.AGENT, id=22)
    db = _OwnershipDatabase(school, SimpleNamespace(id=7))

    assert school_routes._get_school_for_admin_or_school(
        agent, db, school.id
    ) is school

    db.agent_profile.id = 8
    with pytest.raises(HTTPException) as exc_info:
        school_routes._get_school_for_admin_or_school(agent, db, school.id)
    assert exc_info.value.status_code == 403


def test_idp_configuration_is_the_agent_onboarding_gate():
    profile, config = school_routes._resolve_agent_for_school_endpoint(
        SimpleNamespace(id=1471),
        _AgentEligibilityDatabase(),
    )

    assert profile.id == 4
    assert config.idp_is_enabled is True


def test_update_route_persists_values_and_returns_profile_with_stored_values(monkeypatch):
    school = _school()
    admin = SimpleNamespace(role=school_routes.UserRole.ADMIN, id=1)
    monkeypatch.setattr(
        school_routes,
        "_get_school_for_admin_or_school",
        lambda _user, _db, _school_id: school,
    )
    monkeypatch.setattr(
        school_routes,
        "_get_school_public_or_auth",
        lambda _user, _db, _school_id: school,
    )
    body = {
        "city": "Pune",
        "accreditation": ["naac", "nirf"],
        "recognition_approval": ["ugc", "aicte"],
        "institution_type": "school",
        "accommodation_type": ["day_general"],
        "admission_process": ["direct", "interview"],
        "hostel": ["both"],
        "have_digital_board": "yes",
        "computer_lab": "under_development",
        "library": "no",
        "transportation_facility": "available",
        "playground_facility": "outdoor",
        "have_cctv_in_campus": "partial_coverage",
        "medical_faculties": "first_aid",
        "have_scholarship_opportunities": "contact_institution",
        "have_extra_curricular_activities": "available",
        "lms_facility": "integrated",
    }

    response = asyncio.run(
        school_routes.update_school_profile(
            request=_Request(body),
            data=SchoolProfileUpdate(**body),
            school_id=None,
            db=_Database(),
            current_user=admin,
        )
    )

    assert school.accreditation == ["naac", "nirf"]
    assert school.city == "Pune"
    assert school.recognition_approval == ["ugc", "aicte"]
    assert school.institution_type == "school"
    assert school.accommodation_type == ["day_general"]
    assert school.admission_process == ["direct", "interview"]
    assert school.hostel == ["boys", "girls"]
    assert school.have_digital_board == "yes"
    assert school.lms_facility == "integrated"
    assert school.have_scholarship_opportunities == "contact_institution"
    assert response["profile"]["accreditation"] == school.accreditation
    assert response["profile"]["city"] == "Pune"
    assert response["profile"]["admission_process"] == school.admission_process
    assert response["profile"]["hostel"] == school.hostel
    assert response["profile"]["is_verified"] is True
    assert response["profile"]["rating_count"] == 0
    assert response["profile"]["account_type"] is None
    get_response = school_routes.get_school_self(
        school_id=school.id,
        db=_Database(),
        current_user=admin,
    )
    assert response["profile"].keys() == get_response.keys()
    assert get_response["accreditation"] == school.accreditation
    assert get_response["city"] == "Pune"
    assert get_response["recognition_approval"] == school.recognition_approval
    assert get_response["admission_process"] == school.admission_process


def test_school_get_returns_values_from_school_record(monkeypatch):
    school = _school()
    school.city = "Pune"
    school.accreditation = ["naac", "nirf"]
    school.recognition_approval = ["ugc", "aicte"]
    school.institution_type = "school"
    school.accommodation_type = ["day_general", "day_boarding"]
    school.admission_process = ["direct", "merit_mark_based"]
    school.hostel = ["boys", "girls"]
    school.computer_lab = "yes"
    school.library = "under_development"
    school.transportation_facility = "available"
    school.playground_facility = "outdoor"
    school.have_cctv_in_campus = "partial_coverage"
    school.medical_faculties = "first_aid"
    school.have_scholarship_opportunities = "available"
    school.have_extra_curricular_activities = "available"
    school.lms_facility = "integrated"
    monkeypatch.setattr(
        school_routes,
        "_get_school_public_or_auth",
        lambda _user, _db, _school_id: school,
    )

    response = school_routes.get_school_self(
        school_id=school.id,
        db=_Database(),
        current_user=None,
    )

    for field in (
        "city",
        "accreditation",
        "recognition_approval",
        "institution_type",
        "accommodation_type",
        "admission_process",
        "hostel",
        "computer_lab",
        "library",
        "transportation_facility",
        "playground_facility",
        "have_cctv_in_campus",
        "medical_faculties",
        "have_scholarship_opportunities",
        "have_extra_curricular_activities",
        "lms_facility",
    ):
        assert response[field] == getattr(school, field)


def test_update_route_accepts_empty_arrays_and_does_not_change_omitted_fields(monkeypatch):
    school = _school()
    monkeypatch.setattr(
        school_routes,
        "_get_school_for_admin_or_school",
        lambda _user, _db, _school_id: school,
    )

    body = {
        "accreditation": [],
        "admission_process": [],
        "hostel": [],
    }
    response = asyncio.run(
        school_routes.update_school_profile(
            request=_Request(body),
            data=SchoolProfileUpdate(**body),
            school_id=None,
            db=_Database(),
            current_user=SimpleNamespace(role=school_routes.UserRole.ADMIN, id=1),
        )
    )

    assert school.accreditation == []
    assert school.admission_process == []
    assert school.hostel == []
    assert school.have_digital_board == "no"
    assert response["profile"]["accreditation"] == []
