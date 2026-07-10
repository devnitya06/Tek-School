from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional, List
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.user_session import UserSession
from app.models.users import User
from app.schemas.admin import *
from app.services.pagination import PaginationParams
from app.core.dependencies import get_current_user
from app.utils.permission import require_roles
from app.schemas.users import UserRole
from sqlalchemy import or_, and_, desc, asc

router = APIRouter()


@router.get("/sessions")
def list_sessions(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    search: Optional[str] = Query(None),
    role: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    browser: Optional[str] = Query(None),
    os: Optional[str] = Query(None),
    device_type: Optional[str] = Query(None),
    country: Optional[str] = Query(None),
    city: Optional[str] = Query(None),
    sort_by: Optional[str] = Query("last_active_at"),
    order: Optional[str] = Query("desc"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.SUPERADMIN)),
):
    q = db.query(UserSession).join(User)

    if search:
        like = f"%{search}%"
        q = q.filter(or_(User.name.ilike(like), User.email.ilike(like), User.phone.ilike(like), UserSession.ip_address.ilike(like)))

    if role:
        q = q.filter(User.role == role)

    if is_active is not None:
        q = q.filter(UserSession.is_active == is_active)

    if browser:
        q = q.filter(UserSession.browser.ilike(f"%{browser}%"))
    if os:
        q = q.filter(UserSession.os.ilike(f"%{os}%"))
    if device_type:
        q = q.filter(UserSession.device_type.ilike(f"%{device_type}%"))
    if country:
        q = q.filter(UserSession.country.ilike(f"%{country}%"))
    if city:
        q = q.filter(UserSession.city.ilike(f"%{city}%"))

    total = q.count()

    # Sorting
    sort_col = getattr(UserSession, sort_by, None) or UserSession.last_active_at
    if order.lower() == "desc":
        q = q.order_by(desc(sort_col))
    else:
        q = q.order_by(asc(sort_col))

    q = q.offset((page - 1) * limit).limit(limit)
    items = []
    for s in q.all():
        items.append(
            {
                "id": s.id,
                "user_id": s.user_id,
                "name": s.user.name if s.user else None,
                "email": s.user.email if s.user else None,
                "role": s.user.role if s.user else None,
                "ip_address": s.ip_address,
                "country": s.country,
                "region": s.region,
                "city": s.city,
                "browser": s.browser,
                "browser_version": s.browser_version,
                "os": s.os,
                "os_version": s.os_version,
                "device_type": s.device_type,
                "login_at": s.login_at,
                "last_active_at": s.last_active_at,
                "is_active": s.is_active,
            }
        )

    total_pages = (total + limit - 1) // limit

    return {
        "success": True,
        "message": "Sessions fetched successfully.",
        "data": {
            "items": items,
            "pagination": {
                "page": page,
                "limit": limit,
                "total": total,
                "total_pages": total_pages,
                "has_next": page * limit < total,
                "has_previous": page > 1,
            },
        },
    }
