from typing import Annotated, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BeforeValidator
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.core.dependencies import get_current_user_optional
from app.db.session import get_db
from app.models.placement import PlacementAchiever, PlacementPartner, PlacementStatus
from app.models.school import School
from app.models.users import User
from app.schemas.placement import (
    PlacementAchieverListItem,
    PlacementAchieverResponse,
    PlacementPartnerListItem,
    PlacementPartnerResponse,
)
from app.schemas.users import UserRole
from app.services.pagination import PaginationParams
from app.utils.permission import require_roles
from app.utils.s3 import upload_multipart_file_to_s3

router = APIRouter(prefix="/placement")
public_router = APIRouter(prefix="/public")
MAX_FILE_SIZE = 1024 * 1024
ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png"}


def _parse_campus_month(value: object) -> object:
    if value in (None, ""):
        return None
    month = int(value)
    if not 1 <= month <= 12:
        raise ValueError("campus_month must be a month between 1 and 12")
    return month


CampusMonth = Annotated[
    Optional[int],
    BeforeValidator(_parse_campus_month),
]


def _validate_and_upload(upload: Optional[UploadFile], school_id: str, folder: str) -> Optional[str]:
    if not upload or not upload.filename:
        return None
    extension = upload.filename.rsplit(".", 1)[-1].lower() if "." in upload.filename else ""
    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Only JPG and PNG files are allowed.")
    try:
        return upload_multipart_file_to_s3(upload, f"schools/{school_id}/placement/{folder}", MAX_FILE_SIZE)
    except ValueError as exc:
        raise HTTPException(status_code=413 if "size" in str(exc).lower() else 400, detail=str(exc))


def _school_for_user(db: Session, current_user: User, school_id: Optional[str] = None) -> School:
    if current_user.role in (UserRole.ADMIN, UserRole.SUPERADMIN):
        if not school_id:
            raise HTTPException(status_code=400, detail="school_id is required for admin access.")
        school = db.query(School).filter(School.id == school_id).first()
    else:
        school = db.query(School).filter(School.user_id == current_user.id).first()
    if not school:
        raise HTTPException(status_code=404, detail="School not found.")
    if school.institution_class == "school_education":
        raise HTTPException(status_code=403, detail="Placement module is not available for this institution.")
    return school


def _public_school(db: Session, school_id: str) -> School:
    school = db.query(School).filter(School.id == school_id).first()
    if not school:
        raise HTTPException(status_code=404, detail="School not found.")
    if school.institution_class == "school_education":
        raise HTTPException(status_code=404, detail="Placement records not found.")
    return school


def _partner_response(partner: PlacementPartner, count: int) -> dict:
    data = {column.name: getattr(partner, column.name) for column in PlacementPartner.__table__.columns}
    data["no_of_placement"] = count
    return data


def _achiever_response(achiever: PlacementAchiever) -> dict:
    data = {column.name: getattr(achiever, column.name) for column in PlacementAchiever.__table__.columns}
    data["company_name"] = achiever.company.company_name
    return data


@router.post("/partners", response_model=PlacementPartnerResponse, status_code=status.HTTP_201_CREATED)
def create_partner(
    company_name: str = Form(...), website: str = Form(...), placement_year: int = Form(...),
    campus_month: CampusMonth = Form(None), about_company: Optional[str] = Form(None),
    hiring_criteria: Optional[str] = Form(None), what_they_give: Optional[str] = Form(None),
    status_value: PlacementStatus = Form(PlacementStatus.ACTIVE),
    company_logo: Optional[UploadFile] = File(None), school_id: Optional[str] = Query(None),
    current_user: User = Depends(require_roles(UserRole.SCHOOL, UserRole.ADMIN, UserRole.SUPERADMIN)),
    db: Session = Depends(get_db),
):
    school = _school_for_user(db, current_user, school_id)
    partner = PlacementPartner(school_id=school.id, company_name=company_name.strip(), website=website.strip(),
        placement_year=placement_year, campus_month=campus_month, about_company=about_company,
        hiring_criteria=hiring_criteria, what_they_give=what_they_give, status=status_value.value,
        company_logo=_validate_and_upload(company_logo, school.id, "partner"))
    db.add(partner)
    db.commit()
    db.refresh(partner)
    return _partner_response(partner, 0)


@router.get("/partners", response_model=dict)
def list_partners(
    pagination: PaginationParams = Depends(), company_name: Optional[str] = Query(None),
    placement_year: Optional[int] = Query(None), school_id: Optional[str] = Query(None),
    current_user: User = Depends(require_roles(UserRole.SCHOOL, UserRole.ADMIN, UserRole.SUPERADMIN)),
    db: Session = Depends(get_db),
):
    school = _school_for_user(db, current_user, school_id)
    query = db.query(PlacementPartner).filter(PlacementPartner.school_id == school.id)
    if company_name:
        query = query.filter(PlacementPartner.company_name.ilike(f"%{company_name}%"))
    if placement_year is not None:
        query = query.filter(PlacementPartner.placement_year == placement_year)
    total = query.count()
    partners = query.order_by(PlacementPartner.created_at.desc()).offset(pagination.offset()).limit(pagination.limit()).all()
    items = []
    for partner in partners:
        count = db.query(func.count(PlacementAchiever.id)).filter(PlacementAchiever.company_id == partner.id, PlacementAchiever.placement_year == partner.placement_year).scalar() or 0
        items.append(PlacementPartnerListItem.model_validate(_partner_response(partner, count)))
    return pagination.format_response(items, total)


@router.get("/partners/{partner_id}", response_model=PlacementPartnerResponse)
def get_partner(partner_id: int, school_id: Optional[str] = Query(None), current_user: User = Depends(require_roles(UserRole.SCHOOL, UserRole.ADMIN, UserRole.SUPERADMIN)), db: Session = Depends(get_db)):
    school = _school_for_user(db, current_user, school_id)
    partner = db.query(PlacementPartner).filter(PlacementPartner.id == partner_id, PlacementPartner.school_id == school.id).first()
    if not partner:
        raise HTTPException(status_code=404, detail="Placement partner not found.")
    count = db.query(func.count(PlacementAchiever.id)).filter(PlacementAchiever.company_id == partner.id, PlacementAchiever.placement_year == partner.placement_year).scalar() or 0
    return _partner_response(partner, count)


@router.patch("/partners/{partner_id}", response_model=PlacementPartnerResponse)
def update_partner(partner_id: int, company_name: Optional[str] = Form(None), website: Optional[str] = Form(None), placement_year: Optional[int] = Form(None), campus_month: CampusMonth = Form(None), about_company: Optional[str] = Form(None), hiring_criteria: Optional[str] = Form(None), what_they_give: Optional[str] = Form(None), status_value: Optional[PlacementStatus] = Form(None), company_logo: Optional[UploadFile] = File(None), school_id: Optional[str] = Query(None), current_user: User = Depends(require_roles(UserRole.SCHOOL, UserRole.ADMIN, UserRole.SUPERADMIN)), db: Session = Depends(get_db)):
    school = _school_for_user(db, current_user, school_id)
    partner = db.query(PlacementPartner).filter(PlacementPartner.id == partner_id, PlacementPartner.school_id == school.id).first()
    if not partner:
        raise HTTPException(status_code=404, detail="Placement partner not found.")
    for field, value in (("company_name", company_name), ("website", website), ("placement_year", placement_year), ("campus_month", campus_month), ("about_company", about_company), ("hiring_criteria", hiring_criteria), ("what_they_give", what_they_give)):
        if value is not None:
            setattr(partner, field, value.strip() if isinstance(value, str) else value)
    if status_value is not None:
        partner.status = status_value.value
    uploaded = _validate_and_upload(company_logo, school.id, "partner")
    if uploaded:
        partner.company_logo = uploaded
    db.commit()
    db.refresh(partner)
    count = db.query(func.count(PlacementAchiever.id)).filter(PlacementAchiever.company_id == partner.id, PlacementAchiever.placement_year == partner.placement_year).scalar() or 0
    return _partner_response(partner, count)


@router.delete("/partners/{partner_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_partner(partner_id: int, school_id: Optional[str] = Query(None), current_user: User = Depends(require_roles(UserRole.SCHOOL, UserRole.ADMIN, UserRole.SUPERADMIN)), db: Session = Depends(get_db)):
    school = _school_for_user(db, current_user, school_id)
    partner = db.query(PlacementPartner).filter(PlacementPartner.id == partner_id, PlacementPartner.school_id == school.id).first()
    if not partner:
        raise HTTPException(status_code=404, detail="Placement partner not found.")
    db.delete(partner)
    db.commit()


def _create_achiever(*, company_id: int, school: School, db: Session) -> PlacementPartner:
    partner = db.query(PlacementPartner).filter(PlacementPartner.id == company_id, PlacementPartner.school_id == school.id).first()
    if not partner:
        raise HTTPException(status_code=400, detail="Selected company does not belong to this school.")
    return partner


@router.post("/achievers", response_model=PlacementAchieverResponse, status_code=status.HTTP_201_CREATED)
def create_achiever(
    student_name: str = Form(...), gender: str = Form(...), class_name: str = Form(...), company_id: int = Form(...), company_name: str = Form(...), designation: str = Form(...), salary_package_lpa: str = Form(...), placement_year: int = Form(...), section_roll_no: Optional[str] = Form(None), about_student: Optional[str] = Form(None), status_value: PlacementStatus = Form(PlacementStatus.ACTIVE), student_logo: Optional[UploadFile] = File(None), file: Optional[UploadFile] = File(None), school_id: Optional[str] = Query(None), current_user: User = Depends(require_roles(UserRole.SCHOOL, UserRole.ADMIN, UserRole.SUPERADMIN)), db: Session = Depends(get_db)):
    school = _school_for_user(db, current_user, school_id)
    partner = _create_achiever(company_id=company_id, school=school, db=db)
    if company_name.strip().casefold() != partner.company_name.strip().casefold():
        raise HTTPException(status_code=400, detail="company_name does not match the selected company.")
    achiever = PlacementAchiever(school_id=school.id, student_name=student_name.strip(), gender=gender.strip(), class_name=class_name.strip(), section_roll_no=section_roll_no, company_id=partner.id, designation=designation.strip(), salary_package_lpa=salary_package_lpa, placement_year=placement_year, about_student=about_student, status=status_value.value, student_logo=_validate_and_upload(student_logo, school.id, "achiever"), file=_validate_and_upload(file, school.id, "achiever-files"))
    db.add(achiever)
    db.commit()
    db.refresh(achiever)
    return _achiever_response(achiever)


def _achiever_query(db: Session, school: School):
    return db.query(PlacementAchiever).options(joinedload(PlacementAchiever.company)).filter(PlacementAchiever.school_id == school.id)


@router.get("/achievers", response_model=dict)
def list_achievers(pagination: PaginationParams = Depends(), student_name: Optional[str] = Query(None), class_name: Optional[str] = Query(None), company_name: Optional[str] = Query(None), placement_year: Optional[int] = Query(None), school_id: Optional[str] = Query(None), current_user: User = Depends(require_roles(UserRole.SCHOOL, UserRole.ADMIN, UserRole.SUPERADMIN)), db: Session = Depends(get_db)):
    school = _school_for_user(db, current_user, school_id)
    query = _achiever_query(db, school)
    if student_name: query = query.filter(PlacementAchiever.student_name.ilike(f"%{student_name}%"))
    if class_name: query = query.filter(PlacementAchiever.class_name.ilike(f"%{class_name}%"))
    if company_name: query = query.join(PlacementPartner).filter(PlacementPartner.company_name.ilike(f"%{company_name}%"))
    if placement_year is not None: query = query.filter(PlacementAchiever.placement_year == placement_year)
    total = query.count()
    items = [_achiever_response(item) for item in query.order_by(PlacementAchiever.created_at.desc()).offset(pagination.offset()).limit(pagination.limit()).all()]
    return pagination.format_response([PlacementAchieverListItem(**{key: item[key] for key in ("id", "student_name", "class_name", "company_name", "placement_year", "salary_package_lpa", "created_at", "status")}) for item in items], total)


@router.get("/achievers/{achiever_id}", response_model=PlacementAchieverResponse)
def get_achiever(achiever_id: int, school_id: Optional[str] = Query(None), current_user: User = Depends(require_roles(UserRole.SCHOOL, UserRole.ADMIN, UserRole.SUPERADMIN)), db: Session = Depends(get_db)):
    school = _school_for_user(db, current_user, school_id)
    item = _achiever_query(db, school).filter(PlacementAchiever.id == achiever_id).first()
    if not item: raise HTTPException(status_code=404, detail="Placement achiever not found.")
    return _achiever_response(item)


@router.patch("/achievers/{achiever_id}", response_model=PlacementAchieverResponse)
def update_achiever(achiever_id: int, student_name: Optional[str] = Form(None), gender: Optional[str] = Form(None), class_name: Optional[str] = Form(None), company_id: Optional[int] = Form(None), designation: Optional[str] = Form(None), salary_package_lpa: Optional[str] = Form(None), placement_year: Optional[int] = Form(None), section_roll_no: Optional[str] = Form(None), about_student: Optional[str] = Form(None), status_value: Optional[PlacementStatus] = Form(None), student_logo: Optional[UploadFile] = File(None), file: Optional[UploadFile] = File(None), school_id: Optional[str] = Query(None), current_user: User = Depends(require_roles(UserRole.SCHOOL, UserRole.ADMIN, UserRole.SUPERADMIN)), db: Session = Depends(get_db)):
    school = _school_for_user(db, current_user, school_id)
    item = _achiever_query(db, school).filter(PlacementAchiever.id == achiever_id).first()
    if not item: raise HTTPException(status_code=404, detail="Placement achiever not found.")
    if company_id is not None: item.company_id = _create_achiever(company_id=company_id, school=school, db=db).id
    for field, value in (("student_name", student_name), ("gender", gender), ("class_name", class_name), ("designation", designation), ("salary_package_lpa", salary_package_lpa), ("placement_year", placement_year), ("section_roll_no", section_roll_no), ("about_student", about_student)):
        if value is not None: setattr(item, field, value.strip() if isinstance(value, str) else value)
    if status_value is not None: item.status = status_value.value
    student_logo_url = _validate_and_upload(student_logo, school.id, "achiever")
    file_url = _validate_and_upload(file, school.id, "achiever-files")
    if student_logo_url: item.student_logo = student_logo_url
    if file_url: item.file = file_url
    db.commit()
    db.refresh(item)
    return _achiever_response(item)


@router.delete("/achievers/{achiever_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_achiever(achiever_id: int, school_id: Optional[str] = Query(None), current_user: User = Depends(require_roles(UserRole.SCHOOL, UserRole.ADMIN, UserRole.SUPERADMIN)), db: Session = Depends(get_db)):
    school = _school_for_user(db, current_user, school_id)
    item = _achiever_query(db, school).filter(PlacementAchiever.id == achiever_id).first()
    if not item: raise HTTPException(status_code=404, detail="Placement achiever not found.")
    db.delete(item)
    db.commit()


@public_router.get("/schools/{school_id}/placement-achievers", response_model=dict)
def public_achievers(school_id: str, pagination: PaginationParams = Depends(), db: Session = Depends(get_db)):
    school = _public_school(db, school_id)
    query = _achiever_query(db, school).filter(PlacementAchiever.status == PlacementStatus.ACTIVE.value)
    total = query.count()
    items = [_achiever_response(item) for item in query.order_by(PlacementAchiever.created_at.desc()).offset(pagination.offset()).limit(pagination.limit()).all()]
    return pagination.format_response(items, total)


@public_router.get("/schools/{school_id}/placement-partners", response_model=dict)
def public_partners(school_id: str, pagination: PaginationParams = Depends(), db: Session = Depends(get_db)):
    school = _public_school(db, school_id)
    query = db.query(PlacementPartner).filter(PlacementPartner.school_id == school.id, PlacementPartner.status == PlacementStatus.ACTIVE.value)
    total = query.count()
    items = []
    for partner in query.order_by(PlacementPartner.created_at.desc()).offset(pagination.offset()).limit(pagination.limit()).all():
        count = db.query(func.count(PlacementAchiever.id)).filter(PlacementAchiever.company_id == partner.id, PlacementAchiever.placement_year == partner.placement_year, PlacementAchiever.status == PlacementStatus.ACTIVE.value).scalar() or 0
        items.append(_partner_response(partner, count))
    return pagination.format_response(items, total)