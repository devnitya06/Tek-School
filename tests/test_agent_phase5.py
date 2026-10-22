from datetime import date, datetime
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture
def db():
    from app.models.agent import AgentProfile
    from app.models.agent_config import AgentEarning
    from app.models.agent_payment import AgentWithdrawal
    from app.models.users import User

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    for model in (User, AgentProfile, AgentEarning, AgentWithdrawal):
        model.__table__.create(bind=engine, checkfirst=True)
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE schools ("
            "id VARCHAR(64) PRIMARY KEY, "
            "created_by_agent_profile_id INTEGER, "
            "institution_verification_status VARCHAR(32), "
            "institution_verified_at DATETIME, "
            "created_at DATETIME)"
        ))

    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _create_user(db, email, role, *, active=True, deleted=False):
    from app.models.users import User
    from app.schemas.users import UserRole

    user = User(
        name=email.split("@")[0],
        email=email,
        role=UserRole(role),
        is_active=active,
        is_deleted=deleted,
        is_verified=True,
        verification_status="approved",
        profile_completed=False,
    )
    db.add(user)
    db.flush()
    return user


def _create_agent(db, index, *, active=True, deleted=False, district=None):
    from app.models.agent import AgentProfile, StipendType
    from app.schemas.users import UserRole

    user = _create_user(
        db,
        f"agent{index}@example.com",
        UserRole.AGENT.value,
        active=active,
        deleted=deleted,
    )
    profile = AgentProfile(
        user_id=user.id,
        first_name=f"Agent{index}",
        last_name="Test",
        email=user.email,
        stipend_type=StipendType.WITHOUT_STIPEND,
        district=district,
        designation="Field Associate",
    )
    db.add(profile)
    db.flush()
    return user, profile


def test_agent_statistics_use_approved_activity_and_net_ledger(db):
    from app.models.agent_config import AgentEarning
    from app.routes.agent import get_agent_dashboard_statistics

    agent, profile = _create_agent(db, 1)
    db.add_all([
        AgentEarning(
            agent_profile_id=profile.id,
            earning_type="MONTHLY_STIPEND",
            status="APPROVED",
            reference_id="2026-03",
            applied_rate=Decimal("1800"),
            amount=Decimal("1800"),
            earning_date=date(2026, 3, 31),
        ),
        AgentEarning(
            agent_profile_id=profile.id,
            earning_type="OTHER_ACTIVITY",
            status="REJECTED",
            reference_id="rejected-1",
            applied_rate=Decimal("500"),
            amount=Decimal("500"),
            earning_date=date(2026, 3, 10),
        ),
    ])
    db.execute(text(
        "INSERT INTO schools VALUES "
        "('approved-march', :profile_id, 'APPROVED', '2026-03-31 10:00:00.000000', "
        "'2026-03-01 10:00:00.000000'), "
        "('draft-march', :profile_id, 'DRAFT', NULL, '2026-03-01 10:00:00.000000'), "
        "('approved-april', :profile_id, 'APPROVED', '2026-04-01 00:00:00.000000', "
        "'2026-03-01 10:00:00.000000')"
    ), {"profile_id": profile.id})
    db.commit()

    result = get_agent_dashboard_statistics(
        agent_profile_id=profile.id,
        month=3,
        year=2026,
        db=db,
        current_user=agent,
    )

    assert result["institution_listing"] == 1
    assert result["demonstration"] == 0
    assert result["field_verification"] == 0
    assert result["net_earnings"] == Decimal("1800")


def test_agent_cannot_request_another_agents_statistics(db):
    from app.routes.agent import get_agent_dashboard_statistics

    agent, _ = _create_agent(db, 1)
    _, other_profile = _create_agent(db, 2)
    db.commit()

    with pytest.raises(HTTPException) as exc:
        get_agent_dashboard_statistics(
            agent_profile_id=other_profile.id,
            month=None,
            year=None,
            db=db,
            current_user=agent,
        )
    assert exc.value.status_code == 403


def test_admin_summary_and_agent_list_aggregate_counts(db):
    from app.models.agent_config import AgentEarning
    from app.models.agent_payment import AgentWithdrawal
    from app.routes.agent import (
        get_admin_agent_dashboard_statistics,
        list_agents,
    )
    from app.schemas.users import UserRole

    admin = _create_user(db, "admin@example.com", UserRole.ADMIN.value)
    active_user, active_profile = _create_agent(db, 1, district="Cuttack")
    inactive_user, inactive_profile = _create_agent(
        db, 2, active=False, district="Puri"
    )
    _create_agent(db, 3, active=True, deleted=True)

    db.add(AgentEarning(
        agent_profile_id=active_profile.id,
        earning_type="INSTITUTION_DIGITAL_PROFILE",
        status="APPROVED",
        reference_id="school-1",
        applied_rate=Decimal("900"),
        amount=Decimal("900"),
        earning_date=date(2026, 3, 15),
    ))
    db.add_all([
        AgentWithdrawal(
            agent_profile_id=active_profile.id,
            requested_amount=Decimal("100"),
            status="PENDING",
            created_at=datetime(2026, 3, 12),
        ),
        AgentWithdrawal(
            agent_profile_id=active_profile.id,
            requested_amount=Decimal("50"),
            status="REJECTED",
            created_at=datetime(2026, 3, 13),
        ),
    ])
    db.commit()

    summary = get_admin_agent_dashboard_statistics(
        month=3,
        year=2026,
        db=db,
        current_user=admin,
    )
    assert summary["total_agents"] == 2
    assert summary["active_agents"] == 1
    assert summary["inactive_agents"] == 1
    assert summary["agent_earnings"] == Decimal("900")
    assert summary["pending_withdrawal"] == Decimal("100")

    listing = list_agents(
        skip=0,
        limit=50,
        include_deleted=False,
        profile_complete=None,
        db=db,
        current_user=admin,
    )
    listed = {item.user_id: item for item in listing}
    assert listed[active_user.id].district == "Cuttack"
    assert listed[active_user.id].designation == "Field Associate"
    assert listed[active_user.id].pay_request == 2
    assert listed[active_user.id].no_of_tasks == 0
    assert inactive_user.id in listed
