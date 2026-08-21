from typing import Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user_optional, get_current_user
from app.db.session import get_db
from app.models.school import DigitalProspectus, School
from app.models.users import User
from app.schemas.prospectus import ProspectusResponse
from app.schemas.users import UserRole
from app.utils.permission import require_roles_allow_listing_school
from app.utils.s3 import delete_s3_object, upload_multipart_file_to_s3

router = APIRouter(prefix="/prospectus", tags=["Digital Prospectus"])

# ── constants ─────────────────────────────────────────────────────────────────
MAX_PDF_SIZE = 5 * 1024 * 1024          # 5 MB
ALLOWED_EXTENSIONS = {"pdf"}


# ── helpers ───────────────────────────────────────────────────────────────────

def _resolve_school_admin(
    db: Session,
    current_user: User,
    school_id: Optional[str],
) -> School:
    """Return School for admin/superadmin, requiring school_id query param."""
    if not school_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="school_id is required for admin access.",
        )
    school = db.query(School).filter(School.id == school_id).first()
    if not school:
        raise HTTPException(status_code=404, detail="School not found.")
    return school


def _resolve_school_for_user(
    db: Session,
    current_user: User,
    school_id: Optional[str],
) -> School:
    """
    Resolve the target school based on caller role:
      - SCHOOL           -> own school (no school_id param needed)
      - ADMIN/SUPERADMIN -> school_id param required
    """
    role = current_user.role
    if isinstance(role, str):
        try:
            role = UserRole(role)
        except ValueError:
            pass

    if role in (UserRole.ADMIN, UserRole.SUPERADMIN):
        return _resolve_school_admin(db, current_user, school_id)

    # SCHOOL role: look up by user_id
    school = db.query(School).filter(School.user_id == current_user.id).first()
    if not school:
        raise HTTPException(status_code=404, detail="School not found.")
    return school


def _validate_pdf_upload(file: UploadFile) -> int:
    """Validate extension and size; return file size in bytes."""
    ext = (
        file.filename.rsplit(".", 1)[-1].lower()
        if file.filename and "." in file.filename
        else ""
    )
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF files are allowed for the Digital Prospectus.",
        )
    file.file.seek(0, 2)
    file_size = file.file.tell()
    file.file.seek(0)
    if file_size > MAX_PDF_SIZE:
        mb = file_size / (1024 * 1024)
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File size exceeds the maximum allowed size (5 MB). Uploaded: {mb:.2f} MB.",
        )
    return file_size


# ── endpoints ─────────────────────────────────────────────────────────────────

@router.post("/upload", response_model=ProspectusResponse, status_code=status.HTTP_200_OK)
def upload_prospectus(
    file: UploadFile = File(...),
    school_id: Optional[str] = Query(
        None,
        description="Required for admin/superadmin. Ignored for school role.",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles_allow_listing_school(UserRole.SCHOOL, UserRole.ADMIN, UserRole.SUPERADMIN)
    ),
):
    """
    Upload a Digital Prospectus PDF for a school.

    - School: no school_id param needed — uploads for their own school.
    - Admin/SuperAdmin: pass ?school_id= to target a specific school.
    - Max 1 prospectus per school (replaces existing file + deletes old from S3).
    - Max file size: 5 MB. Only PDF accepted.
    """
    school = _resolve_school_for_user(db, current_user, school_id)
    file_size = _validate_pdf_upload(file)

    # Upload to S3
    try:
        file_url = upload_multipart_file_to_s3(
            file,
            f"schools/{school.id}/prospectus",
            max_size=MAX_PDF_SIZE,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=(
                status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
                if "size" in str(exc).lower()
                else status.HTTP_400_BAD_REQUEST
            ),
            detail=str(exc),
        )

    existing: Optional[DigitalProspectus] = (
        db.query(DigitalProspectus)
        .filter(DigitalProspectus.school_id == school.id)
        .first()
    )

    if existing:
        # Delete old S3 object (best-effort)
        try:
            delete_s3_object(existing.file_url)
        except Exception:
            pass
        existing.file_url = file_url
        existing.file_name = file.filename
        existing.file_size = file_size
        db.commit()
        db.refresh(existing)
        return existing

    prospectus = DigitalProspectus(
        school_id=school.id,
        file_url=file_url,
        file_name=file.filename,
        file_size=file_size,
    )
    db.add(prospectus)
    db.commit()
    db.refresh(prospectus)
    return prospectus


@router.delete("/delete", status_code=status.HTTP_200_OK)
def delete_prospectus(
    school_id: Optional[str] = Query(
        None,
        description="Required for admin/superadmin. Ignored for school role.",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles_allow_listing_school(UserRole.SCHOOL, UserRole.ADMIN, UserRole.SUPERADMIN)
    ),
):
    """
    Delete the Digital Prospectus for a school.

    - School: no school_id param needed.
    - Admin/SuperAdmin: pass ?school_id=.
    """
    school = _resolve_school_for_user(db, current_user, school_id)

    existing: Optional[DigitalProspectus] = (
        db.query(DigitalProspectus)
        .filter(DigitalProspectus.school_id == school.id)
        .first()
    )
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No Digital Prospectus found for this school.",
        )

    # Delete from S3 (best-effort)
    try:
        delete_s3_object(existing.file_url)
    except Exception:
        pass

    db.delete(existing)
    db.commit()
    return {"message": "Digital Prospectus deleted successfully."}


@router.get("/view", response_model=ProspectusResponse)
def view_prospectus(
    school_id: Optional[str] = Query(
        None,
        description="Required for public/admin access. School role does not need this.",
    ),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """
    Retrieve the Digital Prospectus for a school.

    **Access rules (single endpoint, no duplicates):**
    - School (authenticated, no token needed in Swagger): call without school_id.
    - Admin/SuperAdmin: pass ?school_id=.
    - Public (no token): pass ?school_id=.
    """
    target_school_id: Optional[str] = None

    if current_user is None:
        # Public access
        if not school_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="school_id query parameter is required for public access.",
            )
        target_school_id = school_id

    else:
        role = current_user.role
        if isinstance(role, str):
            try:
                role = UserRole(role)
            except ValueError:
                pass

        if role in (UserRole.ADMIN, UserRole.SUPERADMIN):
            if not school_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="school_id is required for admin access.",
                )
            target_school_id = school_id

        elif role == UserRole.SCHOOL:
            # Resolve from authenticated user — no param needed
            school = db.query(School).filter(School.user_id == current_user.id).first()
            if not school:
                raise HTTPException(status_code=404, detail="School not found.")
            target_school_id = school.id

        else:
            # Teacher / student / other roles — treated as public
            if not school_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="school_id query parameter is required.",
                )
            target_school_id = school_id

    # Verify school exists
    school_exists = db.query(School).filter(School.id == target_school_id).first()
    if not school_exists:
        raise HTTPException(status_code=404, detail="School not found.")

    prospectus: Optional[DigitalProspectus] = (
        db.query(DigitalProspectus)
        .filter(DigitalProspectus.school_id == target_school_id)
        .first()
    )
    if not prospectus:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No Digital Prospectus found for this school.",
        )
    return prospectus
