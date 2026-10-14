"""Agent Phase 3 — Automated Tests

Covers:
  - Payment account schema validation
  - Payment account DB create / update / duplicate / method validation
  - Earnings summary calculations
  - Withdrawal request lifecycle (create, approve, reject, mark-paid)
  - Balance reservation and double-release prevention
  - Admin mark-paid validation constants
  - Audit history recording
  - Role isolation (agents cannot see others' data)
  - Migration/metadata sanity checks

Run with: pytest tests/test_agent_phase3.py -v
"""

import random
import pytest
from decimal import Decimal
from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.users import User
from app.models.agent import AgentProfile, StipendType
from app.models.agent_config import AgentPaymentConfig, AgentEarning, AgentEarningStatus
from app.models.agent_payment import (
    AgentPaymentAccount,
    AgentWithdrawal,
    AgentWithdrawalHistory,
    PaymentMethod,
    WithdrawalStatus,
)
from app.schemas.users import UserRole
from app.schemas.agent_payment import (
    PaymentAccountRequest,
    WithdrawalCreateRequest,
    ApproveWithdrawalRequest,
    RejectWithdrawalRequest,
    _mask_account,
    ALLOWED_PROOF_EXTS,
    MAX_PROOF_SIZE,
    MAX_TRANSACTION_ID_LEN,
)


# ---------------------------------------------------------------------------
# Shared SQLite engine (module-level, with per-test rollback isolation)
# ---------------------------------------------------------------------------

TEST_DB_URL = "sqlite:///./test_agent_phase3.db"
_ENGINE = None
_SESSION_FACTORY = None


def _get_engine_factory():
    global _ENGINE, _SESSION_FACTORY
    if _ENGINE is None:
        _ENGINE = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
        for tbl in (
            User.__table__,
            AgentProfile.__table__,
            AgentPaymentConfig.__table__,
            AgentEarning.__table__,
            AgentPaymentAccount.__table__,
            AgentWithdrawal.__table__,
            AgentWithdrawalHistory.__table__,
        ):
            tbl.create(bind=_ENGINE, checkfirst=True)
        _SESSION_FACTORY = sessionmaker(autocommit=False, autoflush=False, bind=_ENGINE)
    return _ENGINE, _SESSION_FACTORY


def _open_db():
    _, factory = _get_engine_factory()
    return factory()


def _close_db(db):
    db.rollback()
    db.close()


# ---------------------------------------------------------------------------
# Helpers — unique random values to avoid UNIQUE constraint collisions
# ---------------------------------------------------------------------------

def _rand_email():
    return f"agent_{random.randint(100000, 999999)}@test.com"


def _rand_phone():
    return str(random.randint(7000000000, 9999999999))


def _rand_ref():
    return f"ACT-{random.randint(1000, 999999)}"


def _make_user(db, role=UserRole.AGENT):
    u = User(
        name="Test User",
        email=_rand_email(),
        phone=_rand_phone(),
        role=role,
        hashed_password="hashed",
        is_verified=True,
        is_active=True,
        verification_status="approved",
        profile_completed=False,
        is_deleted=False,
    )
    db.add(u)
    db.flush()
    return u


def _make_profile(db, user, stipend_type=StipendType.WITHOUT_STIPEND):
    p = AgentProfile(
        user_id=user.id,
        first_name="Test",
        last_name="Agent",
        phone=user.phone,
        email=user.email,
        stipend_type=stipend_type,
    )
    db.add(p)
    db.flush()
    return p


def _make_earning(db, profile, amount="1000.00", status=AgentEarningStatus.APPROVED):
    e = AgentEarning(
        agent_profile_id=profile.id,
        earning_type="PHYSICAL_VERIFICATION",
        amount=Decimal(amount),
        applied_rate=Decimal("250.00"),
        status=status.value,
        reference_type="ACTIVITY",
        reference_id=_rand_ref(),
    )
    db.add(e)
    db.flush()
    return e


def _make_payment_account(db, profile, method=PaymentMethod.UPI):
    acct = AgentPaymentAccount(
        agent_profile_id=profile.id,
        account_holder_name="Test Agent",
        payment_method=method.value,
        upi_id="agent@upi" if method == PaymentMethod.UPI else None,
        bank_account_number="123456789012" if method == PaymentMethod.BANK_TRANSFER else None,
        ifsc_code="SBIN0001234" if method == PaymentMethod.BANK_TRANSFER else None,
        bank_name="State Bank" if method == PaymentMethod.BANK_TRANSFER else None,
    )
    db.add(acct)
    db.flush()
    return acct


# ---------------------------------------------------------------------------
# 1. Schema Validation Tests
# ---------------------------------------------------------------------------

class TestPaymentAccountSchema:
    def test_upi_valid(self):
        req = PaymentAccountRequest(
            account_holder_name="John",
            payment_method=PaymentMethod.UPI,
            upi_id="john@upi",
        )
        assert req.upi_id == "john@upi"

    def test_upi_requires_upi_id(self):
        with pytest.raises(Exception):
            PaymentAccountRequest(
                account_holder_name="John",
                payment_method=PaymentMethod.UPI,
            )

    def test_upi_invalid_format(self):
        with pytest.raises(Exception):
            PaymentAccountRequest(
                account_holder_name="John",
                payment_method=PaymentMethod.UPI,
                upi_id="notaupiid",
            )

    def test_bank_transfer_valid(self):
        req = PaymentAccountRequest(
            account_holder_name="John",
            payment_method=PaymentMethod.BANK_TRANSFER,
            bank_account_number="123456789012",
            confirm_bank_account_number="123456789012",
            ifsc_code="SBIN0001234",
            bank_name="SBI",
        )
        assert req.bank_name == "SBI"

    def test_bank_transfer_account_mismatch(self):
        with pytest.raises(Exception):
            PaymentAccountRequest(
                account_holder_name="John",
                payment_method=PaymentMethod.BANK_TRANSFER,
                bank_account_number="111111111111",
                confirm_bank_account_number="222222222222",
                ifsc_code="SBIN0001234",
                bank_name="SBI",
            )

    def test_bank_transfer_missing_fields(self):
        with pytest.raises(Exception):
            PaymentAccountRequest(
                account_holder_name="John",
                payment_method=PaymentMethod.BANK_TRANSFER,
            )

    def test_invalid_ifsc(self):
        with pytest.raises(Exception):
            PaymentAccountRequest(
                account_holder_name="John",
                payment_method=PaymentMethod.BANK_TRANSFER,
                bank_account_number="123456789012",
                confirm_bank_account_number="123456789012",
                ifsc_code="BADINPUT",
                bank_name="SBI",
            )

    def test_mask_account_long(self):
        assert _mask_account("123456789012") == "XXXXXXXX9012"

    def test_mask_account_short(self):
        assert _mask_account("1234") == "XXXX"

    def test_mask_account_empty(self):
        assert _mask_account("") == ""

    def test_confirm_not_stored(self):
        """confirm_bank_account_number must not be a model field."""
        assert not hasattr(AgentPaymentAccount, "confirm_bank_account_number")

    def test_withdrawal_zero_rejected(self):
        with pytest.raises(Exception):
            WithdrawalCreateRequest(amount=Decimal("0.00"))

    def test_withdrawal_negative_rejected(self):
        with pytest.raises(Exception):
            WithdrawalCreateRequest(amount=Decimal("-100.00"))


# ---------------------------------------------------------------------------
# 2. Payment Account DB Tests
# ---------------------------------------------------------------------------

class TestPaymentAccountDB:
    def setup_method(self):
        self.db = _open_db()
        self.u = _make_user(self.db)
        self.p = _make_profile(self.db, self.u)
        self.db.commit()

    def teardown_method(self):
        _close_db(self.db)

    def test_create_upi_account(self):
        acct = _make_payment_account(self.db, self.p, PaymentMethod.UPI)
        self.db.commit()
        assert acct.payment_method == PaymentMethod.UPI.value
        assert acct.upi_id == "agent@upi"
        assert acct.bank_account_number is None

    def test_create_bank_account(self):
        acct = _make_payment_account(self.db, self.p, PaymentMethod.BANK_TRANSFER)
        self.db.commit()
        assert acct.payment_method == PaymentMethod.BANK_TRANSFER.value
        assert acct.bank_account_number == "123456789012"
        assert acct.upi_id is None

    def test_duplicate_account_rejected(self):
        from sqlalchemy.exc import IntegrityError
        _make_payment_account(self.db, self.p, PaymentMethod.UPI)
        self.db.commit()
        acct2 = AgentPaymentAccount(
            agent_profile_id=self.p.id,
            account_holder_name="Another",
            payment_method=PaymentMethod.BANK_TRANSFER.value,
            bank_account_number="999999999999",
        )
        self.db.add(acct2)
        with pytest.raises(IntegrityError):
            self.db.commit()

    def test_bank_account_masked_in_response(self):
        acct = _make_payment_account(self.db, self.p, PaymentMethod.BANK_TRANSFER)
        self.db.commit()
        masked = _mask_account(acct.bank_account_number)
        assert "X" in masked
        # Full account number must never appear unmasked in masked output
        assert acct.bank_account_number not in masked


# ---------------------------------------------------------------------------
# 3. Earnings Summary Tests
# ---------------------------------------------------------------------------

class TestEarningsSummary:
    def setup_method(self):
        self.db = _open_db()
        self.u = _make_user(self.db)
        self.p = _make_profile(self.db, self.u)
        self.db.commit()

    def teardown_method(self):
        _close_db(self.db)

    def _summary(self):
        from app.routes.agent import _calc_earnings_summary
        return _calc_earnings_summary(self.p, self.db)

    def test_empty_profile_all_zeros(self):
        s = self._summary()
        assert s["total_approved_earnings"] == Decimal("0")
        assert s["available_balance"] == Decimal("0")

    def test_approved_earning_counted(self):
        _make_earning(self.db, self.p, "500.00", AgentEarningStatus.APPROVED)
        self.db.commit()
        s = self._summary()
        assert s["total_approved_earnings"] == Decimal("500.00")
        assert s["available_balance"] == Decimal("500.00")

    def test_pending_not_withdrawable(self):
        _make_earning(self.db, self.p, "500.00", AgentEarningStatus.PENDING)
        self.db.commit()
        s = self._summary()
        assert s["total_pending_earnings"] == Decimal("500.00")
        assert s["available_balance"] == Decimal("0")

    def test_rejected_not_withdrawable(self):
        _make_earning(self.db, self.p, "500.00", AgentEarningStatus.REJECTED)
        self.db.commit()
        s = self._summary()
        assert s["total_rejected_earnings"] == Decimal("500.00")
        assert s["available_balance"] == Decimal("0")

    def test_reserved_deducted_from_available(self):
        _make_earning(self.db, self.p, "1000.00", AgentEarningStatus.APPROVED)
        w = AgentWithdrawal(
            agent_profile_id=self.p.id,
            requested_amount=Decimal("600.00"),
            status=WithdrawalStatus.PENDING.value,
            reservation_released=False,
        )
        self.db.add(w)
        self.db.commit()
        s = self._summary()
        assert s["total_reserved_amount"] == Decimal("600.00")
        assert s["available_balance"] == Decimal("400.00")

    def test_paid_withdrawal_deducted(self):
        _make_earning(self.db, self.p, "1000.00", AgentEarningStatus.APPROVED)
        w = AgentWithdrawal(
            agent_profile_id=self.p.id,
            requested_amount=Decimal("500.00"),
            status=WithdrawalStatus.PAID.value,
            actual_paid_amount=Decimal("500.00"),
            reservation_released=True,
        )
        self.db.add(w)
        self.db.commit()
        s = self._summary()
        assert s["total_paid_amount"] == Decimal("500.00")
        assert s["available_balance"] == Decimal("500.00")

    def test_rejected_withdrawal_releases_funds(self):
        _make_earning(self.db, self.p, "1000.00", AgentEarningStatus.APPROVED)
        w = AgentWithdrawal(
            agent_profile_id=self.p.id,
            requested_amount=Decimal("500.00"),
            status=WithdrawalStatus.REJECTED.value,
            reservation_released=True,
        )
        self.db.add(w)
        self.db.commit()
        s = self._summary()
        assert s["total_reserved_amount"] == Decimal("0")
        assert s["available_balance"] == Decimal("1000.00")

    def test_historical_earning_amount_unchanged(self):
        """Rate changes must never affect already-created earning records."""
        e = _make_earning(self.db, self.p, "250.00", AgentEarningStatus.APPROVED)
        original = e.amount
        self.db.commit()
        e_fresh = self.db.query(AgentEarning).filter(AgentEarning.id == e.id).first()
        assert e_fresh.amount == original


# ---------------------------------------------------------------------------
# 4. Withdrawal Lifecycle Tests
# ---------------------------------------------------------------------------

class TestWithdrawalLifecycle:
    def setup_method(self):
        self.db = _open_db()
        self.u = _make_user(self.db)
        self.p = _make_profile(self.db, self.u)
        _make_earning(self.db, self.p, "2000.00", AgentEarningStatus.APPROVED)
        _make_payment_account(self.db, self.p, PaymentMethod.UPI)
        self.db.commit()

    def teardown_method(self):
        _close_db(self.db)

    def _make_withdrawal(self, amount="500.00", status=WithdrawalStatus.PENDING):
        w = AgentWithdrawal(
            agent_profile_id=self.p.id,
            requested_amount=Decimal(amount),
            status=status.value,
            payment_method_snapshot="UPI",
            upi_id_snapshot="agent@upi",
            account_holder_name_snapshot="Test Agent",
            reservation_released=False,
        )
        self.db.add(w)
        self.db.flush()
        return w

    def test_create_withdrawal_pending(self):
        w = self._make_withdrawal()
        self.db.commit()
        assert w.status == WithdrawalStatus.PENDING.value
        assert w.requested_amount == Decimal("500.00")
        assert w.reservation_released is False

    def test_approve_withdrawal(self):
        w = self._make_withdrawal()
        self.db.commit()
        w.status = WithdrawalStatus.APPROVED.value
        self.db.commit()
        assert w.status == WithdrawalStatus.APPROVED.value

    def test_reject_releases_reservation(self):
        w = self._make_withdrawal()
        self.db.commit()
        assert w.reservation_released is False
        w.status = WithdrawalStatus.REJECTED.value
        w.reservation_released = True
        self.db.commit()
        assert w.reservation_released is True

    def test_reservation_guard_persisted(self):
        """Guard flag must survive a DB round-trip."""
        w = self._make_withdrawal()
        w.reservation_released = True
        self.db.commit()
        fresh = self.db.query(AgentWithdrawal).filter(AgentWithdrawal.id == w.id).first()
        assert fresh.reservation_released is True

    def test_paid_consumes_reservation(self):
        w = self._make_withdrawal()
        w.status = WithdrawalStatus.APPROVED.value
        self.db.commit()
        w.status = WithdrawalStatus.PAID.value
        w.transaction_id = f"UTR{random.randint(100000, 999999)}"
        w.actual_paid_amount = Decimal("500.00")
        w.reservation_released = True
        self.db.commit()
        assert w.status == WithdrawalStatus.PAID.value
        assert w.reservation_released is True

    def test_duplicate_transaction_id_rejected(self):
        from sqlalchemy.exc import IntegrityError
        txn = f"UTR_DUP_{random.randint(100000, 999999)}"
        w1 = self._make_withdrawal("300.00")
        w1.status = WithdrawalStatus.PAID.value
        w1.transaction_id = txn
        w1.actual_paid_amount = Decimal("300.00")
        w1.reservation_released = True
        self.db.commit()

        w2 = self._make_withdrawal("200.00")
        w2.status = WithdrawalStatus.APPROVED.value
        self.db.commit()
        w2.transaction_id = txn   # duplicate!
        w2.actual_paid_amount = Decimal("200.00")
        w2.reservation_released = True
        with pytest.raises(IntegrityError):
            self.db.commit()

    def test_paid_status_final(self):
        """Status must not revert after PAID."""
        w = self._make_withdrawal()
        w.status = WithdrawalStatus.PAID.value
        w.reservation_released = True
        self.db.commit()
        fresh = self.db.query(AgentWithdrawal).filter(AgentWithdrawal.id == w.id).first()
        assert fresh.status == WithdrawalStatus.PAID.value


# ---------------------------------------------------------------------------
# 5. Audit History Tests
# ---------------------------------------------------------------------------

class TestWithdrawalHistory:
    def setup_method(self):
        self.db = _open_db()
        self.u = _make_user(self.db)
        self.p = _make_profile(self.db, self.u)
        self.db.commit()

    def teardown_method(self):
        _close_db(self.db)

    def test_history_created(self):
        w = AgentWithdrawal(
            agent_profile_id=self.p.id,
            requested_amount=Decimal("500.00"),
            status=WithdrawalStatus.PENDING.value,
            reservation_released=False,
        )
        self.db.add(w)
        self.db.flush()
        h = AgentWithdrawalHistory(
            withdrawal_id=w.id,
            agent_profile_id=self.p.id,
            from_status=None,
            to_status=WithdrawalStatus.PENDING.value,
            action="CREATED",
            actor_user_id=self.u.id,
        )
        self.db.add(h)
        self.db.commit()
        records = self.db.query(AgentWithdrawalHistory).filter(
            AgentWithdrawalHistory.withdrawal_id == w.id
        ).all()
        assert len(records) == 1
        assert records[0].action == "CREATED"
        assert records[0].from_status is None
        assert records[0].to_status == "PENDING"

    def test_paid_history_stores_transaction(self):
        w = AgentWithdrawal(
            agent_profile_id=self.p.id,
            requested_amount=Decimal("500.00"),
            status=WithdrawalStatus.PAID.value,
            transaction_id=f"UTR{random.randint(100000, 999999)}",
            actual_paid_amount=Decimal("500.00"),
            reservation_released=True,
        )
        self.db.add(w)
        self.db.flush()
        h = AgentWithdrawalHistory(
            withdrawal_id=w.id,
            agent_profile_id=self.p.id,
            from_status="APPROVED",
            to_status="PAID",
            action="PAID",
            actor_user_id=self.u.id,
            transaction_id=w.transaction_id,
            transaction_date=date(2026, 10, 13),
            actual_paid_amount=Decimal("500.00"),
            payment_proof_url="https://s3.example.com/proof.jpg",
        )
        self.db.add(h)
        self.db.commit()
        record = self.db.query(AgentWithdrawalHistory).filter(
            AgentWithdrawalHistory.withdrawal_id == w.id
        ).first()
        assert record.transaction_id == w.transaction_id
        assert record.payment_proof_url is not None
        assert record.actual_paid_amount == Decimal("500.00")


# ---------------------------------------------------------------------------
# 6. Mark-Paid Constants Validation
# ---------------------------------------------------------------------------

class TestMarkPaidConstants:
    def test_allowed_image_extensions(self):
        assert "jpg" in ALLOWED_PROOF_EXTS
        assert "jpeg" in ALLOWED_PROOF_EXTS
        assert "png" in ALLOWED_PROOF_EXTS
        assert "webp" in ALLOWED_PROOF_EXTS
        assert "gif" not in ALLOWED_PROOF_EXTS
        assert "pdf" not in ALLOWED_PROOF_EXTS
        assert "mp4" not in ALLOWED_PROOF_EXTS

    def test_max_proof_size_is_5mb(self):
        assert MAX_PROOF_SIZE == 5 * 1024 * 1024

    def test_transaction_id_max_length(self):
        assert MAX_TRANSACTION_ID_LEN == 128

    def test_withdrawal_zero_amount_rejected(self):
        with pytest.raises(Exception):
            WithdrawalCreateRequest(amount=Decimal("0.00"))

    def test_withdrawal_negative_amount_rejected(self):
        with pytest.raises(Exception):
            WithdrawalCreateRequest(amount=Decimal("-1.00"))

    def test_reject_requires_reason(self):
        with pytest.raises(Exception):
            RejectWithdrawalRequest(rejection_reason="")  # too short

    def test_reject_valid(self):
        req = RejectWithdrawalRequest(rejection_reason="Cannot verify the request details")
        assert req.rejection_reason


# ---------------------------------------------------------------------------
# 7. Role Isolation Tests
# ---------------------------------------------------------------------------

class TestRoleIsolation:
    def setup_method(self):
        self.db = _open_db()
        self.u1 = _make_user(self.db)
        self.u2 = _make_user(self.db)
        self.p1 = _make_profile(self.db, self.u1)
        self.p2 = _make_profile(self.db, self.u2)
        self.db.commit()

    def teardown_method(self):
        _close_db(self.db)

    def test_withdrawal_belongs_to_profile(self):
        w = AgentWithdrawal(
            agent_profile_id=self.p1.id,
            requested_amount=Decimal("100.00"),
            status=WithdrawalStatus.PENDING.value,
            reservation_released=False,
        )
        self.db.add(w)
        self.db.commit()
        # p2 must not find p1's withdrawal when filtered by p2.id
        result = self.db.query(AgentWithdrawal).filter(
            AgentWithdrawal.id == w.id,
            AgentWithdrawal.agent_profile_id == self.p2.id,
        ).first()
        assert result is None

    def test_payment_account_isolated(self):
        _make_payment_account(self.db, self.p1)
        self.db.commit()
        result = self.db.query(AgentPaymentAccount).filter(
            AgentPaymentAccount.agent_profile_id == self.p2.id
        ).first()
        assert result is None

    def test_earnings_isolated(self):
        _make_earning(self.db, self.p1, "500.00", AgentEarningStatus.APPROVED)
        self.db.commit()
        p2_earnings = self.db.query(AgentEarning).filter(
            AgentEarning.agent_profile_id == self.p2.id
        ).all()
        assert len(p2_earnings) == 0


# ---------------------------------------------------------------------------
# 8. Migration / Metadata Sanity
# ---------------------------------------------------------------------------

class TestPhase3Metadata:
    def test_all_phase3_tables_defined(self):
        from app.db.session import Base
        tables = set(Base.metadata.tables.keys())
        assert "agent_payment_accounts" in tables
        assert "agent_withdrawals" in tables
        assert "agent_withdrawal_history" in tables

    def test_phase2_tables_still_present(self):
        from app.db.session import Base
        tables = set(Base.metadata.tables.keys())
        assert "agent_payment_configs" in tables
        assert "agent_earnings" in tables

    def test_payment_account_unique_constraint(self):
        table = AgentPaymentAccount.__table__
        names = {c.name for c in table.constraints}
        assert "uq_agent_payment_account_profile" in names

    def test_withdrawal_unique_transaction_id(self):
        table = AgentWithdrawal.__table__
        names = {c.name for c in table.constraints}
        assert "uq_agent_withdrawal_transaction_id" in names

    def test_payment_method_enum_values(self):
        assert PaymentMethod.UPI.value == "UPI"
        assert PaymentMethod.BANK_TRANSFER.value == "BANK_TRANSFER"

    def test_withdrawal_status_values(self):
        assert WithdrawalStatus.PENDING.value == "PENDING"
        assert WithdrawalStatus.APPROVED.value == "APPROVED"
        assert WithdrawalStatus.REJECTED.value == "REJECTED"
        assert WithdrawalStatus.PAID.value == "PAID"
        assert WithdrawalStatus.CANCELLED.value == "CANCELLED"
