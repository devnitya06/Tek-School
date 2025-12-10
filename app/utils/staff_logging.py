from sqlalchemy.orm import Session
from app.models.staff import ActionType, ResourceType
from app.models.school import School
from app.models.staff import Staff
from app.models.teachers import Teacher
from app.models.users import User
from app.models.staff import ActivityLog
from typing import Optional, Dict, Any


def log_action(
    db: Session,
    current_user: User,
    action_type: ActionType,
    resource_type: ResourceType,
    resource_id: Optional[str] = None,
    description: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> Optional[ActivityLog]:
    """
    Log an action to the activity log for any user (school, staff, teacher, etc.).
    
    Args:
        db: Database session
        current_user: Current user performing the action
        action_type: Type of action (create, update, delete, approve, decline)
        resource_type: Type of resource (student, teacher, leave_request, class, transport)
        resource_id: ID of the resource acted upon
        description: Human-readable description
        metadata: Additional data about the action
    
    Returns:
        ActivityLog if logged, None otherwise
    """
    # Get school_id based on user role
    school_id = None
    
    if current_user.role.value == "school":
        school = db.query(School).filter(School.user_id == current_user.id).first()
        if school:
            school_id = school.id
    elif current_user.role.value == "staff":
        staff = db.query(Staff).filter(Staff.user_id == current_user.id).first()
        if staff:
            school_id = staff.school_id
    elif current_user.role.value == "teacher":
        teacher = db.query(Teacher).filter(Teacher.user_id == current_user.id).first()
        if teacher:
            school_id = teacher.school_id
    
    if not school_id:
        return None
    
    # Create log entry
    log = ActivityLog(
        user_id=current_user.id,
        user_role=current_user.role.value,
        school_id=school_id,
        action_type=action_type,
        resource_type=resource_type,
        resource_id=resource_id,
        description=description,
        action_metadata=metadata
    )
    
    db.add(log)
    db.commit()
    db.refresh(log)
    
    return log

