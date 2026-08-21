# dependencies.py
from fastapi import Depends, HTTPException, Request, status, UploadFile, File
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.core.security import decode_token
from app.schemas.users import UserRole
from app.models.users import User
from app.db.session import get_db
from typing import Optional
from app.utils.s3 import upload_to_s3

security = HTTPBearer()
# NOTE: Do NOT use HTTPBearer(auto_error=False) for optional auth — it still raises 403
# in some FastAPI/Starlette versions when no Authorization header is present.
# Instead we read the header manually via Request so missing auth silently returns None.


def get_current_user_optional(
    request: Request,
    db: Session = Depends(get_db),
) -> Optional[User]:
    """
    Get current user from JWT if present; otherwise return None (public access).
    Use for endpoints that allow both authenticated and anonymous access.
    No 403 is raised when Authorization header is absent — the endpoint stays public.
    """
    auth_header = request.headers.get("Authorization") or request.headers.get("authorization")
    if not auth_header or not auth_header.lower().startswith("bearer "):
        return None
    token = auth_header.split(" ", 1)[1].strip()
    if not token:
        return None
    payload = decode_token(token)
    if not payload:
        return None
    user_id = payload.get("sub")
    if not user_id:
        return None
    user = db.query(User).filter(User.id == user_id).first()
    return user


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    """
    Get current authenticated user from JWT token.
    
    Note: Business account verification is handled in verify_school_business_access()
    which is called in require_roles() and individual endpoints.
    This ensures business accounts are verified by super admin before accessing any APIs.
    """
    token = credentials.credentials
    payload = decode_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
        )
    
    # Get user from database using ID in token
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    
    return user  # Now returns User model instance

def role_required(role: UserRole):
    def _normalize_role(role_value):
        if isinstance(role_value, UserRole):
            return role_value
        if isinstance(role_value, str):
            try:
                return UserRole(role_value)
            except ValueError:
                return None
        return None

    def role_checker(current_user: User = Depends(get_current_user)):
        current_role = _normalize_role(current_user.role)
        if current_role != role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Operation not permitted for this user role",
            )
        return current_user
    return role_checker

# Specific role checkers
admin_required = role_required(UserRole.ADMIN)
school_required = role_required(UserRole.SCHOOL)
teacher_required = role_required(UserRole.TEACHER)
student_required = role_required(UserRole.STUDENT)
self_signed_teacher_required = role_required(UserRole.SELF_SIGNED_TEACHER)

async def handle_profile_picture_upload(
    user_id: str,
    user_type: str,  # "school", "teacher", "student"
    profile_pic: Optional[UploadFile] = None,
    banner_pic: Optional[UploadFile] = None
):
    result = {}
    
    if profile_pic:
        try:
            profile_pic_url = upload_to_s3(profile_pic, f"{user_type}s/{user_id}/profile")
            result["profile_pic_url"] = profile_pic_url
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to upload profile picture: {str(e)}"
            )
    
    if banner_pic:
        try:
            banner_pic_url = upload_to_s3(banner_pic, f"{user_type}s/{user_id}/banner")
            result["banner_pic_url"] = banner_pic_url
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to upload banner picture: {str(e)}"
            )
    
    return result
