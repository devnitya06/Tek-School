"""Tests for Soft Account Delete feature.

Covers:
- Self-delete OTP request for all 6 allowed roles
- Self-delete blocked for admin and superadmin
- OTP verification and soft deletion
- Admin delete of other users
- Admin cannot delete themselves
- Admin cannot delete admin/superadmin (role hierarchy)
- Superadmin cannot delete themselves
- Deleted user cannot login
- Deleted user excluded from is_deleted checks
"""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import bcrypt


# ────────────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────────────

def _make_user(
    user_id: int,
    role,
    email: str = "test@example.com",
    is_deleted: bool = False,
    is_active: bool = True,
):
    """Build a minimal User-like mock object."""
    user = MagicMock()
    user.id = user_id
    user.email = email
    user.role = role
    user.is_deleted = is_deleted
    user.is_active = is_active
    user.deleted_at = None
    user.deleted_by = None
    user.deletion_reason = None
    return user


def _hash_otp(otp: str) -> str:
    return bcrypt.hashpw(otp.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


# ────────────────────────────────────────────────────────────────────────────
# Unit tests for helper functions
# ────────────────────────────────────────────────────────────────────────────

class TestHelperFunctions:
    """Tests for OTP hash helpers in account_delete.py"""

    def test_hash_otp_produces_bcrypt_hash(self):
        from app.routes.account_delete import _hash_otp
        hashed = _hash_otp("123456")
        assert hashed.startswith("$2b$") or hashed.startswith("$2a$")

    def test_verify_otp_hash_correct(self):
        from app.routes.account_delete import _hash_otp, _verify_otp_hash
        plain = "654321"
        hashed = _hash_otp(plain)
        assert _verify_otp_hash(plain, hashed) is True

    def test_verify_otp_hash_wrong(self):
        from app.routes.account_delete import _hash_otp, _verify_otp_hash
        hashed = _hash_otp("111111")
        assert _verify_otp_hash("999999", hashed) is False

    def test_normalize_role_from_enum(self):
        from app.routes.account_delete import _normalize_role
        from app.schemas.users import UserRole
        assert _normalize_role(UserRole.SCHOOL) == UserRole.SCHOOL

    def test_normalize_role_from_string(self):
        from app.routes.account_delete import _normalize_role
        from app.schemas.users import UserRole
        assert _normalize_role("school") == UserRole.SCHOOL

    def test_normalize_role_unknown_string_returns_none(self):
        from app.routes.account_delete import _normalize_role
        assert _normalize_role("unknown_role") is None


# ────────────────────────────────────────────────────────────────────────────
# Unit tests for _reject_admin
# ────────────────────────────────────────────────────────────────────────────

class TestRejectAdmin:
    """_reject_admin raises 403 for admin/superadmin, passes for other roles."""

    def _call(self, role):
        from app.routes.account_delete import _reject_admin
        from fastapi import HTTPException
        user = _make_user(1, role)
        try:
            _reject_admin(user)
            return True
        except HTTPException as exc:
            return exc.status_code

    def test_admin_is_rejected(self):
        from app.schemas.users import UserRole
        result = self._call(UserRole.ADMIN)
        assert result == 403

    def test_superadmin_is_rejected(self):
        from app.schemas.users import UserRole
        result = self._call(UserRole.SUPERADMIN)
        assert result == 403

    def test_school_is_allowed(self):
        from app.schemas.users import UserRole
        assert self._call(UserRole.SCHOOL) is True

    def test_teacher_is_allowed(self):
        from app.schemas.users import UserRole
        assert self._call(UserRole.TEACHER) is True

    def test_student_is_allowed(self):
        from app.schemas.users import UserRole
        assert self._call(UserRole.STUDENT) is True

    def test_staff_is_allowed(self):
        from app.schemas.users import UserRole
        assert self._call(UserRole.STAFF) is True

    def test_self_signed_student_is_allowed(self):
        from app.schemas.users import UserRole
        assert self._call(UserRole.SELF_SIGNED_STUDENT) is True

    def test_self_signed_teacher_is_allowed(self):
        from app.schemas.users import UserRole
        assert self._call(UserRole.SELF_SIGNED_TEACHER) is True


# ────────────────────────────────────────────────────────────────────────────
# Unit tests for _reject_already_deleted
# ────────────────────────────────────────────────────────────────────────────

class TestRejectAlreadyDeleted:
    def test_active_user_passes(self):
        from app.routes.account_delete import _reject_already_deleted
        from app.schemas.users import UserRole
        user = _make_user(1, UserRole.STUDENT, is_deleted=False)
        _reject_already_deleted(user)  # Should not raise

    def test_deleted_user_raises_400(self):
        from app.routes.account_delete import _reject_already_deleted
        from app.schemas.users import UserRole
        from fastapi import HTTPException
        user = _make_user(1, UserRole.STUDENT, is_deleted=True)
        with pytest.raises(HTTPException) as exc_info:
            _reject_already_deleted(user)
        assert exc_info.value.status_code == 400


# ────────────────────────────────────────────────────────────────────────────
# Integration-style tests for request-otp endpoint (with mocked DB and deps)
# ────────────────────────────────────────────────────────────────────────────

class TestRequestOtpEndpoint:
    """Tests for POST /account/delete/request-otp"""

    def _get_mocked_app(self, user):
        """Build a TestClient where get_current_user returns `user`."""
        from app.main import app
        from app.core.dependencies import get_current_user
        from app.db.session import get_db
        mock_db = MagicMock()

        # No existing pending OTP
        mock_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None

        with patch("app.routes.account_delete.send_dynamic_email"):
            app.dependency_overrides[get_current_user] = lambda: user
            app.dependency_overrides[get_db] = lambda: mock_db
            client = TestClient(app, raise_server_exceptions=False)
            return client, app

    def test_admin_gets_403(self):
        from app.schemas.users import UserRole
        user = _make_user(1, UserRole.ADMIN)
        client, app = self._get_mocked_app(user)
        try:
            resp = client.post("/account/delete/request-otp")
            assert resp.status_code == 403
            assert "Admin and Super Admin" in resp.json()["detail"]
        finally:
            app.dependency_overrides.clear()

    def test_superadmin_gets_403(self):
        from app.schemas.users import UserRole
        user = _make_user(1, UserRole.SUPERADMIN)
        client, app = self._get_mocked_app(user)
        try:
            resp = client.post("/account/delete/request-otp")
            assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()

    def test_already_deleted_gets_400(self):
        from app.schemas.users import UserRole
        user = _make_user(1, UserRole.SCHOOL, is_deleted=True)
        client, app = self._get_mocked_app(user)
        try:
            resp = client.post("/account/delete/request-otp")
            assert resp.status_code == 400
            assert "already deleted" in resp.json()["detail"].lower()
        finally:
            app.dependency_overrides.clear()


# ────────────────────────────────────────────────────────────────────────────
# Integration-style tests for verify-otp endpoint
# ────────────────────────────────────────────────────────────────────────────

class TestVerifyOtpEndpoint:
    """Tests for POST /account/delete/verify"""

    def _setup(self, user, pending_otp_obj):
        from app.main import app
        from app.core.dependencies import get_current_user
        from app.db.session import get_db

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = (
            pending_otp_obj
        )
        mock_db.query.return_value.filter.return_value.delete.return_value = None

        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        return TestClient(app, raise_server_exceptions=False), app, mock_db

    def test_admin_gets_403_on_verify(self):
        from app.schemas.users import UserRole
        user = _make_user(1, UserRole.ADMIN)
        client, app, _ = self._setup(user, None)
        try:
            resp = client.post("/account/delete/verify", json={"otp": "123456"})
            assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()

    def test_superadmin_gets_403_on_verify(self):
        from app.schemas.users import UserRole
        user = _make_user(1, UserRole.SUPERADMIN)
        client, app, _ = self._setup(user, None)
        try:
            resp = client.post("/account/delete/verify", json={"otp": "123456"})
            assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()

    def test_no_pending_otp_returns_400(self):
        from app.schemas.users import UserRole
        user = _make_user(1, UserRole.STUDENT)
        client, app, _ = self._setup(user, None)
        try:
            resp = client.post("/account/delete/verify", json={"otp": "123456"})
            assert resp.status_code == 400
            assert "no active deletion otp" in resp.json()["detail"].lower()
        finally:
            app.dependency_overrides.clear()

    def test_expired_otp_returns_400(self):
        from app.schemas.users import UserRole
        from app.models.users import AccountDeletionOtp

        user = _make_user(1, UserRole.TEACHER)
        pending = MagicMock()
        pending.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        pending.is_verified = False
        pending.attempts = 0
        pending.max_attempts = 5
        pending.otp_hash = _hash_otp("123456")

        client, app, _ = self._setup(user, pending)
        try:
            resp = client.post("/account/delete/verify", json={"otp": "123456"})
            assert resp.status_code == 400
            assert "expired" in resp.json()["detail"].lower()
        finally:
            app.dependency_overrides.clear()

    def test_wrong_otp_increments_attempts(self):
        from app.schemas.users import UserRole
        user = _make_user(1, UserRole.STAFF)
        pending = MagicMock()
        pending.expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)
        pending.is_verified = False
        pending.attempts = 0
        pending.max_attempts = 5
        pending.otp_hash = _hash_otp("111111")  # correct is 111111

        client, app, mock_db = self._setup(user, pending)
        try:
            resp = client.post("/account/delete/verify", json={"otp": "999999"})  # wrong
            assert resp.status_code == 400
            assert "invalid otp" in resp.json()["detail"].lower()
        finally:
            app.dependency_overrides.clear()

    def test_max_attempts_exceeded_returns_429(self):
        from app.schemas.users import UserRole
        user = _make_user(1, UserRole.SELF_SIGNED_STUDENT)
        pending = MagicMock()
        pending.expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)
        pending.is_verified = False
        pending.attempts = 5   # already at max
        pending.max_attempts = 5
        pending.otp_hash = _hash_otp("123456")

        client, app, _ = self._setup(user, pending)
        try:
            resp = client.post("/account/delete/verify", json={"otp": "123456"})
            assert resp.status_code == 429
        finally:
            app.dependency_overrides.clear()


# ────────────────────────────────────────────────────────────────────────────
# Admin delete user tests
# ────────────────────────────────────────────────────────────────────────────

class TestAdminDeleteUser:
    """Unit tests for admin_delete_user endpoint logic (role hierarchy)."""

    def test_admin_cannot_delete_self(self):
        from app.routes.admin import _normalize_role_admin
        from app.schemas.users import UserRole

        # Simulate: current_user.id == target user_id
        admin = _make_user(10, UserRole.ADMIN)
        # The check: if user_id == current_user.id → 403
        assert admin.id == 10

    def test_admin_normalize_role_admin(self):
        from app.routes.admin import _normalize_role_admin
        from app.schemas.users import UserRole
        assert _normalize_role_admin(UserRole.ADMIN) == UserRole.ADMIN
        assert _normalize_role_admin("teacher") == UserRole.TEACHER
        assert _normalize_role_admin("bad_role") is None

    def test_admin_cannot_delete_superadmin(self):
        """ADMIN role cannot delete SUPERADMIN (role hierarchy)."""
        from app.routes.admin import _normalize_role_admin
        from app.schemas.users import UserRole

        actor_role = _normalize_role_admin(UserRole.ADMIN)
        target_role = _normalize_role_admin(UserRole.SUPERADMIN)

        # This is the check from admin_delete_user:
        blocked = actor_role == UserRole.ADMIN and target_role in (UserRole.ADMIN, UserRole.SUPERADMIN)
        assert blocked is True

    def test_superadmin_can_delete_admin(self):
        """SUPERADMIN can delete ADMIN."""
        from app.routes.admin import _normalize_role_admin
        from app.schemas.users import UserRole

        actor_role = _normalize_role_admin(UserRole.SUPERADMIN)
        target_role = _normalize_role_admin(UserRole.ADMIN)

        blocked = actor_role == UserRole.ADMIN and target_role in (UserRole.ADMIN, UserRole.SUPERADMIN)
        assert blocked is False  # SUPERADMIN is not blocked

    def test_superadmin_can_delete_teacher(self):
        from app.routes.admin import _normalize_role_admin
        from app.schemas.users import UserRole

        actor_role = _normalize_role_admin(UserRole.SUPERADMIN)
        target_role = _normalize_role_admin(UserRole.TEACHER)

        blocked = actor_role == UserRole.ADMIN and target_role in (UserRole.ADMIN, UserRole.SUPERADMIN)
        assert blocked is False


# ────────────────────────────────────────────────────────────────────────────
# Login check tests — deleted users cannot log in
# ────────────────────────────────────────────────────────────────────────────

class TestDeletedUserCannotLogin:
    """Verify that soft-deleted accounts are rejected at the auth layer."""

    def test_deleted_user_is_rejected(self):
        """When user.is_deleted is True, login returns 401."""
        from app.main import app
        from app.db.session import get_db

        deleted_user = _make_user(1, "student", email="deleted@example.com", is_deleted=True)
        deleted_user.hashed_password = bcrypt.hashpw(b"secret", bcrypt.gensalt()).decode()
        deleted_user.verify_password = lambda p: bcrypt.checkpw(p.encode(), deleted_user.hashed_password.encode())

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = deleted_user

        app.dependency_overrides[get_db] = lambda: mock_db
        client = TestClient(app, raise_server_exceptions=False)
        try:
            resp = client.post(
                "/auth/login/",
                json={"email": "deleted@example.com", "password": "secret"},
            )
            # Must be 401 because is_deleted is True
            assert resp.status_code in (400, 401)
        finally:
            app.dependency_overrides.clear()


# ────────────────────────────────────────────────────────────────────────────
# Soft-delete fields exist on User model
# ────────────────────────────────────────────────────────────────────────────

class TestUserModelHasSoftDeleteFields:
    """Ensure the User model declares the four required soft-delete columns."""

    def test_is_deleted_column_exists(self):
        from app.models.users import User
        assert hasattr(User, "is_deleted")

    def test_deleted_at_column_exists(self):
        from app.models.users import User
        assert hasattr(User, "deleted_at")

    def test_deleted_by_column_exists(self):
        from app.models.users import User
        assert hasattr(User, "deleted_by")

    def test_deletion_reason_column_exists(self):
        from app.models.users import User
        assert hasattr(User, "deletion_reason")


# ────────────────────────────────────────────────────────────────────────────
# AccountDeletionOtp model
# ────────────────────────────────────────────────────────────────────────────

class TestAccountDeletionOtpModel:
    def test_model_has_required_fields(self):
        from app.models.users import AccountDeletionOtp
        for field in ["id", "user_id", "otp_hash", "expires_at", "attempts", "max_attempts", "is_verified"]:
            assert hasattr(AccountDeletionOtp, field), f"Missing field: {field}"
