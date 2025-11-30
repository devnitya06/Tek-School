from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.models.users import User
from app.models.staff import Staff, staff_permissions, StaffPermissionType
from app.schemas.users import UserRole
from app.core.dependencies import get_current_user
from app.db.session import get_db


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


def require_staff_permission(permission: StaffPermissionType):
    """
    Returns a dependency that checks if the current staff user has the required permission.
    Also allows SCHOOL users to access.
    """
    def permission_checker(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ) -> User:
        # SCHOOL users have all permissions
        if current_user.role == UserRole.SCHOOL:
            return current_user
        
        # Check if user is STAFF
        if current_user.role != UserRole.STAFF:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only staff members or school users can access this resource."
            )
        
        # Get staff profile
        staff = db.query(Staff).filter(Staff.user_id == current_user.id).first()
        if not staff:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Staff profile not found."
            )
        
        # Check if staff has the required permission
        from sqlalchemy import select
        stmt = select(staff_permissions).where(
            staff_permissions.c.staff_id == staff.id,
            staff_permissions.c.permission == permission.value
        )
        has_permission = db.execute(stmt).first()
        
        if not has_permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"You do not have the '{permission.value}' permission to perform this action."
            )
        
        return current_user
    
    return permission_checker


def has_staff_permission(staff_id: str, permission: StaffPermissionType, db: Session) -> bool:
    """
    Helper function to check if a staff member has a specific permission.
    Returns True if staff has permission, False otherwise.
    """
    from sqlalchemy import select
    stmt = select(staff_permissions).where(
        staff_permissions.c.staff_id == staff_id,
        staff_permissions.c.permission == permission.value
    )
    has_permission = db.execute(stmt).first()
    
    return has_permission is not None


def get_staff_permissions(staff_id: str, db: Session) -> list[str]:
    """
    Helper function to get all permissions for a staff member.
    Returns a list of permission strings.
    """
    from sqlalchemy import select
    
    stmt = select(staff_permissions.c.permission).where(
        staff_permissions.c.staff_id == staff_id
    )
    result = db.execute(stmt).all()
    
    # Extract enum values properly
    permissions_list = []
    for row in result:
        perm_value = row[0]
        if isinstance(perm_value, StaffPermissionType):
            permissions_list.append(perm_value.value)
        else:
            permissions_list.append(str(perm_value))
    
    return permissions_list
