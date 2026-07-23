from app.crud.tuition.teaching_setup import list_teaching_setups
from app.db.session import SessionLocal
from app.models.tuition.teaching_setup import TuitionTeachingSetup
from app.schemas.tuition.teaching_setup import TeachingSetupCreate, TeachingSetupUpdate
from app.schemas.users import UserRole
from app.services.tuition.teaching_setup import ensure_teacher_scope, update_teaching_setup_service


def test_teaching_setup_calculates_final_fees_and_seats():
    setup = TuitionTeachingSetup(
        teaching_mode="ONLINE_CLASS_AND_STUDY_MATERIALS",
        monthly_tuition_fee=1500,
        monthly_tuition_discount=200,
        premium_study_material_fee=100,
        premium_study_material_discount=50,
        maximum_students=30,
    )

    assert setup.final_tuition_fee == 1300
    assert setup.final_premium_fee == 50
    assert setup.available_seats == 30
    assert setup.joined_students_count == 0


def test_teaching_setup_create_accepts_phase_2_payload_fields():
    payload = TeachingSetupCreate(
        teaching_mode="ONLINE_CLASS_AND_STUDY_MATERIALS",
        lesson_plan_id="lesson-plan-1",
        batch_id="batch-1",
        batch_title="Evening Mathematics Batch",
        batch_start_date="2026-08-01",
        batch_end_date="2026-12-31",
        tuition_from_time="18:00",
        tuition_to_time="19:00",
        tuition_days=["MONDAY", "WEDNESDAY", "FRIDAY"],
        languages=["English", "Hindi"],
        monthly_tuition_fee=1500,
        monthly_tuition_discount=200,
        premium_study_material_fee=100,
        premium_study_material_discount=50,
        meeting_provider="GOOGLE_MEET",
        meeting_link="https://meet.google.com/abc-defg-hij",
        online_teaching_ability=True,
        stable_internet_connection=True,
        camera_available=True,
        silent_place_without_background_noise=True,
        laptop_desktop_pc=True,
        headphone_whiteboard=True,
        maximum_students=30,
        status="ACTIVE",
    )

    assert payload.lesson_plan_id == "lesson-plan-1"
    assert payload.batch_title == "Evening Mathematics Batch"
    assert payload.tuition_days == ["MONDAY", "WEDNESDAY", "FRIDAY"]
    assert payload.status == "ACTIVE"


def test_teaching_setup_model_stores_teacher_type():
    setup = TuitionTeachingSetup(teacher_type="SELF_SIGNED_TEACHER")
    assert setup.teacher_type == "SELF_SIGNED_TEACHER"


def test_teaching_setup_model_stores_is_active():
    setup = TuitionTeachingSetup(is_active=True)
    assert setup.is_active is True


def test_ensure_teacher_scope_allows_self_signed_teacher_without_explicit_id():
    class DummyUser:
        role = UserRole.SELF_SIGNED_TEACHER
        self_signed_teacher_profile = type("Profile", (), {"id": 7})()

    assert ensure_teacher_scope(DummyUser(), teacher_id=None, self_signed_teacher_id=None) is True


def test_list_teaching_setups_supports_owner_user_fallback():
    db = SessionLocal()
    setup = TuitionTeachingSetup(
        lesson_plan_id="LPNTKVBPBK",
        batch_id="IDGHRKIQ82",
        teaching_mode="ONLINE_CLASS_AND_STUDY_MATERIALS",
        status="ACTIVE",
        created_by_user_id=9999,
        created_by_self_signed_teacher_id=123,
    )
    db.add(setup)
    db.commit()
    db.refresh(setup)

    try:
        items = list_teaching_setups(db, owner_user_id=9999, include_inactive=True)
        assert any(item.id == setup.id for item in items)
    finally:
        db.delete(setup)
        db.commit()


def test_update_teaching_setup_service_allows_editing_existing_record():
    db = SessionLocal()
    setup = TuitionTeachingSetup(
        lesson_plan_id="LPNTKVBPBK",
        batch_id="IDGHRKIQ82",
        teaching_mode="ONLINE_CLASS_AND_STUDY_MATERIALS",
        status="ACTIVE",
        created_by_user_id=777,
        created_by_self_signed_teacher_id=321,
    )
    db.add(setup)
    db.commit()
    db.refresh(setup)

    try:
        updated = update_teaching_setup_service(
            db,
            teaching_setup=setup,
            payload=TeachingSetupUpdate(meeting_link="https://meet.google.com/updated"),
        )
        assert updated.meeting_link == "https://meet.google.com/updated"
    finally:
        db.delete(setup)
        db.commit()
