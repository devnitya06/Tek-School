"""
Digital Profile Price Configuration routes.
Prefix: /digital-profile
Tags: Digital Profile Pricing

GET  /digital-profile/price-config           → ADMIN, SUPERADMIN, SCHOOL
POST /digital-profile/price-config           → ADMIN, SUPERADMIN
PATCH /digital-profile/price-config/{id}     → ADMIN, SUPERADMIN
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models.billing import DigitalProfilePriceConfig
from app.models.users import User
from app.schemas.billing import (
    PriceConfigCreate,
    PriceConfigListResponse,
    PriceConfigResponse,
    PriceConfigUpdate,
)
from app.schemas.users import UserRole
from app.utils.permission import require_roles

router = APIRouter()


def _require_admin_or_superadmin(
    current_user: User = Depends(get_current_user),
) -> User:
    """ADMIN or SUPERADMIN only."""
    role = current_user.role
    if isinstance(role, str):
        try:
            role = UserRole(role)
        except ValueError:
            pass
    if role not in (UserRole.ADMIN, UserRole.SUPERADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only Admin or Super Admin can perform this action.",
        )
    return current_user


def _require_admin_superadmin_or_school(
    current_user: User = Depends(get_current_user),
) -> User:
    """ADMIN, SUPERADMIN, or SCHOOL (read-only)."""
    role = current_user.role
    if isinstance(role, str):
        try:
            role = UserRole(role)
        except ValueError:
            pass
    if role not in (UserRole.ADMIN, UserRole.SUPERADMIN, UserRole.SCHOOL):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied.",
        )
    return current_user


@router.get(
    "/price-config",
    response_model=PriceConfigListResponse,
    summary="List Digital Profile Price Configurations",
)
def list_price_configs(
    education_associate: Optional[str] = Query(None, description="Filter by education_associate"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_admin_superadmin_or_school),
):
    """
    List all price configurations.
    Roles: ADMIN, SUPER_ADMIN, SCHOOL.
    """
    q = db.query(DigitalProfilePriceConfig)
    if education_associate:
        q = q.filter(
            DigitalProfilePriceConfig.education_associate == education_associate.upper()
        )
    total = q.count()
    rows = q.order_by(DigitalProfilePriceConfig.updated_at.desc()).offset(offset).limit(limit).all()
    return PriceConfigListResponse(
        items=[PriceConfigResponse.model_validate(r) for r in rows],
        total=total,
    )


@router.post(
    "/price-config",
    response_model=PriceConfigResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Digital Profile Price Configuration",
)
def create_price_config(
    payload: PriceConfigCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_admin_or_superadmin),
):
    """
    Create a new price configuration.
    Roles: ADMIN, SUPER_ADMIN.
    """
    config = DigitalProfilePriceConfig(
        education_associate=payload.education_associate.value,
        education_offered=payload.education_offered,
        first_two_viewer_price=payload.first_two_viewer_price,
        next_five_viewer_price=payload.next_five_viewer_price,
        all_other_viewer_price=payload.all_other_viewer_price,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(config)
    db.commit()
    db.refresh(config)
    return PriceConfigResponse.model_validate(config)


@router.patch(
    "/price-config/{config_id}",
    response_model=PriceConfigResponse,
    summary="Update Digital Profile Price Configuration",
)
def update_price_config(
    config_id: int = Path(...),
    payload: PriceConfigUpdate = ...,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_admin_or_superadmin),
):
    """
    Update an existing price configuration.
    Roles: ADMIN, SUPER_ADMIN.
    updated_at is automatically refreshed.
    Historical prices for already-viewed inquiries are never recalculated.
    """
    config = db.query(DigitalProfilePriceConfig).filter(
        DigitalProfilePriceConfig.id == config_id
    ).first()
    if not config:
        raise HTTPException(
            status_code=404,
            detail={"code": "CONFIGURATION_NOT_FOUND", "message": "Price config not found."},
        )

    if payload.education_associate is not None:
        config.education_associate = payload.education_associate.value
    if payload.education_offered is not None:
        config.education_offered = payload.education_offered
    if payload.first_two_viewer_price is not None:
        config.first_two_viewer_price = payload.first_two_viewer_price
    if payload.next_five_viewer_price is not None:
        config.next_five_viewer_price = payload.next_five_viewer_price
    if payload.all_other_viewer_price is not None:
        config.all_other_viewer_price = payload.all_other_viewer_price
    config.updated_by = current_user.id

    db.commit()
    db.refresh(config)
    return PriceConfigResponse.model_validate(config)
