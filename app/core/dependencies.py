# dependencies.py
from fastapi import Depends, HTTPException, status,UploadFile,File
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.core.security import decode_token
from app.schemas.users import UserRole
from app.models.users import User
from app.db.session import get_db
from typing import Optional
from app.utils.s3 import upload_to_s3

security = HTTPBearer()

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
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
    def role_checker(current_user: User = Depends(get_current_user)):
        if current_user.role != role.value:
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
