"""
Demo Management System — Admin Request Routes

Admin endpoints (require ADMIN or SUPERADMIN role):
  GET    /demo/admin/requests
  GET    /demo/admin/requests/{id}
  PATCH  /demo/admin/requests/{id}/status
  POST   /demo/admin/requests/{id}/reschedule
  POST   /demo/admin/requests/{id}/images
  DELETE /demo/admin/requests/{id}/images/{image_id}
  PATCH  /demo/admin/requests/{id}/feedback
"""
from datetime import date, time, datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, UploadFile, File
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.logger import logger
from app.db.session import get_db
from app.models.users import User
from app.schemas.users import UserRole
from app.utils.permission import require_roles
from app.utils.s3 import upload_multipart_file_to_s3, delete_s3_object
from app.demo.exceptions import DemoAPIException, DemoErrorCode
from app.demo.models import (
    DemoConfiguration,
    DemoRequest,
    DemoRequestImage,
)
from app.demo.enums import (
    DemoStatus,
    ACTIVE_DEMO_STATUSES,
    RESCHEDULABLE_STATUSES,
    ALLOWED_STATUS_TRANSITIONS,
)
from app.demo.schemas import (
    DemoStatusUpdate,
    DemoRescheduleRequest,
    DemoFeedbackUpdate,
)
from app.demo.services import (
    DemoSlotService,
    DemoCapacityService,
    DemoEmailService,
    get_configuration_or_404,
    require_active_configuration,
    IMAGE_MAX_COUNT,
    IMAGE_MAX_TOTAL_BYTES,
    ALLOWED_IMAGE_EXTENSIONS,
    ALLOWED_IMAGE_CONTENT_TYPES,
    FEEDBACK_MAX_LENGTH,
)

router = APIRouter(prefix="/demo/admin", tags=["Demo (Admin - Requests)"])

_admin_dep = require_roles(UserRole.ADMIN, UserRole.SUPERADMIN)


def _get_request_or_404(db: Session, request_id: int) -> DemoRequest:
    req = db.query(DemoRequest).filter(DemoRequest.id == request_id).first()
    if not req:
        raise DemoAPIException(
            404,
            DemoErrorCode.REQUEST_NOT_FOUND,
            "Demo request was not found.",
        )
    return req


def _format_request(req: DemoRequest, include_access_code: bool = False) -> dict:
    images = [
        {
            "id": img.id,
            "image_url": img.image_url,
            "file_name": img.file_name,
            "file_size": img.file_size,
            "created_at": img.created_at.isoformat() if img.created_at else None,
        }
        for img in req.images
    ]
    data = {
        "id": req.id,
        "request_code": req.request_code,
        "email": req.email,
        "user_category": req.user_category,
        "institution_name": req.institution_name,
        "full_name": req.full_name,
        "designation": req.designation,
        "phone": req.phone,
        "institution_address": req.institution_address,
        "area_of_interest": req.area_of_interest,
        "config_id": req.config_id,
        "demo_date": str(req.demo_date),
        "start_time": req.start_time.strftime("%H:%M") if req.start_time else None,
        "end_time": req.end_time.strftime("%H:%M") if req.end_time else None,
        "presented_by": req.presented_by,
        "demonstration_link": req.demonstration_link,
        "status": req.status,
        "feedback_message": req.feedback_message,
        "images": images,
        "created_at": req.created_at.isoformat() if req.created_at else None,
        "updated_at": req.updated_at.isoformat() if req.updated_at else None,
    }
    if include_access_code:
        data["access_code"] = req.access_code
    return data


# ─── 12. List Requests ────────────────────────────────────────────────────────

@router.get("/requests")
def list_demo_requests(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    search: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    user_category: Optional[str] = Query(None),
    presented_by: Optional[str] = Query(None),
    demo_date: Optional[str] = Query(None),
    demo_date_from: Optional[str] = Query(None),
    demo_date_to: Optional[str] = Query(None),
    created_date_from: Optional[str] = Query(None),
    created_date_to: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(_admin_dep),
):
    from sqlalchemy import or_

    q = db.query(DemoRequest)

    if search:
        like = f"%{search}%"
        q = q.filter(
            or_(
                DemoRequest.email.ilike(like),
                DemoRequest.full_name.ilike(like),
                DemoRequest.phone.ilike(like),
                DemoRequest.institution_name.ilike(like),
                DemoRequest.request_code.ilike(like),
            )
        )

    if status:
        # Validate status value
        try:
            DemoStatus(status.upper())
        except ValueError:
            raise DemoAPIException(
                422,
                DemoErrorCode.INVALID_STATUS,
                "The selected demo status is invalid.",
            )
        q = q.filter(DemoRequest.status == status.upper())

    if user_category:
        q = q.filter(DemoRequest.user_category == user_category.upper())

    if presented_by:
        q = q.filter(DemoRequest.presented_by.ilike(f"%{presented_by}%"))

    if demo_date:
        try:
            q = q.filter(DemoRequest.demo_date == date.fromisoformat(demo_date))
        except ValueError:
            raise DemoAPIException(422, DemoErrorCode.INVALID_DATE, "Please provide a valid demo date.")

    if demo_date_from:
        try:
            q = q.filter(DemoRequest.demo_date >= date.fromisoformat(demo_date_from))
        except ValueError:
            raise DemoAPIException(422, DemoErrorCode.INVALID_DATE, "Please provide a valid demo date.")

    if demo_date_to:
        try:
            q = q.filter(DemoRequest.demo_date <= date.fromisoformat(demo_date_to))
        except ValueError:
            raise DemoAPIException(422, DemoErrorCode.INVALID_DATE, "Please provide a valid demo date.")

    if created_date_from:
        try:
            q = q.filter(DemoRequest.created_at >= datetime.fromisoformat(created_date_from))
        except ValueError:
            pass

    if created_date_to:
        try:
            q = q.filter(DemoRequest.created_at <= datetime.fromisoformat(created_date_to))
        except ValueError:
            pass

    total = q.count()
    requests = (
        q.order_by(DemoRequest.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    items = []
    for req in requests:
        items.append({
            "id": req.id,
            "request_code": req.request_code,
            "email": req.email,
            "full_name": req.full_name,
            "phone": req.phone,
            "user_category": req.user_category,
            "institution_name": req.institution_name,
            "demo_date": str(req.demo_date),
            "start_time": req.start_time.strftime("%H:%M") if req.start_time else None,
            "end_time": req.end_time.strftime("%H:%M") if req.end_time else None,
            "presented_by": req.presented_by,
            "status": req.status,
            "created_at": req.created_at.isoformat() if req.created_at else None,
        })

    total_pages = (total + page_size - 1) // page_size
    return {
        "success": True,
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


# ─── 13. Request Detail ───────────────────────────────────────────────────────

@router.get("/requests/{request_id}")
def get_demo_request(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_admin_dep),
):
    """Admin detail — includes access_code."""
    req = _get_request_or_404(db, request_id)
    return {
        "success": True,
        "data": _format_request(req, include_access_code=True),
    }


# ─── 14. Change Status ────────────────────────────────────────────────────────

@router.patch("/requests/{request_id}/status")
def update_request_status(
    request_id: int,
    payload: DemoStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(_admin_dep),
):
    req = _get_request_or_404(db, request_id)

    current_status = DemoStatus(req.status)
    new_status = payload.status

    allowed = ALLOWED_STATUS_TRANSITIONS.get(current_status, set())
    if new_status not in allowed:
        raise DemoAPIException(
            409,
            DemoErrorCode.INVALID_STATUS_TRANSITION,
            "This demo status cannot be changed from the current status.",
        )

    req.status = new_status.value
    db.commit()
    db.refresh(req)

    logger.info(
        "[DEMO_REQUEST] Status changed request_id=%d %s→%s by admin user_id=%d",
        req.id,
        current_status.value,
        new_status.value,
        current_user.id,
    )

    return {
        "success": True,
        "message": f"Demo request status updated to {new_status.value}.",
        "data": {"id": req.id, "status": req.status},
    }


# ─── 15. Reschedule ───────────────────────────────────────────────────────────

@router.post("/requests/{request_id}/reschedule")
def reschedule_demo_request(
    request_id: int,
    payload: DemoRescheduleRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(_admin_dep),
):
    """
    Reschedule a demo.
    Backend derives: end_time, presented_by, demonstration_link from config_id.
    Keeps: access_code, request_code.
    Updates: status → RESCHEDULED.
    """
    req = _get_request_or_404(db, request_id)

    # Validate reschedulable status
    current_status = DemoStatus(req.status)
    if current_status not in RESCHEDULABLE_STATUSES:
        raise DemoAPIException(
            409,
            DemoErrorCode.RESCHEDULE_NOT_ALLOWED,
            "This demo cannot be rescheduled in its current status.",
        )

    # Load and validate configuration
    config = get_configuration_or_404(db, payload.config_id)
    require_active_configuration(config)

    # Validate weekday
    DemoSlotService.validate_weekday(config, payload.demo_date)

    # Find slot
    slot_start, slot_end = DemoSlotService.find_slot(config, payload.start_time)

    # Concurrency-safe capacity check (exclude current request)
    try:
        DemoCapacityService.check_and_lock_slot(
            db,
            config,
            payload.demo_date,
            slot_start,
            exclude_request_id=req.id,
        )
    except DemoAPIException as exc:
        # Re-raise DEMO_SLOT_FULL for reschedule context
        if exc.error_code == DemoErrorCode.CAPACITY_CONFLICT:
            raise DemoAPIException(
                409,
                DemoErrorCode.SLOT_FULL,
                "The selected demo time slot is full. Please choose another slot.",
            )
        raise

    old_date = req.demo_date
    old_start = req.start_time

    # Update request
    req.config_id = config.id
    req.demo_date = payload.demo_date
    req.start_time = slot_start
    req.end_time = slot_end
    req.presented_by = config.presented_by
    req.demonstration_link = config.demonstration_link
    req.status = DemoStatus.RESCHEDULED.value
    # access_code and request_code are intentionally NOT changed

    try:
        db.commit()
        db.refresh(req)
    except IntegrityError:
        db.rollback()
        raise DemoAPIException(
            409,
            DemoErrorCode.CAPACITY_CONFLICT,
            "The selected demo slot became unavailable. Please choose another slot.",
        )

    logger.info(
        "[DEMO_REQUEST] Rescheduled request_id=%d from %s %s to %s %s by admin user_id=%d",
        req.id,
        old_date,
        old_start,
        req.demo_date,
        req.start_time,
        current_user.id,
    )

    # Queue reschedule notification asynchronously so admin response stays fast.
    DemoEmailService.queue_reschedule_notification(req)

    return {
        "success": True,
        "message": "Demo request rescheduled successfully.",
        "data": {
            "id": req.id,
            "request_code": req.request_code,
            "status": req.status,
            "demo_date": str(req.demo_date),
            "start_time": req.start_time.strftime("%H:%M"),
            "end_time": req.end_time.strftime("%H:%M"),
            "presented_by": req.presented_by,
            "config_id": req.config_id,
        },
    }


# ─── 16. Upload Images ────────────────────────────────────────────────────────

@router.post("/requests/{request_id}/images", status_code=201)
async def upload_images(
    request_id: int,
    images: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(_admin_dep),
):
    """
    Upload up to 10 images for a demo request.
    Allowed types: JPG, JPEG, PNG, WEBP.
    Max combined size: 10 MB.
    """
    req = _get_request_or_404(db, request_id)

    # Check current image count
    current_count = (
        db.query(DemoRequestImage)
        .filter(DemoRequestImage.demo_request_id == request_id)
        .count()
    )
    if current_count + len(images) > IMAGE_MAX_COUNT:
        raise DemoAPIException(
            409,
            DemoErrorCode.IMAGE_LIMIT_EXCEEDED,
            f"A maximum of {IMAGE_MAX_COUNT} images can be uploaded for a demo request.",
        )

    # Validate each file type
    for img in images:
        ext = (img.filename or "").rsplit(".", 1)[-1].lower() if img.filename else ""
        content_type = (img.content_type or "").lower()
        if ext not in ALLOWED_IMAGE_EXTENSIONS and content_type not in ALLOWED_IMAGE_CONTENT_TYPES:
            raise DemoAPIException(
                422,
                DemoErrorCode.INVALID_IMAGE_TYPE,
                "Invalid image type. Only JPG, JPEG, PNG, and WEBP files are allowed.",
            )

    # Calculate total size
    total_size = 0
    file_data_list = []
    for img in images:
        img.file.seek(0, 2)
        size = img.file.tell()
        img.file.seek(0)
        total_size += size
        file_data_list.append((img, size))

    if total_size > IMAGE_MAX_TOTAL_BYTES:
        raise DemoAPIException(
            413,
            DemoErrorCode.IMAGE_SIZE_EXCEEDED,
            "The total image size cannot exceed 10 MB.",
        )

    # Upload each image
    uploaded = []
    for img, size in file_data_list:
        img.file.seek(0)
        image_url = upload_multipart_file_to_s3(
            img,
            filename_prefix=f"demo_requests/{request_id}/images",
            max_size=IMAGE_MAX_TOTAL_BYTES,
        )
        db_image = DemoRequestImage(
            demo_request_id=request_id,
            image_url=image_url,
            file_name=img.filename,
            file_size=size,
        )
        db.add(db_image)
        uploaded.append(db_image)

    db.commit()
    for img_obj in uploaded:
        db.refresh(img_obj)

    logger.info(
        "[DEMO_IMAGE] Uploaded %d images to request_id=%d by admin user_id=%d",
        len(uploaded),
        request_id,
        current_user.id,
    )

    return {
        "success": True,
        "message": f"{len(uploaded)} image(s) uploaded successfully.",
        "data": [
            {
                "id": img_obj.id,
                "image_url": img_obj.image_url,
                "file_name": img_obj.file_name,
                "file_size": img_obj.file_size,
            }
            for img_obj in uploaded
        ],
    }


# ─── 17. Delete Image ─────────────────────────────────────────────────────────

@router.delete("/requests/{request_id}/images/{image_id}", status_code=204)
def delete_image(
    request_id: int,
    image_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_admin_dep),
):
    # Verify request exists
    _get_request_or_404(db, request_id)

    image = (
        db.query(DemoRequestImage)
        .filter(
            DemoRequestImage.id == image_id,
            DemoRequestImage.demo_request_id == request_id,
        )
        .first()
    )

    if not image:
        raise DemoAPIException(
            404,
            DemoErrorCode.IMAGE_NOT_FOUND,
            "Demo image was not found for this request.",
        )

    image_url = image.image_url
    db.delete(image)
    db.commit()

    # Delete from S3 (best effort)
    try:
        delete_s3_object(image_url)
    except Exception as exc:
        logger.warning("[DEMO_IMAGE] Failed to delete S3 object %s: %s", image_url, exc)

    logger.info(
        "[DEMO_IMAGE] Deleted image_id=%d from request_id=%d by admin user_id=%d",
        image_id,
        request_id,
        current_user.id,
    )
    # 204 No Content
    return None


# ─── 18. Feedback ─────────────────────────────────────────────────────────────

@router.patch("/requests/{request_id}/feedback")
def update_feedback(
    request_id: int,
    payload: DemoFeedbackUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(_admin_dep),
):
    req = _get_request_or_404(db, request_id)

    message = payload.feedback_message.strip() if payload.feedback_message else ""
    if not message:
        raise DemoAPIException(
            422,
            DemoErrorCode.FEEDBACK_REQUIRED,
            "Feedback message is required.",
        )
    if len(message) > FEEDBACK_MAX_LENGTH:
        raise DemoAPIException(
            422,
            DemoErrorCode.FEEDBACK_TOO_LONG,
            "Feedback message exceeds the maximum allowed length.",
        )

    req.feedback_message = message
    db.commit()
    db.refresh(req)

    logger.info(
        "[DEMO_REQUEST] Feedback added to request_id=%d by admin user_id=%d",
        req.id,
        current_user.id,
    )

    return {
        "success": True,
        "message": "Feedback updated successfully.",
        "data": {"id": req.id, "feedback_message": req.feedback_message},
    }
