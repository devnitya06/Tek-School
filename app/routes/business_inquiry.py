"""Public business inquiry route (no auth). Visitors submit inquiries for one or more schools."""
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from app.db.session import get_db
from app.models.school import BusinessInquiry, School
from app.schemas.school import BusinessInquiryResponse
from app.utils.s3 import upload_to_s3
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

router = APIRouter()


def _parse_list(value: Optional[str]) -> List[str]:
    """Parse comma-separated form value into list of non-empty strings."""
    if not value or not value.strip():
        return []
    return [x.strip() for x in value.split(",") if x.strip()]


@router.post("", response_model=BusinessInquiryResponse, status_code=status.HTTP_201_CREATED)
async def create_business_inquiry(
    school_ids: str = Form(..., description="Comma-separated school IDs, e.g. SCH-123,SCH-456"),
    guardian_name: str = Form(..., max_length=255),
    phone: str = Form(..., max_length=20),
    email: str = Form(..., max_length=255),
    location: Optional[str] = Form(None),
    student_name: Optional[str] = Form(None),
    standard_in_academic: Optional[str] = Form(None),
    inquiry_for_class: Optional[str] = Form(None, description="Comma-separated classes, e.g. Class 1,Class 2"),
    desire_to_know: Optional[str] = Form(None, description="Comma-separated items"),
    message: Optional[str] = Form(None),
    files: Optional[List[UploadFile]] = File(None),
    db: Session = Depends(get_db),
):
    """Submit a business inquiry as a visitor (no authentication). Multiple schools and file uploads supported."""
    ids = _parse_list(school_ids)
    if not ids:
        raise HTTPException(status_code=400, detail="At least one school_id is required.")

    # Validate all school_ids exist
    existing = db.query(School.id).filter(School.id.in_(ids)).all()
    existing_ids = {r.id for r in existing}
    invalid_ids = [sid for sid in ids if sid not in existing_ids]
    if invalid_ids:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid school_id(s): {', '.join(invalid_ids)}. No matching school(s) found.",
        )

    inquiry_for_class_list = _parse_list(inquiry_for_class)
    desire_to_know_list = _parse_list(desire_to_know)

    uploaded_urls = []
    if files:
        for f in files:
            if f and f.filename:
                try:
                    url = upload_to_s3(f, "business_inquiry/uploads")
                    uploaded_urls.append(url)
                except Exception as e:
                    raise HTTPException(status_code=400, detail=f"File upload failed: {str(e)}")

    record = BusinessInquiry(
        school_ids=ids,
        guardian_name=guardian_name.strip(),
        phone=phone.strip(),
        email=email.strip(),
        location=location.strip() if location else None,
        student_name=student_name.strip() if student_name else None,
        standard_in_academic=standard_in_academic.strip() if standard_in_academic else None,
        inquiry_for_class=inquiry_for_class_list or None,
        desire_to_know=desire_to_know_list or None,
        files=uploaded_urls if uploaded_urls else None,
        message=message.strip() if message else None,
    )
    db.add(record)
    try:
        db.commit()
        db.refresh(record)
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Database error while saving inquiry.")

    return BusinessInquiryResponse(
        id=record.id,
        school_ids=record.school_ids,
        guardian_name=record.guardian_name,
        phone=record.phone,
        email=record.email,
        location=record.location,
        student_name=record.student_name,
        standard_in_academic=record.standard_in_academic,
        inquiry_for_class=record.inquiry_for_class,
        desire_to_know=record.desire_to_know,
        files=record.files,
        message=record.message,
        created_at=record.created_at,
    )
