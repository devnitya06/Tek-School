"""
Complete logout all users: deactivate sessions + invalidate ALL tokens (access + refresh).
This prevents users from using any tokens and forces them to re-login.
"""
from datetime import datetime, timezone, timedelta
from app.db.session import SessionLocal
from app.models.user_session import UserSession
from app.models.users import Token


def logout_all_users_complete():
    """
    Complete logout: deactivate sessions + expire all tokens (access + refresh).
    This prevents users from using any tokens and forces them to re-login.
    """
    db = SessionLocal()
    try:
        # 1. Deactivate all sessions
        now = datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)
        session_count = db.query(UserSession).filter(
            UserSession.is_active == True
        ).update({
            UserSession.is_active: False,
            UserSession.last_active_at: now
        })
        
        # 2. Expire ALL tokens (access + refresh) - set expires_at to now
        past_time = datetime.now(timezone.utc)
        token_count = db.query(Token).update({
            Token.expires_at: past_time
        })
        
        # 3. Alternative: Delete all tokens completely (uncomment if you prefer hard delete)
        # token_count = db.query(Token).delete()
        
        db.commit()
        print(f"✓ Deactivated {session_count} sessions")
        print(f"✓ Expired {token_count} access & refresh tokens")
        print("✓ All users must login again")
        return session_count, token_count
        
    except Exception as e:
        db.rollback()
        print(f"✗ Error: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    logout_all_users_complete()
