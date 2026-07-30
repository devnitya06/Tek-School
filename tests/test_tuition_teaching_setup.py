from datetime import date, time
from uuid import uuid4

from app.crud.tuition.teaching_setup import list_teaching_setups
from app.db.session import SessionLocal
from app.models.tuition.class_sessions import TuitionTeachingSetupClassSession
from app.models.tuition.teaching_setup import TuitionTeachingSetup
from app.models.users import User
from app.routes.tuition.class_sessions import list_class_sessions_endpoint
from app.models.tuition.teaching_setup import TuitionTeachingSetupRating
from app.schemas.tuition.class_sessions import (
    ClassSessionListResponse,
    TeachingSetupClassSessionCreate,
    TeachingSetupClassSessionUpdate,
)
from app.schemas.tuition.teaching_setup import TeachingSetupRatingCreate
from app.schemas.tuition.teaching_setup import TeachingSetupCreate, TeachingSetupUpdate
from app.schemas.users import UserRole
from app.services.tuition.teaching_setup import (
    ensure_teacher_scope,
    submit_teaching_setup_rating_service,
    update_teaching_setup_service,
)
from app.services.tuition.class_sessions import (
    create_class_session_service,
    list_class_sessions_service,
    update_class_session_service,
)


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


def test_list_class_sessions_endpoint_returns_class_session_list_response(monkeypatch):
    class DummyTeachingSetup:
        id = "TS-ROUTE-TEST"
        tuition_from_time = time(18, 0)
        tuition_to_time = time(19, 0)
        tuition_days = ["MONDAY"]
        meeting_link = "https://meet.example.com"
        created_by_user_id = None
        created_by_teacher_id = None
        created_by_self_signed_teacher_id = None

    monkeypatch.setattr("app.routes.tuition.class_sessions.get_teaching_setup", lambda db, teaching_setup_id: DummyTeachingSetup())
    monkeypatch.setattr("app.routes.tuition.class_sessions._ensure_access", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.routes.tuition.class_sessions.list_class_sessions_service", lambda db, teaching_setup: [])

    response = list_class_sessions_endpoint(
        teaching_setup_id="TS-ROUTE-TEST",
        db=object(),
        current_user=object(),
    )

    assert isinstance(response, ClassSessionListResponse)
    assert response.teaching_setup_id == "TS-ROUTE-TEST"
    assert response.sessions == []


def test_teaching_setup_rating_is_created_and_overwritten_by_same_user():
    db = SessionLocal()
    setup = TuitionTeachingSetup(
        id=f"TS-RATING-TEST-{uuid4().hex[:8]}",
        lesson_plan_id="LPNTKVBPBK",
        batch_id="IDGHRKIQ82",
        teaching_mode="ONLINE_CLASS_AND_STUDY_MATERIALS",
        status="ACTIVE",
        created_by_user_id=999,
    )
    db.add(setup)
    db.commit()
    db.refresh(setup)

    user = User(id=777, name="Test Student", email="student-rating@example.com", phone="1234567890", role=UserRole.STUDENT)
    db.add(user)
    db.flush()

    class DummyUser:
        id = user.id
        role = UserRole.STUDENT
        student_profile = type("Profile", (), {"id": 1})()

    try:
        first = submit_teaching_setup_rating_service(
            db,
            current_user=DummyUser(),
            teaching_setup=setup,
            payload=TeachingSetupRatingCreate(rating=5),
        )
        assert first.rating == 5
        assert first.teaching_setup_id == setup.id

        second = submit_teaching_setup_rating_service(
            db,
            current_user=DummyUser(),
            teaching_setup=setup,
            payload=TeachingSetupRatingCreate(rating=3),
        )
        assert second.rating == 3
        assert db.query(TuitionTeachingSetupRating).filter(TuitionTeachingSetupRating.teaching_setup_id == setup.id).count() == 1
    finally:
        db.rollback()
        db.query(TuitionTeachingSetupRating).filter(TuitionTeachingSetupRating.teaching_setup_id == setup.id).delete(synchronize_session=False)
        db.query(TuitionTeachingSetup).filter(TuitionTeachingSetup.id == setup.id).delete(synchronize_session=False)
        db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
        db.commit()


def test_class_session_service_supports_list_start_and_update():
    db = SessionLocal()
    setup = TuitionTeachingSetup(
        id=f"TS-CLASS-SESSION-TEST-{uuid4().hex[:8]}",
        lesson_plan_id="LPNTKVBPBK",
        batch_id="IDGHRKIQ82",
        teaching_mode="ONLINE_CLASS_AND_STUDY_MATERIALS",
        status="ACTIVE",
        created_by_user_id=888,
        created_by_self_signed_teacher_id=321,
    )
    db.add(setup)
    db.commit()
    db.refresh(setup)

    class DummyUser:
        id = 888
        role = UserRole.SELF_SIGNED_TEACHER
        self_signed_teacher_profile = type("Profile", (), {"id": 321})()

    try:
        started = create_class_session_service(
            db,
            current_user=DummyUser(),
            teaching_setup=setup,
            payload=TeachingSetupClassSessionCreate(session_date="2026-08-10"),
        )
        assert started.status == "IN_PROGRESS"
        assert started.session_date == date(2026, 8, 10)

        listed = list_class_sessions_service(db, teaching_setup=setup)
        assert len(listed) == 1
        assert listed[0].session_date == date(2026, 8, 10)

        updated = update_class_session_service(
            db,
            current_user=DummyUser(),
            teaching_setup=setup,
            session_date="2026-08-10",
            payload=TeachingSetupClassSessionUpdate(status="COMPLETED", notes="Done"),
        )
        assert updated.status == "COMPLETED"
        assert updated.notes == "Done"
    finally:
        db.rollback()
        db.query(TuitionTeachingSetupClassSession).filter(
            TuitionTeachingSetupClassSession.teaching_setup_id == setup.id
        ).delete(synchronize_session=False)
        db.query(TuitionTeachingSetup).filter(TuitionTeachingSetup.id == setup.id).delete(synchronize_session=False)
        db.commit()
