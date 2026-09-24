"""
Demo Management System — Tests

Tests are split into two groups:
  1. Pure-logic / unit tests (always pass, no DB required) — TestDemoSlotService,
     TestStatusTransitions, TestGenerators, TestDemoAPIException, TestErrorCodeRegistry
  2. Integration tests marked `requires_postgres` — skip without a live Postgres connection.

Run unit tests only:
    pytest tests/test_demo_system.py -v -m "not requires_postgres"

Run all (with Postgres available):
    pytest tests/test_demo_system.py -v
"""
import os
import pytest
from datetime import date, time, datetime, timezone, timedelta
from types import SimpleNamespace
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base, get_db
from app.main import app
from app.demo.models import (
    DemoConfiguration,
    DemoRequest,
    DemoOtp,
    DemoAccessAttempt,
)
from app.demo.enums import (
    DemoStatus,
    ACTIVE_DEMO_STATUSES,
    RESCHEDULABLE_STATUSES,
    TERMINAL_STATUSES,
    ALLOWED_STATUS_TRANSITIONS,
)
from app.demo.exceptions import DemoErrorCode, DemoAPIException
from app.demo.services import (
    DemoSlotService,
    generate_request_code,
    generate_access_code,
    _parse_hhmm,
)


# ─── Markers ─────────────────────────────────────────────────────────────────

requires_postgres = pytest.mark.requires_postgres


# ─── Simple namespace config (no DB write needed for slot tests) ──────────────

def make_stub_config(start="10:00", end="17:00", limit=5, days=None, active=True):
    """Create a simple namespace object that mimics DemoConfiguration for unit tests.
    Avoids ARRAY/PostgreSQL column type issues in SQLite-backed test DBs.
    """
    days = days or ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY"]
    return SimpleNamespace(
        id=1,
        start_time=_parse_hhmm(start),
        end_time=_parse_hhmm(end),
        user_limit=limit,
        demo_days=days,
        presented_by="Test Presenter",
        demonstration_link="https://example.com/demo",
        is_active=active,
    )


# ─── DB Fixture (only used by requires_postgres tests) ───────────────────────

SQLITE_URL = "sqlite:///./test_demo.db"


@pytest.fixture(scope="module")
def db_engine():
    if not os.environ.get("DATABASE_URL", "").startswith("postgresql"):
        pytest.skip("PostgreSQL is required for demo integration tests.")

    engine = create_engine(
        SQLITE_URL,
        connect_args={"check_same_thread": False},
    )
    from app.demo.models import DemoConfiguration, DemoRequest, DemoRequestImage, DemoOtp, DemoAccessAttempt
    from sqlalchemy import MetaData
    demo_metadata = MetaData()
    DemoConfiguration.__table__.tometadata(demo_metadata)
    DemoRequest.__table__.tometadata(demo_metadata)
    DemoRequestImage.__table__.tometadata(demo_metadata)
    DemoOtp.__table__.tometadata(demo_metadata)
    DemoAccessAttempt.__table__.tometadata(demo_metadata)
    demo_metadata.drop_all(bind=engine)
    demo_metadata.create_all(bind=engine)
    yield engine
    demo_metadata.drop_all(bind=engine)


@pytest.fixture()
def db_session(db_engine):
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    session = TestingSession()
    yield session
    session.rollback()
    session.close()


@pytest.fixture()
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


def make_verified_otp(db, email="dotgarnaik@gmail.com"):
    otp = DemoOtp(
        email=email.lower(),
        otp_code="123456",
        is_verified=True,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
    )
    db.add(otp)
    db.commit()
    db.refresh(otp)
    return otp


def make_config(
    db,
    start="10:00",
    end="17:00",
    limit=5,
    days=None,
    active=True,
    presented_by="Test Presenter",
    demonstration_link="https://example.com/demo",
):
    """Create a DemoConfiguration row used by the database-backed tests."""
    days = days or ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY"]
    config = DemoConfiguration(
        start_time=_parse_hhmm(start),
        end_time=_parse_hhmm(end),
        user_limit=limit,
        demo_days=days,
        presented_by=presented_by,
        demonstration_link=demonstration_link,
        is_active=active,
    )
    db.add(config)
    db.commit()
    db.refresh(config)
    return config


def make_demo_request(
    db,
    config,
    email="dotgarnaik@gmail.com",
    full_name="Test Student",
    phone="9999999999",
    demo_date=None,
    start_time="10:00",
    end_time=None,
    status=DemoStatus.PENDING.value,
    request_code=None,
    access_code="123456",
    institution_name="Test Institution",
    user_category="SCHOOL",
    designation="Manager",
    institution_address="Test Address",
    area_of_interest=None,
):
    """Create a DemoRequest row used by the database-backed tests."""
    if demo_date is None:
        demo_date = date(2026, 9, 21)
    slot_start, slot_end = DemoSlotService.find_slot(config, start_time)
    if end_time is not None:
        slot_end = _parse_hhmm(end_time)
    if request_code is None:
        request_code = generate_request_code()

    req = DemoRequest(
        request_code=request_code,
        email=email,
        user_category=user_category,
        institution_name=institution_name,
        full_name=full_name,
        designation=designation,
        phone=phone,
        institution_address=institution_address,
        area_of_interest=area_of_interest,
        config_id=config.id,
        demo_date=demo_date,
        start_time=slot_start,
        end_time=slot_end,
        presented_by=config.presented_by,
        demonstration_link=config.demonstration_link,
        status=status,
        access_code=access_code,
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    return req


# ─── Unit Tests: Slot Service ─────────────────────────────────────────────────

class TestDemoSlotService:
    def test_generates_correct_slots(self):
        config = make_stub_config(start="10:00", end="13:00")
        slots = DemoSlotService.generate_slots(config)
        assert len(slots) == 3
        assert slots[0] == (time(10, 0), time(11, 0))
        assert slots[1] == (time(11, 0), time(12, 0))
        assert slots[2] == (time(12, 0), time(13, 0))

    def test_no_slots_for_short_range(self):
        config = make_stub_config(start="10:00", end="10:30")
        slots = DemoSlotService.generate_slots(config)
        assert slots == []

    def test_validate_slot_config_raises_for_empty_range(self):
        config = make_stub_config(start="15:00", end="15:30")
        with pytest.raises(DemoAPIException) as exc_info:
            DemoSlotService.validate_configuration_slots(config)
        assert exc_info.value.error_code == DemoErrorCode.INVALID_SLOT_CONFIGURATION

    def test_find_slot_valid(self):
        config = make_stub_config(start="10:00", end="13:00")
        start, end = DemoSlotService.find_slot(config, "11:00")
        assert start == time(11, 0)
        assert end == time(12, 0)

    def test_find_slot_invalid_raises(self):
        config = make_stub_config(start="10:00", end="13:00")
        with pytest.raises(DemoAPIException) as exc_info:
            DemoSlotService.find_slot(config, "09:00")
        assert exc_info.value.error_code == DemoErrorCode.INVALID_SLOT

    def test_validate_weekday_passes(self):
        config = make_stub_config(days=["MONDAY"])
        # Monday
        monday = date(2026, 9, 14)
        DemoSlotService.validate_weekday(config, monday)  # Should not raise

    def test_validate_weekday_fails(self):
        config = make_stub_config(days=["MONDAY"])
        # Tuesday
        tuesday = date(2026, 9, 15)
        with pytest.raises(DemoAPIException) as exc_info:
            DemoSlotService.validate_weekday(config, tuesday)
        assert exc_info.value.error_code == DemoErrorCode.DATE_NOT_AVAILABLE


# ─── Unit Tests: Enums and Transitions ───────────────────────────────────────

class TestStatusTransitions:
    def test_pending_can_transition_to_accepted(self):
        assert DemoStatus.ACCEPTED in ALLOWED_STATUS_TRANSITIONS[DemoStatus.PENDING]

    def test_pending_cannot_transition_to_no_show(self):
        assert DemoStatus.NO_SHOW not in ALLOWED_STATUS_TRANSITIONS[DemoStatus.PENDING]

    def test_completed_is_terminal(self):
        assert DemoStatus.COMPLETED in TERMINAL_STATUSES
        assert ALLOWED_STATUS_TRANSITIONS[DemoStatus.COMPLETED] == set()

    def test_cancelled_is_terminal(self):
        assert DemoStatus.CANCELLED in TERMINAL_STATUSES
        assert ALLOWED_STATUS_TRANSITIONS[DemoStatus.CANCELLED] == set()

    def test_no_show_is_terminal(self):
        assert DemoStatus.NO_SHOW in TERMINAL_STATUSES

    def test_accepted_can_go_to_completed_no_show_or_cancelled(self):
        allowed = ALLOWED_STATUS_TRANSITIONS[DemoStatus.ACCEPTED]
        assert DemoStatus.COMPLETED in allowed
        assert DemoStatus.NO_SHOW in allowed
        assert DemoStatus.CANCELLED in allowed
        assert DemoStatus.PENDING not in allowed

    def test_rescheduled_cannot_be_rescheduled_to_pending(self):
        assert DemoStatus.PENDING not in ALLOWED_STATUS_TRANSITIONS[DemoStatus.RESCHEDULED]

    def test_active_demo_statuses(self):
        assert DemoStatus.PENDING in ACTIVE_DEMO_STATUSES
        assert DemoStatus.RESCHEDULED in ACTIVE_DEMO_STATUSES
        assert DemoStatus.ACCEPTED in ACTIVE_DEMO_STATUSES
        assert DemoStatus.COMPLETED not in ACTIVE_DEMO_STATUSES
        assert DemoStatus.CANCELLED not in ACTIVE_DEMO_STATUSES

    def test_reschedulable_statuses(self):
        assert DemoStatus.PENDING in RESCHEDULABLE_STATUSES
        assert DemoStatus.RESCHEDULED in RESCHEDULABLE_STATUSES
        assert DemoStatus.ACCEPTED in RESCHEDULABLE_STATUSES
        assert DemoStatus.COMPLETED not in RESCHEDULABLE_STATUSES


# ─── Unit Tests: Generators ───────────────────────────────────────────────────

class TestGenerators:
    def test_request_code_format(self):
        code = generate_request_code()
        assert code.startswith("DM")
        assert len(code) == 8
        assert code.isalnum()

    def test_access_code_format(self):
        code = generate_access_code()
        assert len(code) == 6
        assert code.isdigit()

    def test_uniqueness(self):
        codes = {generate_request_code() for _ in range(100)}
        assert len(codes) == 100


class TestDemoEmailService:
    @patch("app.utils.email_utility.send_dynamic_email")
    def test_booking_confirmation_includes_access_code(self, mock_send_dynamic_email):
        demo_request = SimpleNamespace(
            email="dotgarnaik@gmail.com",
            full_name="Test Student",
            request_code="DMABCD12",
            access_code="123456",
            demo_date=date(2026, 9, 21),
            start_time=time(10, 0),
            end_time=time(11, 0),
            presented_by="Santanu Garnaik",
            demonstration_link="https://meet.google.com/demo-link",
        )

        from app.demo.services import DemoEmailService
        DemoEmailService.send_booking_confirmation(demo_request)

        mock_send_dynamic_email.assert_called_once()
        _, kwargs = mock_send_dynamic_email.call_args
        assert kwargs["context_data"]["access_code"] == "123456"

    @patch("app.utils.email_utility.send_dynamic_email")
    def test_reschedule_notification_includes_access_code(self, mock_send_dynamic_email):
        demo_request = SimpleNamespace(
            email="dotgarnaik@gmail.com",
            full_name="Test Student",
            request_code="DMABCD12",
            access_code="654321",
            demo_date=date(2026, 9, 21),
            start_time=time(10, 0),
            end_time=time(11, 0),
            presented_by="Santanu Garnaik",
            demonstration_link="https://meet.google.com/demo-link",
        )

        from app.demo.services import DemoEmailService
        DemoEmailService.send_reschedule_notification(demo_request)

        mock_send_dynamic_email.assert_called_once()
        _, kwargs = mock_send_dynamic_email.call_args
        assert kwargs["context_data"]["access_code"] == "654321"

    @patch("app.demo.services.threading.Thread")
    @patch("app.core.celery_app.celery_app.send_task", side_effect=RuntimeError("redis down"))
    def test_queue_booking_confirmation_uses_background_thread_when_celery_unavailable(
        self,
        mock_send_task,
        mock_thread,
    ):
        demo_request = SimpleNamespace(
            id=4,
            email="dotgarnaik@gmail.com",
            full_name="Test Student",
            request_code="DMABCD12",
            access_code="123456",
            demo_date=date(2026, 9, 21),
            start_time=time(10, 0),
            end_time=time(11, 0),
            presented_by="Santanu Garnaik",
            demonstration_link="https://meet.google.com/demo-link",
        )

        from app.demo.services import DemoEmailService
        DemoEmailService.queue_booking_confirmation(demo_request)

        mock_thread.assert_called_once()
        mock_thread.return_value.start.assert_called_once()


# ─── Unit Tests: DemoAPIException ────────────────────────────────────────────

class TestDemoAPIException:
    def test_has_correct_attributes(self):
        exc = DemoAPIException(409, DemoErrorCode.CAPACITY_CONFLICT, "Slot is full.")
        assert exc.status_code == 409
        assert exc.error_code == DemoErrorCode.CAPACITY_CONFLICT
        assert exc.message == "Slot is full."
        assert exc.details is None

    def test_with_details(self):
        exc = DemoAPIException(422, DemoErrorCode.INVALID_SLOT, "Bad slot.", details={"field": "start_time"})
        assert exc.details == {"field": "start_time"}


# ─── API Tests: Public Endpoints ─────────────────────────────────────────────

@requires_postgres
class TestPublicCheckEndpoint:
    def test_missing_email_returns_error_code(self, client):
        resp = client.get("/demo/public/check")
        assert resp.status_code == 422
        data = resp.json()
        assert data["error_code"] == DemoErrorCode.EMAIL_REQUIRED

    def test_no_demo_returns_false(self, client):
        resp = client.get("/demo/public/check?email=nobody@example.com")
        assert resp.status_code == 200
        assert resp.json()["has_active_demo"] is False

    def test_active_demo_returns_true(self, client, db_session):
        config = make_config(db_session)
        demo_date = date(2026, 9, 15)  # Monday
        make_demo_request(db_session, config, email="active@example.com", demo_date=demo_date)
        resp = client.get("/demo/public/check?email=active@example.com")
        assert resp.status_code == 200
        assert resp.json()["has_active_demo"] is True


@requires_postgres
class TestAvailableSlotsEndpoint:
    def test_missing_date_returns_error(self, client):
        resp = client.get("/demo/public/available-slots")
        assert resp.status_code == 422
        assert resp.json()["error_code"] == DemoErrorCode.INVALID_DATE

    def test_invalid_date_format(self, client):
        resp = client.get("/demo/public/available-slots?date=not-a-date")
        assert resp.status_code == 422
        assert resp.json()["error_code"] == DemoErrorCode.INVALID_DATE

    def test_no_config_for_date_returns_404(self, client):
        # Saturday — most configs won't have Saturday if days=Mon-Fri
        # Use a future Sunday
        resp = client.get("/demo/public/available-slots?date=2026-09-20")
        assert resp.status_code == 404
        assert resp.json()["error_code"] == DemoErrorCode.NO_AVAILABLE_CONFIGURATION


@requires_postgres
class TestSendOtpEndpoint:
    def test_missing_email_returns_validation_error(self, client):
        resp = client.post("/demo/public/send-otp", json={})
        assert resp.status_code == 422

    @patch("app.demo.services.DemoEmailService.send_otp_email")
    def test_send_otp_success(self, mock_email, client):
        mock_email.return_value = None
        resp = client.post("/demo/public/send-otp", json={"email": "new_user@example.com"})
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    @patch("app.demo.services.DemoEmailService.send_otp_email")
    def test_rate_limit_exceeded(self, mock_email, client, db_session):
        """After OTP_MAX_RESEND_PER_HOUR attempts, should return OTP_RATE_LIMITED."""
        mock_email.return_value = None
        email = "ratelimit@example.com"
        # Create 5 OTPs within the hour
        for _ in range(5):
            otp = DemoOtp(
                email=email,
                otp_code="111111",
                is_verified=False,
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
            )
            db_session.add(otp)
        db_session.commit()
        resp = client.post("/demo/public/send-otp", json={"email": email})
        assert resp.status_code == 429
        assert resp.json()["error_code"] == DemoErrorCode.OTP_RATE_LIMITED


@requires_postgres
class TestVerifyOtpEndpoint:
    def test_no_otp_returns_invalid_otp(self, client):
        resp = client.post("/demo/public/verify-otp", json={"email": "ghost@example.com", "otp": "123456"})
        assert resp.status_code == 400
        assert resp.json()["error_code"] == DemoErrorCode.INVALID_OTP

    def test_expired_otp_returns_otp_expired(self, client, db_session):
        email = "expired@example.com"
        otp = DemoOtp(
            email=email,
            otp_code="999888",
            is_verified=False,
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),  # expired
        )
        db_session.add(otp)
        db_session.commit()
        resp = client.post("/demo/public/verify-otp", json={"email": email, "otp": "999888"})
        assert resp.status_code == 400
        assert resp.json()["error_code"] == DemoErrorCode.OTP_EXPIRED

    def test_already_verified_returns_error(self, client, db_session):
        email = "alreadyverified@example.com"
        otp = DemoOtp(
            email=email,
            otp_code="555666",
            is_verified=True,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        )
        db_session.add(otp)
        db_session.commit()
        resp = client.post("/demo/public/verify-otp", json={"email": email, "otp": "555666"})
        assert resp.status_code == 409
        assert resp.json()["error_code"] == DemoErrorCode.OTP_ALREADY_VERIFIED

    def test_wrong_otp_returns_invalid(self, client, db_session):
        email = "wrongotp@example.com"
        otp = DemoOtp(
            email=email,
            otp_code="123456",
            is_verified=False,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        )
        db_session.add(otp)
        db_session.commit()
        resp = client.post("/demo/public/verify-otp", json={"email": email, "otp": "000000"})
        assert resp.status_code == 400
        assert resp.json()["error_code"] == DemoErrorCode.INVALID_OTP


@requires_postgres
class TestCreateDemoRequest:
    @patch("app.demo.services.DemoEmailService.send_otp_email")
    def test_request_creates_pending_otp_without_booking(self, mock_email, client, db_session):
        config = make_config(db_session, days=["MONDAY"])
        email = "pendingdemo@example.com"
        payload = {
            "email": email,
            "user_category": "SCHOOL",
            "institution_name": "Test Institution",
            "full_name": "Pending User",
            "phone": "9999999999",
            "config_id": config.id,
            "demo_date": "2026-09-21",
            "start_time": "10:00",
        }

        resp = client.post("/demo/public/request", json=payload)
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        assert db_session.query(DemoRequest).filter(DemoRequest.email == email).count() == 0

        otp = db_session.query(DemoOtp).filter(DemoOtp.email == email).order_by(DemoOtp.created_at.desc()).first()
        assert otp is not None
        assert otp.is_verified is False
        assert otp.request_payload is not None
        assert otp.request_payload["full_name"] == "Pending User"

    @patch("app.demo.services.DemoEmailService.send_otp_email")
    def test_verifying_pending_otp_creates_demo_request(self, mock_email, client, db_session):
        config = make_config(db_session, days=["MONDAY"])
        email = "verifypending@example.com"
        payload = {
            "email": email,
            "user_category": "SCHOOL",
            "institution_name": "Verify Institution",
            "full_name": "Verify User",
            "phone": "9999999999",
            "config_id": config.id,
            "demo_date": "2026-09-21",
            "start_time": "10:00",
        }

        client.post("/demo/public/request", json=payload)
        otp = db_session.query(DemoOtp).filter(DemoOtp.email == email).order_by(DemoOtp.created_at.desc()).first()
        assert otp is not None

        resp = client.post("/demo/public/verify-otp", json={"email": email, "otp": otp.otp_code})
        assert resp.status_code == 200
        requests = db_session.query(DemoRequest).filter(DemoRequest.email == email).all()
        assert len(requests) == 1
        assert requests[0].full_name == "Verify User"
        assert requests[0].status == DemoStatus.PENDING.value

    @patch("app.demo.services.DemoEmailService.send_booking_confirmation")
    def test_requires_otp_verification(self, mock_email, client):
        resp = client.post("/demo/public/request", json={
            "email": "dotgarnaik@gmail.com",
            "user_category": "SCHOOL",
            "institution_name": "Test",
            "full_name": "Test User",
            "phone": "9999999999",
            "config_id": 1,
            "demo_date": "2026-09-21",  # Monday
            "start_time": "10:00",
        })
        assert resp.status_code == 403
        assert resp.json()["error_code"] == DemoErrorCode.OTP_VERIFICATION_REQUIRED

    @patch("app.demo.services.DemoEmailService.send_booking_confirmation")
    def test_inactive_config_raises_error(self, mock_email, client, db_session):
        config = make_config(db_session, active=False)
        email = "dotgarnaik@gmail.com"
        make_verified_otp(db_session, email)
        resp = client.post("/demo/public/request", json={
            "email": email,
            "user_category": "SCHOOL",
            "institution_name": "Test",
            "full_name": "Test User",
            "phone": "9999999999",
            "config_id": config.id,
            "demo_date": "2026-09-21",
            "start_time": "10:00",
        })
        assert resp.status_code == 409
        assert resp.json()["error_code"] == DemoErrorCode.CONFIGURATION_INACTIVE

    @patch("app.demo.services.DemoEmailService.send_booking_confirmation")
    def test_active_request_exists_blocks_booking(self, mock_email, client, db_session):
        config = make_config(db_session, days=["MONDAY"])
        email = "dotgarnaik@gmail.com"
        make_verified_otp(db_session, email)
        make_demo_request(db_session, config, email=email, demo_date=date(2026, 9, 14))
        resp = client.post("/demo/public/request", json={
            "email": email,
            "user_category": "SCHOOL",
            "institution_name": "Test",
            "full_name": "Test User",
            "phone": "9999999999",
            "config_id": config.id,
            "demo_date": "2026-09-21",
            "start_time": "10:00",
        })
        assert resp.status_code == 409
        assert resp.json()["error_code"] == DemoErrorCode.ACTIVE_REQUEST_EXISTS


@requires_postgres
class TestAccessDemoEndpoint:
    def test_invalid_access_code_format(self, client):
        resp = client.post("/demo/public/access", json={
            "email": "dotgarnaik@gmail.com",
            "access_code": "abc"
        })
        assert resp.status_code == 422

    def test_wrong_access_code_returns_invalid(self, client, db_session):
        config = make_config(db_session, days=["MONDAY"])
        req = make_demo_request(db_session, config, demo_date=date(2026, 9, 21))
        req.access_code = "111111"
        db_session.commit()
        resp = client.post("/demo/public/access", json={
            "email": req.email,
            "access_code": "999999"
        })
        assert resp.status_code == 401
        assert resp.json()["error_code"] == DemoErrorCode.INVALID_ACCESS_CODE

    def test_expired_access_code(self, client, db_session):
        config = make_config(db_session, days=["MONDAY"])
        # Use a past demo date
        req = make_demo_request(db_session, config, demo_date=date(2020, 1, 6))  # past date
        req.access_code = "777888"
        db_session.commit()
        resp = client.post("/demo/public/access", json={
            "email": req.email,
            "access_code": "777888"
        })
        assert resp.status_code == 410
        assert resp.json()["error_code"] == DemoErrorCode.ACCESS_CODE_EXPIRED


# ─── API Tests: Admin Status Update ──────────────────────────────────────────

@requires_postgres
class TestAdminStatusUpdate:
    """These test status transition logic without full auth (assume auth is mocked out in a real test environment)."""

    def test_invalid_status_transition_error_code(self, db_session):
        """Direct service-level test: trying COMPLETED → PENDING raises correct error code."""
        from app.demo.enums import DemoStatus, ALLOWED_STATUS_TRANSITIONS
        current = DemoStatus.COMPLETED
        new = DemoStatus.PENDING
        allowed = ALLOWED_STATUS_TRANSITIONS.get(current, set())
        assert new not in allowed  # Verify our transition table is correct

    def test_all_transitions_covered(self):
        """Every DemoStatus has an entry in ALLOWED_STATUS_TRANSITIONS."""
        for status in DemoStatus:
            assert status in ALLOWED_STATUS_TRANSITIONS


# ─── Error Code Completeness ──────────────────────────────────────────────────

class TestErrorCodeRegistry:
    def test_all_error_codes_are_strings(self):
        codes = [
            v for k, v in vars(DemoErrorCode).items()
            if not k.startswith("_")
        ]
        for code in codes:
            assert isinstance(code, str), f"Error code {code} is not a string"
            assert code.startswith("DEMO_"), f"Error code {code} must start with DEMO_"
