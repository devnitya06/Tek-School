from fastapi import Depends, HTTPException, status
from app.models.users import User
from app.schemas.users import UserRole
from app.core.dependencies import get_current_user  

def require_roles(*roles: UserRole):
    """
    Returns a dependency that checks if the current user has one of the required roles.
    """
    def permission_dependency(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action."
            )
        return current_user
    return permission_dependency
