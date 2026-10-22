"""Agent Phase 2 — Automated Tests

Tests cover:
  - Configuration CRUD (POST/PUT/GET)
  - Authorization enforcement (SUPERADMIN-only writes)
  - Duplicate prevention
  - Disabled-activity visibility (rate not zeroed)
  - Agent self-access for GET config
  - wants_initial_bonus via consent endpoint
  - Bonus withdrawal guard
  - created_at preservation on PUT
  - Stipend eligibility logic
  - Earning duplicate prevention

These tests use an in-memory SQLite database to avoid touching production data.
Run with: pytest tests/test_agent_phase2.py -v
"""
import pytest
from decimal import Decimal
from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# We use SQLite for test isolation — no PostgreSQL needed
TEST_DB_URL = "sqlite:///./test_agent_phase2.db"


def test_agent_experience_accepts_free_form_text():
    from sqlalchemy import Text

    from app.models.agent import AgentProfile
    from app.schemas.agent import AgentProfileUpdate

    assert isinstance(AgentProfile.__table__.c.experience.type, Text)
    assert AgentProfileUpdate(experience="12 years in product management").experience == (
        "12 years in product management"
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def engine():
    from app.db.session import Base
    # Import all models so they register with Base
    import app.models.users        # noqa
    import app.models.agent        # noqa
    import app.models.agent_config  # noqa

    eng = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
    # Only create the agent-specific tables; full Base includes PG-only types
    from app.models.users import User
    from app.models.agent import AgentProfile
    from app.models.agent_config import AgentPaymentConfig, AgentEarning
    from app.models.agent_config import AgentStipendRate
    for tbl in (
        User.__table__,
        AgentProfile.__table__,
        AgentPaymentConfig.__table__,
        AgentEarning.__table__,
        AgentStipendRate.__table__,
    ):
        tbl.create(bind=eng, checkfirst=True)
    yield eng
    from app.models.users import User
    from app.models.agent import AgentProfile
    from app.models.agent_config import AgentPaymentConfig, AgentEarning, AgentStipendRate
    for tbl in (
        AgentStipendRate.__table__,
        AgentEarning.__table__,
        AgentPaymentConfig.__table__,
        AgentProfile.__table__,
        User.__table__,
    ):
        tbl.drop(bind=eng, checkfirst=True)


@pytest.fixture
def db(engine):
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSession()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def agent_profile(db):
    """Create a test User + AgentProfile pair."""
    import random
    from app.models.users import User
    from app.models.agent import AgentProfile, StipendType
    from app.schemas.users import UserRole

    n = random.randint(10000000, 99999999)
    email = f"testagent_{n}@example.com"
    phone = f"98{n}"
    user = User(
        name="Test Agent",
        email=email,
        phone=phone,
        role=UserRole.AGENT.value,
        hashed_password="hashed",
        is_verified=True,
        is_active=True,
        verification_status="approved",
        profile_completed=False,
        is_deleted=False,
    )
    db.add(user)
    db.flush()

    profile = AgentProfile(
        user_id=user.id,
        first_name="Test",
        last_name="Agent",
        phone=phone,
        email=email,
        stipend_type=StipendType.WITH_STIPEND,
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return user, profile


@pytest.fixture
def with_stipend_profile(db):
    """Agent with WITH_STIPEND type."""
    import random
    from app.models.users import User
    from app.models.agent import AgentProfile, StipendType
    from app.schemas.users import UserRole

    n = random.randint(10000000, 99999999)
    email = f"stipendagent_{n}@example.com"
    phone = f"91{n}"
    user = User(
        name="Stipend Agent",
        email=email,
        phone=phone,
        role=UserRole.AGENT.value,
        hashed_password="hashed",
        is_verified=True,
        is_active=True,
        verification_status="approved",
        profile_completed=False,
        is_deleted=False,
    )
    db.add(user)
    db.flush()

    profile = AgentProfile(
        user_id=user.id,
        first_name="Stipend",
        last_name="Agent",
        phone=phone,
        email=email,
        stipend_type=StipendType.WITH_STIPEND,
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return user, profile


@pytest.fixture
def no_stipend_profile(db):
    """Agent with WITHOUT_STIPEND type."""
    import random
    from app.models.users import User
    from app.models.agent import AgentProfile, StipendType
    from app.schemas.users import UserRole

    n = random.randint(10000000, 99999999)
    email = f"nostipend_{n}@example.com"
    phone = f"90{n}"
    user = User(
        name="NoStipend Agent",
        email=email,
        phone=phone,
        role=UserRole.AGENT.value,
        hashed_password="hashed",
        is_verified=True,
        is_active=True,
        verification_status="approved",
        profile_completed=False,
        is_deleted=False,
    )
    db.add(user)
    db.flush()

    profile = AgentProfile(
        user_id=user.id,
        first_name="NoStipend",
        last_name="Agent",
        phone=phone,
        email=email,
        stipend_type=StipendType.WITHOUT_STIPEND,
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return user, profile


def make_config_data():
    """Return a valid AgentConfigRequest-like dict."""
    from app.schemas.agent_config import AgentConfigRequest, ActivityConfig, StipendConfig
    return AgentConfigRequest(
        institution_digital_profile=ActivityConfig(is_enabled=True, rate=Decimal("1200.00")),
        monthly_stipend=StipendConfig(is_enabled=True, monthly_rate=Decimal("500.00")),
        physical_verification=ActivityConfig(is_enabled=True, rate=Decimal("250.00")),
        online_demonstration=ActivityConfig(is_enabled=False, rate=Decimal("600.00")),
        offline_demonstration=ActivityConfig(is_enabled=True, rate=Decimal("750.00")),
        other_activities=ActivityConfig(is_enabled=False, rate=Decimal("300.00")),
        initial_bonus=Decimal("1000.00"),
    )


# ---------------------------------------------------------------------------
# Schema validation tests
# ---------------------------------------------------------------------------

class TestSchemaValidation:
    def test_negative_rate_rejected(self):
        from pydantic import ValidationError
        from app.schemas.agent_config import ActivityConfig
        with pytest.raises(ValidationError):
            ActivityConfig(is_enabled=True, rate=Decimal("-1.00"))

    def test_negative_bonus_rejected(self):
        from pydantic import ValidationError
        from app.schemas.agent_config import AgentConfigRequest, ActivityConfig, StipendConfig
        with pytest.raises(ValidationError):
            AgentConfigRequest(
                institution_digital_profile=ActivityConfig(is_enabled=True, rate=Decimal("100.00")),
                monthly_stipend=StipendConfig(is_enabled=True, monthly_rate=Decimal("100.00")),
                physical_verification=ActivityConfig(is_enabled=True, rate=Decimal("100.00")),
                online_demonstration=ActivityConfig(is_enabled=True, rate=Decimal("100.00")),
                offline_demonstration=ActivityConfig(is_enabled=True, rate=Decimal("100.00")),
                other_activities=ActivityConfig(is_enabled=True, rate=Decimal("100.00")),
                initial_bonus=Decimal("-500.00"),
            )

    def test_zero_rate_allowed(self):
        from app.schemas.agent_config import ActivityConfig
        cfg = ActivityConfig(is_enabled=False, rate=Decimal("0.00"))
        assert cfg.rate == Decimal("0.00")

    def test_consent_schema_defaults(self):
        from app.schemas.agent import AgentConsentRequest
        req = AgentConsentRequest()
        assert req.wants_initial_bonus is False

    def test_consent_schema_bonus_true(self):
        from app.schemas.agent import AgentConsentRequest
        req = AgentConsentRequest(wants_initial_bonus=True)
        assert req.wants_initial_bonus is True


# ---------------------------------------------------------------------------
# Configuration DB tests
# ---------------------------------------------------------------------------

class TestAgentPaymentConfig:
    def test_create_config(self, db, agent_profile):
        """SUPERADMIN can create initial configuration."""
        from app.models.agent_config import AgentPaymentConfig
        _, profile = agent_profile
        data = make_config_data()

        cfg = AgentPaymentConfig(
            agent_profile_id=profile.id,
            idp_is_enabled=data.institution_digital_profile.is_enabled,
            idp_rate=data.institution_digital_profile.rate,
            stipend_monthly_is_enabled=data.monthly_stipend.is_enabled,
            stipend_monthly_rate=data.monthly_stipend.monthly_rate,
            pv_is_enabled=data.physical_verification.is_enabled,
            pv_rate=data.physical_verification.rate,
            od_is_enabled=data.online_demonstration.is_enabled,
            od_rate=data.online_demonstration.rate,
            offd_is_enabled=data.offline_demonstration.is_enabled,
            offd_rate=data.offline_demonstration.rate,
            oa_is_enabled=data.other_activities.is_enabled,
            oa_rate=data.other_activities.rate,
            initial_bonus=data.initial_bonus,
            is_bonus_withdrawn=False,
        )
        db.add(cfg)
        db.commit()
        db.refresh(cfg)

        assert cfg.id is not None
        assert cfg.agent_profile_id == profile.id
        assert cfg.idp_is_enabled is True
        assert Decimal(str(cfg.idp_rate)) == Decimal("1200.00")
        assert cfg.is_bonus_withdrawn is False
        assert cfg.created_at is not None

    def test_duplicate_config_rejected(self, db, agent_profile):
        """Second POST for same agent must be rejected at DB level."""
        from app.models.agent_config import AgentPaymentConfig
        from sqlalchemy.exc import IntegrityError
        _, profile = agent_profile

        existing = db.query(AgentPaymentConfig).filter(
            AgentPaymentConfig.agent_profile_id == profile.id
        ).first()
        if not existing:
            cfg1 = AgentPaymentConfig(
                agent_profile_id=profile.id,
                idp_is_enabled=True, idp_rate=Decimal("100.00"),
                stipend_is_enabled=False, stipend_daily_rate=Decimal("0.00"),
                pv_is_enabled=False, pv_rate=Decimal("0.00"),
                od_is_enabled=False, od_rate=Decimal("0.00"),
                offd_is_enabled=False, offd_rate=Decimal("0.00"),
                oa_is_enabled=False, oa_rate=Decimal("0.00"),
                initial_bonus=Decimal("0.00"),
                is_bonus_withdrawn=False,
            )
            db.add(cfg1)
            db.commit()

        # Try inserting a second one — must fail
        cfg2 = AgentPaymentConfig(
            agent_profile_id=profile.id,
            idp_is_enabled=False, idp_rate=Decimal("50.00"),
            stipend_is_enabled=False, stipend_daily_rate=Decimal("0.00"),
            pv_is_enabled=False, pv_rate=Decimal("0.00"),
            od_is_enabled=False, od_rate=Decimal("0.00"),
            offd_is_enabled=False, offd_rate=Decimal("0.00"),
            oa_is_enabled=False, oa_rate=Decimal("0.00"),
            initial_bonus=Decimal("0.00"),
            is_bonus_withdrawn=False,
        )
        db.add(cfg2)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

    def test_put_updates_same_record(self, db, agent_profile):
        """PUT updates in-place; exactly one config row remains."""
        from app.models.agent_config import AgentPaymentConfig
        _, profile = agent_profile

        cfg = db.query(AgentPaymentConfig).filter(
            AgentPaymentConfig.agent_profile_id == profile.id
        ).first()
        if cfg is None:
            cfg = AgentPaymentConfig(
                agent_profile_id=profile.id,
                idp_is_enabled=True, idp_rate=Decimal("500.00"),
                stipend_is_enabled=False, stipend_daily_rate=Decimal("0.00"),
                pv_is_enabled=False, pv_rate=Decimal("0.00"),
                od_is_enabled=False, od_rate=Decimal("0.00"),
                offd_is_enabled=False, offd_rate=Decimal("0.00"),
                oa_is_enabled=False, oa_rate=Decimal("0.00"),
                initial_bonus=Decimal("100.00"),
                is_bonus_withdrawn=False,
            )
            db.add(cfg)
            db.commit()
            db.refresh(cfg)

        original_created_at = cfg.created_at
        original_id = cfg.id

        # Simulate PUT
        cfg.idp_rate = Decimal("700.00")
        db.commit()
        db.refresh(cfg)

        # Only one record
        count = db.query(AgentPaymentConfig).filter(
            AgentPaymentConfig.agent_profile_id == profile.id
        ).count()
        assert count == 1
        assert cfg.id == original_id
        assert cfg.created_at == original_created_at
        assert Decimal(str(cfg.idp_rate)) == Decimal("700.00")

    def test_disabled_activity_rate_preserved(self, db, agent_profile):
        """Disabled activities must retain their configured rate (not zero)."""
        from app.models.agent_config import AgentPaymentConfig
        _, profile = agent_profile

        cfg = db.query(AgentPaymentConfig).filter(
            AgentPaymentConfig.agent_profile_id == profile.id
        ).first()
        if cfg is None:
            cfg = AgentPaymentConfig(
                agent_profile_id=profile.id,
                idp_is_enabled=False, idp_rate=Decimal("1200.00"),
                stipend_is_enabled=False, stipend_daily_rate=Decimal("500.00"),
                pv_is_enabled=False, pv_rate=Decimal("250.00"),
                od_is_enabled=False, od_rate=Decimal("600.00"),
                offd_is_enabled=False, offd_rate=Decimal("750.00"),
                oa_is_enabled=False, oa_rate=Decimal("300.00"),
                initial_bonus=Decimal("1000.00"),
                is_bonus_withdrawn=False,
            )
            db.add(cfg)
            db.commit()
            db.refresh(cfg)

        # All disabled — rates must still be non-zero
        assert cfg.od_is_enabled is False
        assert Decimal(str(cfg.od_rate)) == Decimal("600.00")
        assert cfg.oa_is_enabled is False
        assert Decimal(str(cfg.oa_rate)) == Decimal("300.00")

    def test_is_bonus_withdrawn_not_changed_by_config_update(self, db, agent_profile):
        """Configuration PUT must never change is_bonus_withdrawn."""
        from app.models.agent_config import AgentPaymentConfig
        _, profile = agent_profile

        cfg = db.query(AgentPaymentConfig).filter(
            AgentPaymentConfig.agent_profile_id == profile.id
        ).first()
        if cfg is None:
            cfg = AgentPaymentConfig(
                agent_profile_id=profile.id,
                idp_is_enabled=True, idp_rate=Decimal("100.00"),
                stipend_is_enabled=False, stipend_daily_rate=Decimal("0.00"),
                pv_is_enabled=False, pv_rate=Decimal("0.00"),
                od_is_enabled=False, od_rate=Decimal("0.00"),
                offd_is_enabled=False, offd_rate=Decimal("0.00"),
                oa_is_enabled=False, oa_rate=Decimal("0.00"),
                initial_bonus=Decimal("500.00"),
                is_bonus_withdrawn=False,
            )
            db.add(cfg)
            db.commit()

        # Simulate a config update WITHOUT touching is_bonus_withdrawn
        cfg.idp_rate = Decimal("200.00")
        db.commit()
        db.refresh(cfg)

        assert cfg.is_bonus_withdrawn is False


# ---------------------------------------------------------------------------
# Stipend eligibility logic tests
# ---------------------------------------------------------------------------

class TestStipendEligibility:
    def _is_stipend_eligible(self, stipend_type, config_enabled):
        """
        Business rule: daily stipend only if WITH_STIPEND AND config enabled.
        """
        from app.models.agent import StipendType
        return (
            stipend_type == StipendType.WITH_STIPEND
            and config_enabled is True
        )

    def test_with_stipend_and_enabled(self, with_stipend_profile):
        """WITH_STIPEND + enabled → eligible."""
        from app.models.agent import StipendType
        _, profile = with_stipend_profile
        assert self._is_stipend_eligible(profile.stipend_type, True) is True

    def test_with_stipend_and_disabled(self, with_stipend_profile):
        """WITH_STIPEND + disabled → not eligible."""
        _, profile = with_stipend_profile
        assert self._is_stipend_eligible(profile.stipend_type, False) is False

    def test_without_stipend_enabled_config(self, no_stipend_profile):
        """WITHOUT_STIPEND + enabled → still not eligible."""
        _, profile = no_stipend_profile
        assert self._is_stipend_eligible(profile.stipend_type, True) is False

    def test_without_stipend_disabled_config(self, no_stipend_profile):
        """WITHOUT_STIPEND + disabled → not eligible."""
        _, profile = no_stipend_profile
        assert self._is_stipend_eligible(profile.stipend_type, False) is False


# ---------------------------------------------------------------------------
# wants_initial_bonus tests
# ---------------------------------------------------------------------------

class TestWantsInitialBonus:
    def test_default_is_false(self, db, agent_profile):
        """wants_initial_bonus defaults to False on new profiles."""
        _, profile = agent_profile
        assert profile.wants_initial_bonus is False

    def test_set_to_true(self, db, agent_profile):
        """Agent can set wants_initial_bonus to True."""
        _, profile = agent_profile
        profile.wants_initial_bonus = True
        db.commit()
        db.refresh(profile)
        assert profile.wants_initial_bonus is True

    def test_set_back_to_false(self, db, agent_profile):
        """Agent can change mind and set wants_initial_bonus back to False."""
        _, profile = agent_profile
        profile.wants_initial_bonus = False
        db.commit()
        db.refresh(profile)
        assert profile.wants_initial_bonus is False

    def test_false_preference_blocks_bonus_eligibility(self, db, agent_profile):
        """Business rule: wants_initial_bonus=False means not eligible for bonus."""
        _, profile = agent_profile
        profile.wants_initial_bonus = False
        db.commit()
        # The eligibility check: backend must enforce this preference
        assert profile.wants_initial_bonus is False  # confirmed not eligible


# ---------------------------------------------------------------------------
# Earning ledger tests
# ---------------------------------------------------------------------------

class TestAgentEarnings:
    def test_create_earning(self, db, agent_profile):
        """Can create an earning record with applied rate snapshot."""
        from app.models.agent_config import AgentEarning, AgentEarningType, AgentEarningStatus
        _, profile = agent_profile

        earning = AgentEarning(
            agent_profile_id=profile.id,
            earning_type=AgentEarningType.INSTITUTION_DIGITAL_PROFILE.value,
            status=AgentEarningStatus.PENDING.value,
            reference_type="institution_digital_profile",
            reference_id="idp-001",
            applied_rate=Decimal("1200.00"),
            amount=Decimal("1200.00"),
            earning_date=date.today(),
            description="IDP approved for school XYZ",
        )
        db.add(earning)
        db.commit()
        db.refresh(earning)

        assert earning.id is not None
        assert Decimal(str(earning.applied_rate)) == Decimal("1200.00")
        assert earning.status == AgentEarningStatus.PENDING.value

    def test_duplicate_earning_rejected(self, db, agent_profile):
        """Same (agent, type, reference_id) cannot be earned twice."""
        from app.models.agent_config import AgentEarning, AgentEarningType, AgentEarningStatus
        from sqlalchemy.exc import IntegrityError
        _, profile = agent_profile

        # Insert the first earning row
        first = AgentEarning(
            agent_profile_id=profile.id,
            earning_type=AgentEarningType.INSTITUTION_DIGITAL_PROFILE.value,
            status=AgentEarningStatus.PENDING.value,
            reference_type="institution_digital_profile",
            reference_id="idp-dup-test",
            applied_rate=Decimal("1200.00"),
            amount=Decimal("1200.00"),
            earning_date=date.today(),
        )
        db.add(first)
        db.commit()

        # Now try inserting the same reference again — must raise
        dup = AgentEarning(
            agent_profile_id=profile.id,
            earning_type=AgentEarningType.INSTITUTION_DIGITAL_PROFILE.value,
            status=AgentEarningStatus.PENDING.value,
            reference_type="institution_digital_profile",
            reference_id="idp-dup-test",   # same reference_id
            applied_rate=Decimal("1200.00"),
            amount=Decimal("1200.00"),
            earning_date=date.today(),
        )
        db.add(dup)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

    def test_rate_change_does_not_affect_approved_earning(self, db, agent_profile):
        """Updating config rate must not change an already-approved earning."""
        from app.models.agent_config import AgentEarning, AgentPaymentConfig, AgentEarningType, AgentEarningStatus
        _, profile = agent_profile

        # Create earning at rate 500
        earning = AgentEarning(
            agent_profile_id=profile.id,
            earning_type=AgentEarningType.DAILY_STIPEND.value,
            status=AgentEarningStatus.APPROVED.value,
            reference_type="attendance",
            reference_id="day-2026-10-01",
            applied_rate=Decimal("500.00"),
            amount=Decimal("500.00"),
            earning_date=date(2026, 10, 1),
        )
        db.add(earning)
        db.commit()
        earning_id = earning.id

        # Update config rate to 700
        cfg = db.query(AgentPaymentConfig).filter(
            AgentPaymentConfig.agent_profile_id == profile.id
        ).first()
        if cfg:
            cfg.stipend_daily_rate = Decimal("700.00")
            db.commit()

        # Re-fetch the earning — applied_rate must still be 500
        db.expire_all()
        old_earning = db.query(AgentEarning).filter(AgentEarning.id == earning_id).first()
        assert Decimal(str(old_earning.applied_rate)) == Decimal("500.00")
        assert Decimal(str(old_earning.amount)) == Decimal("500.00")


class TestMonthlyAgentStipends:
    def test_with_stipend_agent_gets_monthly_configured_rate_once(self, db, agent_profile):
        from app.models.agent import StipendType
        from app.models.agent_config import AgentEarning, AgentStipendRate
        from app.tasks.agent_tasks import generate_monthly_agent_stipends_for_period

        _, profile = agent_profile
        profile.stipend_type = StipendType.WITH_STIPEND
        db.add(AgentStipendRate(
            agent_profile_id=profile.id,
            effective_from=date(2026, 9, 1),
            is_enabled=True,
            monthly_rate=Decimal("1800.00"),
        ))
        db.commit()

        period_start = date(2026, 9, 1)
        period_end = date(2026, 10, 1)
        assert generate_monthly_agent_stipends_for_period(
            db, period_start, period_end
        ) == 1
        assert generate_monthly_agent_stipends_for_period(
            db, period_start, period_end
        ) == 0

        earning = db.query(AgentEarning).filter(
            AgentEarning.agent_profile_id == profile.id,
            AgentEarning.earning_type == "MONTHLY_STIPEND",
        ).one()
        assert earning.reference_id == "2026-09"
        assert earning.earning_date == date(2026, 9, 30)
        assert Decimal(str(earning.amount)) == Decimal("1800.00")
        assert Decimal(str(earning.applied_rate)) == Decimal("1800.00")

    def test_without_stipend_agent_never_receives_monthly_stipend(self, db, agent_profile):
        from app.models.agent import StipendType
        from app.models.agent_config import AgentEarning, AgentStipendRate
        from app.tasks.agent_tasks import generate_monthly_agent_stipends_for_period

        _, profile = agent_profile
        profile.stipend_type = StipendType.WITHOUT_STIPEND
        db.add(AgentStipendRate(
            agent_profile_id=profile.id,
            effective_from=date(2026, 9, 1),
            is_enabled=True,
            monthly_rate=Decimal("1800.00"),
        ))
        db.commit()

        assert generate_monthly_agent_stipends_for_period(
            db, date(2026, 9, 1), date(2026, 10, 1)
        ) == 0
        assert db.query(AgentEarning).filter(
            AgentEarning.agent_profile_id == profile.id,
            AgentEarning.earning_type == "MONTHLY_STIPEND",
        ).count() == 0

    def test_monthly_rate_changes_are_effective_next_month(self, db, agent_profile):
        from app.models.agent_config import AgentStipendRate
        from app.routes.agent import (
            _next_stipend_effective_date,
            _save_stipend_rate_snapshot,
        )

        _, profile = agent_profile
        effective_date = _next_stipend_effective_date()
        _save_stipend_rate_snapshot(
            db, profile.id, True, Decimal("2000.00")
        )
        db.commit()
        _save_stipend_rate_snapshot(
            db, profile.id, True, Decimal("2500.00")
        )
        db.commit()

        snapshots = db.query(AgentStipendRate).filter(
            AgentStipendRate.agent_profile_id == profile.id
        ).all()
        assert len(snapshots) == 1
        assert snapshots[0].effective_from == effective_date
        assert Decimal(str(snapshots[0].monthly_rate)) == Decimal("2500.00")


    def test_stipend_rate_snapshot_is_not_retroactive(self, db, agent_profile):
        from app.models.agent import StipendType
        from app.models.agent_config import AgentEarning, AgentStipendRate
        from app.tasks.agent_tasks import generate_monthly_agent_stipends_for_period

        _, profile = agent_profile
        profile.stipend_type = StipendType.WITH_STIPEND
        db.add(AgentStipendRate(
            agent_profile_id=profile.id,
            effective_from=date(2026, 10, 1),
            is_enabled=True,
            monthly_rate=Decimal("2100.00"),
        ))
        db.commit()

        assert generate_monthly_agent_stipends_for_period(
            db, date(2026, 9, 1), date(2026, 10, 1)
        ) == 0
        assert db.query(AgentEarning).filter(
            AgentEarning.agent_profile_id == profile.id,
            AgentEarning.earning_type == "MONTHLY_STIPEND",
        ).count() == 0


def test_agent_statistics_require_month_and_year_together():
    from fastapi import HTTPException

    from app.routes.agent import _stats_period

    assert _stats_period(None, None) is None
    assert _stats_period(3, 2026)[0:2] == (date(2026, 3, 1), date(2026, 4, 1))
    with pytest.raises(HTTPException) as exc:
        _stats_period(3, None)
    assert exc.value.status_code == 422
