"""
Tests for Digital Profile Pricing, Wallet, and Business Inquiry Billing.

Unit tests (no DB required):
    TestPricingCalculation
    TestRechargeBonus
    TestViewerNumberPricing

Integration tests (requires_postgres marker):
    TestWalletOperations
    TestBusinessInquiryBilling

Run unit tests only:
    pytest tests/test_billing_wallet.py -v -m "not requires_postgres"

Run all (with Postgres):
    pytest tests/test_billing_wallet.py -v
"""

import os
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


# ─── Markers ─────────────────────────────────────────────────────────────────

requires_postgres = pytest.mark.requires_postgres


# ─── Helpers ─────────────────────────────────────────────────────────────────

def make_stub_config(
    first_two=Decimal("50.00"),
    next_five=Decimal("20.00"),
    all_other=Decimal("10.00"),
):
    """Create a stub DigitalProfilePriceConfig without DB."""
    return SimpleNamespace(
        id=1,
        education_associate="SCHOOL_EDUCATIONS",
        education_offered=["CBSE", "ICSE"],
        first_two_viewer_price=first_two,
        next_five_viewer_price=next_five,
        all_other_viewer_price=all_other,
    )


# ─── Unit Tests: Pricing Calculation ─────────────────────────────────────────

class TestPricingCalculation:
    """Tests for calculate_applicable_price(). No DB needed."""

    def _price(self, viewer_number: int, config=None) -> Decimal:
        from app.services.billing import calculate_applicable_price
        c = config or make_stub_config()
        return calculate_applicable_price(viewer_number, c)

    def test_viewer_1_gets_first_two_price(self):
        assert self._price(1) == Decimal("50.00")

    def test_viewer_2_gets_first_two_price(self):
        assert self._price(2) == Decimal("50.00")

    def test_viewer_3_gets_next_five_price(self):
        assert self._price(3) == Decimal("20.00")

    def test_viewer_4_gets_next_five_price(self):
        assert self._price(4) == Decimal("20.00")

    def test_viewer_5_gets_next_five_price(self):
        assert self._price(5) == Decimal("20.00")

    def test_viewer_6_gets_next_five_price(self):
        assert self._price(6) == Decimal("20.00")

    def test_viewer_7_gets_next_five_price(self):
        assert self._price(7) == Decimal("20.00")

    def test_viewer_8_gets_all_other_price(self):
        assert self._price(8) == Decimal("10.00")

    def test_viewer_100_gets_all_other_price(self):
        assert self._price(100) == Decimal("10.00")

    def test_custom_config_prices(self):
        config = make_stub_config(
            first_two=Decimal("60.00"),
            next_five=Decimal("25.00"),
            all_other=Decimal("15.00"),
        )
        assert self._price(1, config) == Decimal("60.00")
        assert self._price(2, config) == Decimal("60.00")
        assert self._price(3, config) == Decimal("25.00")
        assert self._price(7, config) == Decimal("25.00")
        assert self._price(8, config) == Decimal("15.00")


# ─── Unit Tests: Recharge Bonus Calculation ───────────────────────────────────

class TestRechargeBonus:
    """Tests for calculate_recharge_bonus(). No DB needed."""

    def _make_config(self, slabs):
        bonus_configs = [
            SimpleNamespace(recharge_amount=Decimal(str(amt)), bonus_percentage=Decimal(str(pct)))
            for amt, pct in slabs
        ]
        return SimpleNamespace(bonus_configs=bonus_configs)

    def _bonus(self, amount, slabs):
        from app.services.billing import calculate_recharge_bonus
        config = self._make_config(slabs)
        return calculate_recharge_bonus(Decimal(str(amount)), config)

    def test_exact_match_5000_20pct(self):
        pct, amt = self._bonus(5000, [(5000, 20), (10000, 15), (20000, 20)])
        assert pct == Decimal("20.00")
        assert amt == Decimal("1000.00")

    def test_exact_match_10000_15pct(self):
        pct, amt = self._bonus(10000, [(5000, 20), (10000, 15), (20000, 20)])
        assert pct == Decimal("15.00")
        assert amt == Decimal("1500.00")

    def test_exact_match_20000_20pct(self):
        pct, amt = self._bonus(20000, [(5000, 20), (10000, 15), (20000, 20)])
        assert pct == Decimal("20.00")
        assert amt == Decimal("4000.00")

    def test_no_match_returns_zero_bonus(self):
        pct, amt = self._bonus(1000, [(5000, 20), (10000, 15)])
        assert pct == Decimal("0.00")
        assert amt == Decimal("0.00")

    def test_total_credit_calculation(self):
        """5000 + 20% = 6000 total."""
        pct, bonus_amt = self._bonus(5000, [(5000, 20)])
        total = Decimal("5000") + bonus_amt
        assert total == Decimal("6000.00")


# ─── Unit Tests: Pydantic Schema Validation ───────────────────────────────────

class TestPriceConfigSchema:
    """Pydantic validation tests. No DB needed."""

    def test_valid_config_accepted(self):
        from app.schemas.billing import PriceConfigCreate, EducationAssociate
        data = PriceConfigCreate(
            education_associate=EducationAssociate.SCHOOL_EDUCATIONS,
            education_offered=["CBSE", "ICSE"],
            first_two_viewer_price=Decimal("50"),
            next_five_viewer_price=Decimal("20"),
            all_other_viewer_price=Decimal("10"),
        )
        assert data.education_associate == EducationAssociate.SCHOOL_EDUCATIONS

    def test_empty_education_offered_rejected(self):
        from app.schemas.billing import PriceConfigCreate, EducationAssociate
        with pytest.raises(Exception):
            PriceConfigCreate(
                education_associate=EducationAssociate.SCHOOL_EDUCATIONS,
                education_offered=[],
                first_two_viewer_price=Decimal("50"),
                next_five_viewer_price=Decimal("20"),
                all_other_viewer_price=Decimal("10"),
            )

    def test_negative_price_rejected(self):
        from app.schemas.billing import PriceConfigCreate, EducationAssociate
        with pytest.raises(Exception):
            PriceConfigCreate(
                education_associate=EducationAssociate.SCHOOL_EDUCATIONS,
                education_offered=["CBSE"],
                first_two_viewer_price=Decimal("-1"),
                next_five_viewer_price=Decimal("20"),
                all_other_viewer_price=Decimal("10"),
            )

    def test_invalid_education_associate_rejected(self):
        from app.schemas.billing import PriceConfigCreate
        with pytest.raises(Exception):
            PriceConfigCreate(
                education_associate="INVALID_VALUE",
                education_offered=["CBSE"],
                first_two_viewer_price=Decimal("50"),
                next_five_viewer_price=Decimal("20"),
                all_other_viewer_price=Decimal("10"),
            )


class TestRechargeConfigSchema:
    """Pydantic validation tests for recharge config. No DB needed."""

    def test_valid_config_accepted(self):
        from app.schemas.billing import RechargeConfigUpdate, RechargeBonusItem
        data = RechargeConfigUpdate(
            min_recharge_amount=Decimal("500"),
            max_recharge_amount=Decimal("20000"),
            bonus_configs=[
                RechargeBonusItem(recharge_amount=Decimal("5000"), bonus_percentage=Decimal("20")),
            ],
        )
        assert data.min_recharge_amount == Decimal("500")

    def test_max_less_than_min_rejected(self):
        from app.schemas.billing import RechargeConfigUpdate
        with pytest.raises(Exception):
            RechargeConfigUpdate(
                min_recharge_amount=Decimal("20000"),
                max_recharge_amount=Decimal("500"),
                bonus_configs=[],
            )

    def test_duplicate_recharge_amounts_rejected(self):
        from app.schemas.billing import RechargeConfigUpdate, RechargeBonusItem
        with pytest.raises(Exception):
            RechargeConfigUpdate(
                min_recharge_amount=Decimal("500"),
                max_recharge_amount=Decimal("20000"),
                bonus_configs=[
                    RechargeBonusItem(recharge_amount=Decimal("5000"), bonus_percentage=Decimal("20")),
                    RechargeBonusItem(recharge_amount=Decimal("5000"), bonus_percentage=Decimal("15")),
                ],
            )


# ─── Integration Tests (PostgreSQL required) ──────────────────────────────────

@requires_postgres
class TestWalletOperations:
    """Integration tests — require a live PostgreSQL database."""

    @pytest.fixture(autouse=True)
    def skip_if_no_postgres(self):
        if not os.environ.get("DATABASE_URL", "").startswith("postgresql"):
            pytest.skip("PostgreSQL is required for wallet integration tests.")

    def test_recharge_creates_pending_transaction(self, db_session):
        """POST /school/wallet/recharge → creates PENDING transaction, does NOT credit wallet."""
        from app.services.billing import initiate_wallet_recharge, get_or_create_wallet
        from app.models.billing import WalletTransactionStatus

        school_id = "TEST-SCH-001"

        # Create wallet with 0 balance
        wallet = get_or_create_wallet(school_id, db_session)
        db_session.commit()
        assert wallet.balance == Decimal("0.00")

        # Initiate recharge
        config_mock = SimpleNamespace(
            id=1,
            min_recharge_amount=Decimal("500"),
            max_recharge_amount=Decimal("20000"),
            bonus_configs=[
                SimpleNamespace(
                    recharge_amount=Decimal("5000"),
                    bonus_percentage=Decimal("20"),
                )
            ],
        )

        with patch("app.services.billing.get_active_recharge_config", return_value=config_mock):
            txn, bonus_pct = initiate_wallet_recharge(
                school_id=school_id,
                amount=Decimal("5000"),
                db=db_session,
                current_user_id=1,
            )
            db_session.commit()

        assert txn.transaction_status == WalletTransactionStatus.PENDING.value
        assert txn.amount == Decimal("5000")
        assert txn.bonus_amount == Decimal("1000")
        assert txn.total_credit == Decimal("6000")
        assert bonus_pct == Decimal("20")

        # Wallet must NOT be credited yet
        db_session.refresh(wallet)
        assert wallet.balance == Decimal("0.00"), "Wallet must NOT be credited for PENDING transaction"

    def test_wallet_defaults_to_zero(self, db_session):
        """New school wallet starts at 0 balance with INR currency."""
        from app.services.billing import get_or_create_wallet

        school_id = "TEST-SCH-002"
        wallet = get_or_create_wallet(school_id, db_session)
        db_session.commit()

        assert wallet.balance == Decimal("0.00")
        assert wallet.currency == "INR"
        assert wallet.school_id == school_id


@requires_postgres
class TestBusinessInquiryBilling:
    """Integration tests for inquiry billing flow."""

    @pytest.fixture(autouse=True)
    def skip_if_no_postgres(self):
        if not os.environ.get("DATABASE_URL", "").startswith("postgresql"):
            pytest.skip("PostgreSQL is required for billing integration tests.")

    def test_insufficient_balance_returns_402(self, db_session, monkeypatch):
        """wallet=30, price=50 → 402 INSUFFICIENT_WALLET_BALANCE."""
        from fastapi import HTTPException
        from app.services.billing import view_business_inquiry
        from app.models.billing import SchoolWallet, WalletTransactionStatus
        from app.models.school import BusinessInquiry

        school_id = "TEST-SCH-003"

        # Create wallet with low balance
        wallet = SchoolWallet(school_id=school_id, balance=Decimal("30.00"), currency="INR")
        db_session.add(wallet)

        # Create inquiry
        inquiry = BusinessInquiry(
            school_ids=[school_id],
            guardian_name="Test User",
            phone="9999999999",
            email="test@test.com",
            gender="male",
            who_is_this="parent",
            is_seen=False,
        )
        db_session.add(inquiry)
        db_session.flush()

        # Create seed BIS row
        from app.models.billing import BusinessInquirySchool
        from app.services.billing import seed_inquiry_school_rows
        seed_inquiry_school_rows(inquiry.id, [school_id], db_session)
        db_session.flush()

        # Mock pricing to return ₹50
        stub_config = make_stub_config(
            first_two=Decimal("50.00"),
            next_five=Decimal("20.00"),
            all_other=Decimal("10.00"),
        )
        school_stub = SimpleNamespace(
            id=school_id,
            school_board=None,
        )

        with patch("app.services.billing.get_price_config_for_school", return_value=stub_config):
            with pytest.raises(HTTPException) as exc_info:
                view_business_inquiry(
                    inquiry_id=inquiry.id,
                    school_id=school_id,
                    school=school_stub,
                    db=db_session,
                )
            db_session.rollback()

        assert exc_info.value.status_code == 402
        detail = exc_info.value.detail
        assert detail["code"] == "INSUFFICIENT_WALLET_BALANCE"
        assert detail["required_amount"] == 50.0
        assert detail["wallet_balance"] == 30.0
        assert detail["shortfall_amount"] == 20.0

    def test_first_view_charges_and_marks_seen(self, db_session):
        """First view deducts wallet, sets viewer_number=1, marks is_seen."""
        from app.services.billing import view_business_inquiry, seed_inquiry_school_rows
        from app.models.billing import SchoolWallet, BusinessInquirySchool
        from app.models.school import BusinessInquiry

        school_id = "TEST-SCH-004"

        wallet = SchoolWallet(school_id=school_id, balance=Decimal("500.00"), currency="INR")
        db_session.add(wallet)

        inquiry = BusinessInquiry(
            school_ids=[school_id],
            guardian_name="Rahul",
            phone="9999999990",
            email="rahul@test.com",
            gender="male",
            who_is_this="parent",
            is_seen=False,
        )
        db_session.add(inquiry)
        db_session.flush()

        seed_inquiry_school_rows(inquiry.id, [school_id], db_session)
        db_session.flush()

        stub_config = make_stub_config()
        school_stub = SimpleNamespace(id=school_id, school_board=None)

        with patch("app.services.billing.get_price_config_for_school", return_value=stub_config):
            inq, bis = view_business_inquiry(
                inquiry_id=inquiry.id,
                school_id=school_id,
                school=school_stub,
                db=db_session,
            )
            db_session.commit()

        assert bis.is_seen is True
        assert bis.viewer_number == 1
        assert bis.price_per_view == Decimal("50.00")
        assert bis.amount_deducted == Decimal("50.00")

        db_session.refresh(wallet)
        assert wallet.balance == Decimal("450.00")

    def test_second_view_does_not_charge(self, db_session):
        """Viewing the same inquiry again returns stored data without deducting."""
        from app.services.billing import view_business_inquiry, seed_inquiry_school_rows
        from app.models.billing import SchoolWallet, BusinessInquirySchool
        from app.models.school import BusinessInquiry

        school_id = "TEST-SCH-005"

        wallet = SchoolWallet(school_id=school_id, balance=Decimal("500.00"), currency="INR")
        db_session.add(wallet)

        inquiry = BusinessInquiry(
            school_ids=[school_id],
            guardian_name="Priya",
            phone="9999999991",
            email="priya@test.com",
            gender="female",
            who_is_this="student",
            is_seen=False,
        )
        db_session.add(inquiry)
        db_session.flush()

        seed_inquiry_school_rows(inquiry.id, [school_id], db_session)
        db_session.flush()

        stub_config = make_stub_config()
        school_stub = SimpleNamespace(id=school_id, school_board=None)

        # First view
        with patch("app.services.billing.get_price_config_for_school", return_value=stub_config):
            view_business_inquiry(inquiry_id=inquiry.id, school_id=school_id, school=school_stub, db=db_session)
            db_session.commit()

        db_session.refresh(wallet)
        balance_after_first = wallet.balance

        # Second view — should NOT deduct
        with patch("app.services.billing.get_price_config_for_school", return_value=stub_config):
            inq, bis = view_business_inquiry(
                inquiry_id=inquiry.id, school_id=school_id, school=school_stub, db=db_session
            )
            db_session.commit()

        db_session.refresh(wallet)
        assert wallet.balance == balance_after_first, "Balance must not change on second view"
        assert bis.viewer_number == 1, "Viewer number must stay at 1"

    def test_multi_school_billing_independence(self, db_session):
        """School A viewed → A charged. School B not viewed → B not charged."""
        from app.services.billing import view_business_inquiry, seed_inquiry_school_rows
        from app.models.billing import SchoolWallet, BusinessInquirySchool
        from app.models.school import BusinessInquiry

        school_a = "TEST-SCH-A01"
        school_b = "TEST-SCH-B01"

        wallet_a = SchoolWallet(school_id=school_a, balance=Decimal("500.00"), currency="INR")
        wallet_b = SchoolWallet(school_id=school_b, balance=Decimal("500.00"), currency="INR")
        db_session.add_all([wallet_a, wallet_b])

        inquiry = BusinessInquiry(
            school_ids=[school_a, school_b],
            guardian_name="Multi School Test",
            phone="9999999992",
            email="multi@test.com",
            gender="other",
            who_is_this="parent",
            is_seen=False,
        )
        db_session.add(inquiry)
        db_session.flush()

        seed_inquiry_school_rows(inquiry.id, [school_a, school_b], db_session)
        db_session.flush()

        stub_config = make_stub_config()
        school_a_stub = SimpleNamespace(id=school_a, school_board=None)

        # Only school A views
        with patch("app.services.billing.get_price_config_for_school", return_value=stub_config):
            view_business_inquiry(inquiry_id=inquiry.id, school_id=school_a, school=school_a_stub, db=db_session)
            db_session.commit()

        db_session.refresh(wallet_a)
        db_session.refresh(wallet_b)

        assert wallet_a.balance == Decimal("450.00"), "School A must be charged"
        assert wallet_b.balance == Decimal("500.00"), "School B must NOT be charged"

    def test_historical_price_preserved_after_config_change(self, db_session):
        """Old viewed inquiry shows ₹50 even after admin changes config to ₹60."""
        from app.services.billing import view_business_inquiry, seed_inquiry_school_rows
        from app.models.billing import SchoolWallet, BusinessInquirySchool
        from app.models.school import BusinessInquiry

        school_id = "TEST-SCH-006"

        wallet = SchoolWallet(school_id=school_id, balance=Decimal("500.00"), currency="INR")
        db_session.add(wallet)

        inquiry = BusinessInquiry(
            school_ids=[school_id],
            guardian_name="Historical Test",
            phone="9999999993",
            email="hist@test.com",
            gender="male",
            who_is_this="parent",
            is_seen=False,
        )
        db_session.add(inquiry)
        db_session.flush()

        seed_inquiry_school_rows(inquiry.id, [school_id], db_session)
        db_session.flush()

        # View with ₹50 config
        old_config = make_stub_config(first_two=Decimal("50.00"))
        school_stub = SimpleNamespace(id=school_id, school_board=None)

        with patch("app.services.billing.get_price_config_for_school", return_value=old_config):
            inq, bis = view_business_inquiry(
                inquiry_id=inquiry.id, school_id=school_id, school=school_stub, db=db_session
            )
            db_session.commit()

        assert bis.price_per_view == Decimal("50.00")

        # Simulate admin changing config to ₹60
        new_config = make_stub_config(first_two=Decimal("60.00"))

        # Re-view the same inquiry — must return stored ₹50, not recalculate ₹60
        with patch("app.services.billing.get_price_config_for_school", return_value=new_config):
            inq2, bis2 = view_business_inquiry(
                inquiry_id=inquiry.id, school_id=school_id, school=school_stub, db=db_session
            )
            db_session.commit()

        assert bis2.price_per_view == Decimal("50.00"), "Historical price must be preserved"


# ─── DB Fixture for integration tests ────────────────────────────────────────

@pytest.fixture(scope="function")
def db_session():
    """Provide a fresh DB session; rolls back after each test."""
    if not os.environ.get("DATABASE_URL", "").startswith("postgresql"):
        pytest.skip("PostgreSQL required.")

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.db.session import Base

    engine = create_engine(os.environ["DATABASE_URL"])
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    session.begin_nested()  # savepoint
    yield session
    session.rollback()
    session.close()
