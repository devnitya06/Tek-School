from datetime import datetime, timedelta, timezone
from typing import List, Optional

from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status, BackgroundTasks
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user_optional
from app.db.session import get_db
from app.models.news import NewsStatus, NewsSubmission
from app.models.school import School
from app.models.users import User
from app.schemas.news import (
    NewsRemarkRequest,
    NewsSubmissionUpdateRequest,
    NewsSubmissionVerifyRequest,
)
from app.schemas.users import UserRole
from app.utils.email_utility import generate_otp, send_raw_email
from app.utils.permission import require_roles_allow_listing_school
from app.utils.s3 import upload_to_s3, delete_s3_object
from app.db.session import SessionLocal

router = APIRouter()


def _to_utc_datetime(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _upload_news_images(images: Optional[List[UploadFile]], school_id: str) -> List[str]:
    if not images:
        return []

    uploaded_urls: List[str] = []
    for image in images:
        if not image or not image.filename:
            continue
        try:
            uploaded_urls.append(upload_to_s3(image, f"schools/{school_id}/news"))
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Image upload failed: {str(exc)}")

    return uploaded_urls


def _cleanup_expired_unverified(db: Session) -> None:
    """Delete expired, unverified news submissions and their S3 images.

    This is a best-effort cleanup: image deletion errors are logged but do not
    stop the DB record from being removed.
    """
    now = datetime.now(timezone.utc)
    expired = (
        db.query(NewsSubmission)
        .filter(NewsSubmission.is_verified.is_(False))
        .filter(NewsSubmission.otp_expires_at != None)
        .filter(NewsSubmission.otp_expires_at < now)
        .all()
    )
    if not expired:
        return

    for sub in expired:
        # Attempt to delete any uploaded images
        if sub.images:
            for img in list(sub.images):
                try:
                    delete_s3_object(img)
                except Exception as e:
                    print(f"Warning: failed to delete S3 image {img}: {e}")
        try:
            db.delete(sub)
        except Exception as e:
            print(f"Warning: failed to delete DB record for news id={getattr(sub, 'id', None)}: {e}")

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"Warning: failed to commit news cleanup: {e}")


def _cleanup_expired_unverified_background() -> None:
    """Background wrapper that creates its own DB session for cleanup."""
    db = SessionLocal()
    try:
        _cleanup_expired_unverified(db)
    finally:
        try:
            db.close()
        except Exception:
            pass


def _resolve_school_for_public_or_auth(
    current_user: Optional[User], db: Session, school_id: Optional[str]
) -> School:
    if current_user is None:
        if not school_id:
            raise HTTPException(
                status_code=400,
                detail="school_id is required for public access. Pass school_id as query parameter.",
            )
        school = db.query(School).filter(School.id == school_id).first()
        if not school:
            raise HTTPException(status_code=404, detail="School not found.")
        return school

    if current_user.role == UserRole.ADMIN:
        if not school_id:
            raise HTTPException(
                status_code=400,
                detail="school_id is required when accessing as admin.",
            )
        school = db.query(School).filter(School.id == school_id).first()
        if not school:
            raise HTTPException(status_code=404, detail="School not found.")
        return school

    if current_user.role == UserRole.SCHOOL:
        school = db.query(School).filter(School.user_id == current_user.id).first()
        if not school:
            raise HTTPException(status_code=404, detail="School profile not found.")
        return school

    raise HTTPException(
        status_code=403,
        detail="Only school and admin users can access this resource.",
    )


def _resolve_school_for_school_or_admin(
    current_user: User, db: Session, school_id: Optional[str]
) -> School:
    if current_user.role == UserRole.ADMIN:
        if not school_id:
            raise HTTPException(
                status_code=400,
                detail="school_id is required when accessing as admin.",
            )
        school = db.query(School).filter(School.id == school_id).first()
        if not school:
            raise HTTPException(status_code=404, detail="School not found.")
        return school

    if current_user.role == UserRole.SCHOOL:
        school = db.query(School).filter(School.user_id == current_user.id).first()
        if not school:
            raise HTTPException(status_code=404, detail="School profile not found.")
        return school

    raise HTTPException(
        status_code=403,
        detail="Only school and admin users can access this resource.",
    )


@router.post("/news", status_code=status.HTTP_201_CREATED)
def submit_news_public(
    title: str = Form(..., min_length=1, max_length=255),
    description: Optional[str] = Form(None),
    full_name: Optional[str] = Form(None),
    phone_no: Optional[str] = Form(None),
    email_id: Optional[str] = Form(None),
    location: Optional[str] = Form(None),
    images: Optional[List[UploadFile]] = File(None),
    school_id: str = Query(..., description="School ID is required for public submissions."),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    school = _resolve_school_for_public_or_auth(current_user, db, school_id)
    uploaded_image_urls = _upload_news_images(images, school.id)

    otp_code = generate_otp(length=6)
    submission = NewsSubmission(
        school_id=school.id,
        title=title.strip(),
        description=description.strip() if description else None,
        images=uploaded_image_urls or None,
        full_name=full_name.strip() if full_name else None,
        phone_no=phone_no.strip() if phone_no else None,
        email_id=email_id.strip() if email_id else None,
        location=location.strip() if location else None,
        user_type="visitor",
        status=NewsStatus.PENDING.value,
        is_verified=False,
        otp_code=otp_code,
        otp_expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
    )

    db.add(submission)
    try:
        db.commit()
        db.refresh(submission)
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to save news submission: {str(exc)}")

    if email_id:
        try:
            body = (
                f"<p>Your OTP for school news verification is <strong>{otp_code}</strong>.</p>"
                f"<p>This code expires in 10 minutes.</p>"
            )
            send_raw_email(email_id, "Verify your school news submission", body)
        except Exception:
            pass

    return {
        "detail": "News submission created. Please verify the OTP to complete the submission.",
        "news_id": submission.id,
        "is_verified": submission.is_verified,
    }


@router.post("/news/verify")
def verify_news_public(
    payload: NewsSubmissionVerifyRequest,
    db: Session = Depends(get_db),
):
    submission = (
        db.query(NewsSubmission)
        .filter(NewsSubmission.id == payload.news_id)
        .first()
    )
    if not submission:
        raise HTTPException(status_code=404, detail="News submission not found.")

    if submission.is_verified:
        raise HTTPException(status_code=400, detail="News submission is already verified.")

    expires_at = _to_utc_datetime(submission.otp_expires_at)
    if expires_at and expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="OTP has expired.")

    if submission.otp_code != payload.otp_code:
        raise HTTPException(status_code=400, detail="Invalid OTP.")

    submission.is_verified = True
    submission.verified_at = datetime.now(timezone.utc)
    submission.otp_code = None
    submission.otp_expires_at = None

    try:
        db.commit()
        db.refresh(submission)
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to verify news submission: {str(exc)}")

    return {
        "detail": "News submission verified successfully.",
        "news_id": submission.id,
        "is_verified": submission.is_verified,
    }


@router.get("/news")
def list_news_public(
    school_id: str = Query(..., description="School ID is required for public news listing."),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
    background_tasks: BackgroundTasks = None,
):
    school = _resolve_school_for_public_or_auth(current_user, db, school_id)
    # Schedule cleanup in background to avoid blocking the request
    try:
        if background_tasks is not None:
            background_tasks.add_task(_cleanup_expired_unverified_background)
        else:
            # Fallback to synchronous cleanup if BackgroundTasks not available
            _cleanup_expired_unverified(db)
    except Exception as e:
        print(f"Warning: scheduling cleanup failed before public list: {e}")
    query = db.query(NewsSubmission).filter(NewsSubmission.school_id == school.id)
    if current_user is None:
        query = query.filter(NewsSubmission.is_verified.is_(True)).filter(
            NewsSubmission.status != NewsStatus.REJECTED.value
        )
    items = query.order_by(NewsSubmission.created_at.desc()).all()
    return {
        "school_id": school.id,
        "items": [
            {
                "id": item.id,
                "school_id": item.school_id,
                "title": item.title,
                "description": item.description,
                "images": item.images,
                "user_type": item.user_type,
                "full_name": item.full_name,
                "phone_no": item.phone_no,
                "email_id": item.email_id,
                "location": item.location,
                "status": item.status,
                "remark": item.remark,
                "is_verified": item.is_verified,
                "created_at": item.created_at,
                "updated_at": item.updated_at,
                "verified_at": item.verified_at,
            }
            for item in items
        ],
    }


@router.get("/news/{news_id}")
def get_news_public(
    news_id: int,
    school_id: str = Query(..., description="School ID is required for public news detail."),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    school = _resolve_school_for_public_or_auth(current_user, db, school_id)
    item = (
        db.query(NewsSubmission)
        .filter(NewsSubmission.id == news_id, NewsSubmission.school_id == school.id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="News submission not found.")
    if current_user is None and (not item.is_verified or item.status == NewsStatus.REJECTED.value):
        raise HTTPException(status_code=404, detail="News submission not found.")
    return {
        "id": item.id,
        "school_id": item.school_id,
        "title": item.title,
        "description": item.description,
        "images": item.images,
        "user_type": item.user_type,
        "full_name": item.full_name,
        "phone_no": item.phone_no,
        "email_id": item.email_id,
        "location": item.location,
        "status": item.status,
        "remark": item.remark,
        "is_verified": item.is_verified,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
        "verified_at": item.verified_at,
    }


@router.post("/school/news", status_code=status.HTTP_201_CREATED)
def create_news_school(
    title: str = Form(..., min_length=1, max_length=255),
    description: Optional[str] = Form(None),
    full_name: Optional[str] = Form(None),
    phone_no: Optional[str] = Form(None),
    email_id: Optional[str] = Form(None),
    location: Optional[str] = Form(None),
    images: Optional[List[UploadFile]] = File(None),
    school_id: Optional[str] = Query(None, description="Required when accessing as admin."),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles_allow_listing_school(UserRole.SCHOOL, UserRole.ADMIN)),
):
    school = _resolve_school_for_school_or_admin(current_user, db, school_id)
    uploaded_image_urls = _upload_news_images(images, school.id)

    item = NewsSubmission(
        school_id=school.id,
        title=title.strip(),
        description=description.strip() if description else None,
        images=uploaded_image_urls or None,
        full_name=full_name.strip() if full_name else None,
        phone_no=phone_no.strip() if phone_no else None,
        email_id=email_id.strip() if email_id else None,
        location=location.strip() if location else None,
        user_type="school",
        status=NewsStatus.APPROVED.value,
        is_verified=True,
        otp_code=None,
        otp_expires_at=None,
    )
    db.add(item)
    try:
        db.commit()
        db.refresh(item)
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to save news item: {str(exc)}")
    return {
        "id": item.id,
        "school_id": item.school_id,
        "title": item.title,
        "description": item.description,
        "images": item.images,
        "user_type": item.user_type,
        "full_name": item.full_name,
        "phone_no": item.phone_no,
        "email_id": item.email_id,
        "location": item.location,
        "status": item.status,
        "remark": item.remark,
        "is_verified": item.is_verified,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
        "verified_at": item.verified_at,
    }


@router.get("/school/news")
def list_news_school(
    school_id: Optional[str] = Query(None, description="Required when accessing as admin."),
    status: Optional[str] = Query(None, description="Optional filter by status: pending, approved, rejected"),
    user_type: Optional[str] = Query(None, description="Optional filter by user_type: visitor or school"),
    from_date: Optional[date] = Query(None, description="Filter from this date (inclusive)"),
    to_date: Optional[date] = Query(None, description="Filter up to this date (inclusive)"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(10, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles_allow_listing_school(UserRole.SCHOOL, UserRole.ADMIN)),
    background_tasks: BackgroundTasks = None,
):
    school = _resolve_school_for_school_or_admin(current_user, db, school_id)
    # Schedule background cleanup so admin/school view doesn't show stale pending items
    try:
        if background_tasks is not None:
            background_tasks.add_task(_cleanup_expired_unverified_background)
        else:
            _cleanup_expired_unverified(db)
    except Exception as e:
        print(f"Warning: scheduling cleanup failed before school list: {e}")
    query = (
        db.query(NewsSubmission)
        .filter(NewsSubmission.school_id == school.id)
        .filter(NewsSubmission.is_verified.is_(True))
    )

    if status:
        query = query.filter(NewsSubmission.status == status.strip().lower())

    if user_type:
        query = query.filter(NewsSubmission.user_type == user_type.strip().lower())

    if from_date:
        query = query.filter(NewsSubmission.created_at >= datetime.combine(from_date, datetime.min.time(), tzinfo=timezone.utc))

    if to_date:
        end_of_day = datetime.combine(to_date, datetime.max.time().replace(microsecond=0), tzinfo=timezone.utc)
        query = query.filter(NewsSubmission.created_at <= end_of_day)

    total_items = query.count()
    total_pages = (total_items + page_size - 1) // page_size if total_items else 0
    offset = (page - 1) * page_size
    items = query.order_by(NewsSubmission.created_at.desc()).offset(offset).limit(page_size).all()

    return {
        "school_id": school.id,
        "page": page,
        "page_size": page_size,
        "total_items": total_items,
        "total_pages": total_pages,
        "has_next": page < total_pages,
        "has_previous": page > 1,
        "filters": {
            "status": status,
            "user_type": user_type,
            "from_date": from_date.isoformat() if from_date else None,
            "to_date": to_date.isoformat() if to_date else None,
        },
        "items": [
            {
                "id": item.id,
                "school_id": item.school_id,
                "title": item.title,
                "description": item.description,
                "images": item.images,
                "user_type": item.user_type,
                "full_name": item.full_name,
                "phone_no": item.phone_no,
                "email_id": item.email_id,
                "location": item.location,
                "status": item.status,
                "remark": item.remark,
                "is_verified": item.is_verified,
                "created_at": item.created_at,
                "updated_at": item.updated_at,
                "verified_at": item.verified_at,
            }
            for item in items
        ],
    }


@router.get("/school/news/{news_id}")
def get_news_school(
    news_id: int,
    school_id: Optional[str] = Query(None, description="Required when accessing as admin."),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles_allow_listing_school(UserRole.SCHOOL, UserRole.ADMIN)),
):
    school = _resolve_school_for_school_or_admin(current_user, db, school_id)
    item = (
        db.query(NewsSubmission)
        .filter(NewsSubmission.id == news_id, NewsSubmission.school_id == school.id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="News submission not found.")
    return {
        "id": item.id,
        "school_id": item.school_id,
        "title": item.title,
        "description": item.description,
        "images": item.images,
        "user_type": item.user_type,
        "full_name": item.full_name,
        "phone_no": item.phone_no,
        "email_id": item.email_id,
        "location": item.location,
        "status": item.status,
        "remark": item.remark,
        "is_verified": item.is_verified,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
        "verified_at": item.verified_at,
    }


@router.patch("/school/news/{news_id}")
def update_news_school(
    news_id: int,
    payload: NewsSubmissionUpdateRequest,
    school_id: Optional[str] = Query(None, description="Required when accessing as admin."),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles_allow_listing_school(UserRole.SCHOOL, UserRole.ADMIN)),
):
    school = _resolve_school_for_school_or_admin(current_user, db, school_id)
    item = (
        db.query(NewsSubmission)
        .filter(NewsSubmission.id == news_id, NewsSubmission.school_id == school.id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="News submission not found.")

    if payload.title is not None:
        item.title = payload.title.strip()
    if payload.description is not None:
        item.description = payload.description.strip() if payload.description else None
    if payload.full_name is not None:
        item.full_name = payload.full_name.strip() if payload.full_name else None
    if payload.phone_no is not None:
        item.phone_no = payload.phone_no.strip() if payload.phone_no else None
    if payload.email_id is not None:
        item.email_id = payload.email_id.strip() if payload.email_id else None
    if payload.location is not None:
        item.location = payload.location.strip() if payload.location else None
    if payload.status is not None:
        item.status = payload.status.strip().lower()
    if payload.remark is not None:
        item.remark = payload.remark.strip() if payload.remark else None

    try:
        db.commit()
        db.refresh(item)
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update news item: {str(exc)}")

    return {
        "id": item.id,
        "school_id": item.school_id,
        "title": item.title,
        "description": item.description,
        "images": item.images,
        "user_type": item.user_type,
        "full_name": item.full_name,
        "phone_no": item.phone_no,
        "email_id": item.email_id,
        "location": item.location,
        "status": item.status,
        "remark": item.remark,
        "is_verified": item.is_verified,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
        "verified_at": item.verified_at,
    }


@router.delete("/school/news/{news_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_news_school(
    news_id: int,
    school_id: Optional[str] = Query(None, description="Required when accessing as admin."),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles_allow_listing_school(UserRole.SCHOOL, UserRole.ADMIN)),
):
    school = _resolve_school_for_school_or_admin(current_user, db, school_id)
    item = (
        db.query(NewsSubmission)
        .filter(NewsSubmission.id == news_id, NewsSubmission.school_id == school.id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="News submission not found.")

    db.delete(item)
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete news item: {str(exc)}")

    return None


@router.patch("/school/news/{news_id}/remark")
def remark_news_school(
    news_id: int,
    payload: NewsRemarkRequest,
    school_id: Optional[str] = Query(None, description="Required when accessing as admin."),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles_allow_listing_school(UserRole.SCHOOL, UserRole.ADMIN)),
):
    school = _resolve_school_for_school_or_admin(current_user, db, school_id)
    item = (
        db.query(NewsSubmission)
        .filter(NewsSubmission.id == news_id, NewsSubmission.school_id == school.id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="News submission not found.")

    if payload.status is not None:
        item.status = payload.status.strip().lower()
    if payload.remark is not None:
        item.remark = payload.remark.strip() if payload.remark else None

    try:
        db.commit()
        db.refresh(item)
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update news remark: {str(exc)}")

    return {
        "id": item.id,
        "school_id": item.school_id,
        "status": item.status,
        "remark": item.remark,
    }
