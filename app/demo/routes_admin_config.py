"""
Demo Management System — Admin Configuration Routes

Admin endpoints (require ADMIN or SUPERADMIN role):
  GET   /demo/admin/configurations
  POST  /demo/admin/configurations
  GET   /demo/admin/configurations/{id}
  PUT   /demo/admin/configurations/{id}
  PATCH /demo/admin/configurations/{id}/status
"""
from datetime import time
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.logger import logger
from app.db.session import get_db
from app.models.users import User
from app.schemas.users import UserRole
from app.utils.permission import require_roles
from app.demo.exceptions import DemoAPIException, DemoErrorCode
from app.demo.models import DemoConfiguration
from app.demo.enums import DemoDay
from app.demo.schemas import (
    DemoConfigurationCreate,
    DemoConfigurationUpdate,
    DemoConfigurationStatusUpdate,
    DemoConfigurationResponse,
)
from app.demo.services import (
    DemoSlotService,
    get_configuration_or_404,
    validate_time_range,
    _parse_hhmm,
)

router = APIRouter(prefix="/demo/admin", tags=["Demo (Admin - Config)"])

_admin_dep = require_roles(UserRole.ADMIN, UserRole.SUPERADMIN)


def _validate_config_payload(data: DemoConfigurationCreate) -> tuple:
    """Validate and parse configuration fields. Returns (start_time, end_time)."""

    # Validate time range
    start_time, end_time = validate_time_range(data.start_time, data.end_time)

    # Validate user_limit
    if data.user_limit <= 0:
        raise DemoAPIException(
            422,
            DemoErrorCode.INVALID_USER_LIMIT,
            "User limit must be greater than zero.",
        )

    # Validate demo_days
    if not data.demo_days:
        raise DemoAPIException(
            422,
            DemoErrorCode.DAYS_REQUIRED,
            "At least one demo day must be selected.",
        )

    # Validate presenter
    if not data.presented_by or not data.presented_by.strip():
        raise DemoAPIException(
            422,
            DemoErrorCode.PRESENTER_REQUIRED,
            "Demo presenter is required.",
        )

    # Validate demonstration link
    if not data.demonstration_link or not data.demonstration_link.strip():
        raise DemoAPIException(
            422,
            DemoErrorCode.LINK_REQUIRED,
            "Demonstration link is required.",
        )

    # Validate that the time range generates at least one slot
    dummy_config = type("DummyConfig", (), {
        "start_time": start_time,
        "end_time": end_time,
    })()
    DemoSlotService.validate_configuration_slots(dummy_config)

    return start_time, end_time


# ─── 7. List Configurations ───────────────────────────────────────────────────

@router.get("/configurations")
def list_configurations(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100, alias="page_size"),
    is_active: Optional[bool] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(_admin_dep),
):
    q = db.query(DemoConfiguration)
    if is_active is not None:
        q = q.filter(DemoConfiguration.is_active == is_active)
    q = q.order_by(DemoConfiguration.created_at.desc())

    total = q.count()
    configs = q.offset((page - 1) * page_size).limit(page_size).all()

    items = []
    for c in configs:
        items.append({
            "id": c.id,
            "start_time": c.start_time.strftime("%H:%M"),
            "end_time": c.end_time.strftime("%H:%M"),
            "user_limit": c.user_limit,
            "demo_days": c.demo_days,
            "presented_by": c.presented_by,
            "demonstration_link": c.demonstration_link,
            "is_active": c.is_active,
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "updated_at": c.updated_at.isoformat() if c.updated_at else None,
        })

    total_pages = (total + page_size - 1) // page_size
    return {
        "success": True,
        "message": "Configurations fetched successfully.",
        "data": {
            "items": items,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": total_pages,
                "has_next": page * page_size < total,
                "has_previous": page > 1,
            },
        },
    }


# ─── 8. Create Configuration ─────────────────────────────────────────────────

@router.post("/configurations", status_code=201)
def create_configuration(
    payload: DemoConfigurationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(_admin_dep),
):
    start_time, end_time = _validate_config_payload(payload)

    config = DemoConfiguration(
        start_time=start_time,
        end_time=end_time,
        user_limit=payload.user_limit,
        demo_days=[d.value for d in payload.demo_days],
        presented_by=payload.presented_by.strip(),
        demonstration_link=payload.demonstration_link.strip(),
        is_active=payload.is_active,
    )
    db.add(config)
    db.commit()
    db.refresh(config)

    logger.info(
        "[DEMO_CONFIG] Created config id=%d by admin user_id=%d",
        config.id,
        current_user.id,
    )

    return {
        "success": True,
        "message": "Demo configuration created successfully.",
        "data": {
            "id": config.id,
            "start_time": config.start_time.strftime("%H:%M"),
            "end_time": config.end_time.strftime("%H:%M"),
            "user_limit": config.user_limit,
            "demo_days": config.demo_days,
            "presented_by": config.presented_by,
            "demonstration_link": config.demonstration_link,
            "is_active": config.is_active,
            "created_at": config.created_at.isoformat() if config.created_at else None,
        },
    }


# ─── 9. Get Configuration ─────────────────────────────────────────────────────

@router.get("/configurations/{config_id}")
def get_configuration(
    config_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_admin_dep),
):
    config = get_configuration_or_404(db, config_id)

    return {
        "success": True,
        "data": {
            "id": config.id,
            "start_time": config.start_time.strftime("%H:%M"),
            "end_time": config.end_time.strftime("%H:%M"),
            "user_limit": config.user_limit,
            "demo_days": config.demo_days,
            "presented_by": config.presented_by,
            "demonstration_link": config.demonstration_link,
            "is_active": config.is_active,
            "created_at": config.created_at.isoformat() if config.created_at else None,
            "updated_at": config.updated_at.isoformat() if config.updated_at else None,
        },
    }


# ─── 10. Update Configuration ─────────────────────────────────────────────────

@router.put("/configurations/{config_id}")
def update_configuration(
    config_id: int,
    payload: DemoConfigurationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(_admin_dep),
):
    """
    Update a configuration. Existing DemoRequests are NOT modified —
    they retain the presenter/link/time they were booked with.
    """
    config = get_configuration_or_404(db, config_id)
    start_time, end_time = _validate_config_payload(payload)

    config.start_time = start_time
    config.end_time = end_time
    config.user_limit = payload.user_limit
    config.demo_days = [d.value for d in payload.demo_days]
    config.presented_by = payload.presented_by.strip()
    config.demonstration_link = payload.demonstration_link.strip()
    config.is_active = payload.is_active

    db.commit()
    db.refresh(config)

    logger.info(
        "[DEMO_CONFIG] Updated config id=%d by admin user_id=%d",
        config.id,
        current_user.id,
    )

    return {
        "success": True,
        "message": "Demo configuration updated successfully.",
        "data": {
            "id": config.id,
            "start_time": config.start_time.strftime("%H:%M"),
            "end_time": config.end_time.strftime("%H:%M"),
            "user_limit": config.user_limit,
            "demo_days": config.demo_days,
            "presented_by": config.presented_by,
            "demonstration_link": config.demonstration_link,
            "is_active": config.is_active,
            "updated_at": config.updated_at.isoformat() if config.updated_at else None,
        },
    }


# ─── 11. Configuration Status ─────────────────────────────────────────────────

@router.patch("/configurations/{config_id}/status")
def update_configuration_status(
    config_id: int,
    payload: DemoConfigurationStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(_admin_dep),
):
    config = get_configuration_or_404(db, config_id)
    config.is_active = payload.is_active
    db.commit()
    db.refresh(config)

    status_str = "activated" if config.is_active else "deactivated"
    logger.info(
        "[DEMO_CONFIG] Config id=%d %s by admin user_id=%d",
        config.id,
        status_str,
        current_user.id,
    )

    return {
        "success": True,
        "message": f"Demo configuration {status_str} successfully.",
        "data": {"id": config.id, "is_active": config.is_active},
    }
