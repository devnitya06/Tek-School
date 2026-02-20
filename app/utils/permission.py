from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.models.users import User
from app.models.staff import Staff, staff_permissions, StaffPermissionType
from app.models.school import School, SchoolAccountType
from app.schemas.users import UserRole
from app.core.dependencies import get_current_user
from app.db.session import get_db


def require_roles(*roles: UserRole):
    """
    Returns a dependency that checks if the current user has one of the required roles.
    If SCHOOL role is included, also verifies business account access.
    
    IMPORTANT: For business accounts, super admin verification is REQUIRED before accessing any APIs.
    """
    def permission_dependency(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ) -> User:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action."
            )
        
        # ✅ If SCHOOL role is required, verify business account access
        # This ensures business accounts are verified by super admin before accessing ANY APIs
        if UserRole.SCHOOL in roles and current_user.role == UserRole.SCHOOL:
            verify_school_business_access(current_user, db)
        
        return current_user
    return permission_dependency


def require_roles_allow_listing_school(*roles: UserRole):
    """
    Same as require_roles but does NOT verify business account for SCHOOL.
    Use for APIs that both listing and business schools can access (e.g. school profile,
    school-info, class-fees, team-members, excellent-students, catalogue, photo-gallery, listed-students).
    """
    def permission_dependency(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ) -> User:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action."
            )
        # Do NOT call verify_school_business_access — allow listing schools
        return current_user
    return permission_dependency


def require_staff_permission(permission: StaffPermissionType):
    """
    Returns a dependency that checks if the current staff user has the required permission.
    Also allows SCHOOL users to access (but requires business account verification).
    """
    def permission_checker(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ) -> User:
        # SCHOOL users have all permissions, but must be verified business accounts
        if current_user.role == UserRole.SCHOOL:
            verify_school_business_access(current_user, db)
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


def require_business_account(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> User:
    """
    Check if school has business account access.
    Business accounts have both listing + business permissions.
    Listing accounts are blocked from business features.
    """
    if current_user.role != UserRole.SCHOOL:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only school users can access this resource"
        )
    
    school = db.query(School).filter(School.user_id == current_user.id).first()
    if not school:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="School profile not found"
        )
    
    # Check if has business access
    if school.account_type != SchoolAccountType.BUSINESS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This feature requires a business account. Please upgrade your account."
        )
    
    # Also check if business is approved (business accounts need approval for business features)
    if not school.is_business_approved:
        raise HTTPException(
            status_code=423,  # 423 Locked - Account pending admin verification
            detail="Your business account is pending approval. Please wait for admin verification."
        )
    
    return current_user


def is_business_account(current_user: User, db: Session) -> bool:
    """
    Helper function to check if the current school user has a business account.
    Returns True if business account (and approved), False otherwise.
    """
    if current_user.role != UserRole.SCHOOL:
        return False
    
    school = db.query(School).filter(School.user_id == current_user.id).first()
    if not school:
        return False
    
    # Business account and approved
    return school.account_type == SchoolAccountType.BUSINESS and school.is_business_approved


def require_school_or_business(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> User:
    """
    Check if user is SCHOOL role AND has business account (approved).
    This replaces UserRole.SCHOOL checks for business-only features.
    Listing accounts are blocked.
    """
    if current_user.role != UserRole.SCHOOL:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only school users can access this resource"
        )
    
    school = db.query(School).filter(School.user_id == current_user.id).first()
    if not school:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="School profile not found"
        )
    
    # Check if has business account and is approved
    if school.account_type != SchoolAccountType.BUSINESS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This feature requires a business account. Please upgrade your account."
        )
    
    if not school.is_business_approved:
        raise HTTPException(
            status_code=423,  # 423 Locked - Account pending admin verification
            detail="Your business account is pending approval. Please wait for admin verification."
        )
    
    return current_user


def check_school_business_access(current_user: User, db: Session) -> bool:
    """
    Helper function to check if school user has business account access.
    Returns True if business account and approved, False otherwise.
    """
    if current_user.role != UserRole.SCHOOL:
        return False
    
    school = db.query(School).filter(School.user_id == current_user.id).first()
    if not school:
        return False
    
    # Business account and approved
    return school.account_type == SchoolAccountType.BUSINESS and school.is_business_approved


def verify_school_business_access(current_user: User, db: Session):
    """
    Verify that SCHOOL user has business account access.
    Raises HTTPException if not business account or not approved by super admin.
    Use this in endpoints that require business account (not listing).
    
    IMPORTANT: Business accounts MUST be verified by super admin before accessing any APIs.
    """
    if current_user.role != UserRole.SCHOOL:
        return  # Not a school user, let other checks handle it
    
    school = db.query(School).filter(School.user_id == current_user.id).first()
    if not school:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="School profile not found"
        )
    
    # Check if has business account
    if school.account_type != SchoolAccountType.BUSINESS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This feature requires a business account. Please upgrade your account."
        )
    
    # CRITICAL: Business accounts MUST be verified by super admin before accessing ANY APIs
    if not school.is_business_approved:
        raise HTTPException(
            status_code=423,  # 423 Locked - Account pending admin verification
            detail="Your business account is not verified by admin yet. Please wait for admin verification before accessing any APIs."
        )
