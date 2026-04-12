"""Helpers for staff employee compensation and designation-based templates."""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.staff import (
    DesignationCompensationTemplate,
    EmployeeCompensation,
    Staff,
)


def _num(v: Any) -> Optional[float]:
    if v is None:
        return None
    return float(v)


def staff_designation_for_display(staff: Staff) -> Optional[str]:
    """Prefer EmployeeCompensation.designation, then Staff.designation (trimmed)."""
    comp = getattr(staff, "compensation", None)
    if comp is not None and (comp.designation or "").strip():
        return str(comp.designation).strip()
    if staff.designation and str(staff.designation).strip():
        return str(staff.designation).strip()
    return None


def serialize_employee_compensation(ec: Optional[EmployeeCompensation]) -> Optional[dict[str, Any]]:
    if ec is None:
        return None
    return {
        "id": ec.id,
        "staff_id": ec.staff_id,
        "basic_salary": _num(ec.basic_salary),
        "hra": _num(ec.hra),
        "special_allowance": _num(ec.special_allowance),
        "travel_allowance": _num(ec.travel_allowance),
        "medical_allowance": _num(ec.medical_allowance),
        "employee_pf_contribution": _num(ec.employee_pf_contribution),
        "additional_benefits": bool(ec.additional_benefits),
        "extra_benefits": ec.extra_benefits,
        "designation": ec.designation,
        "employee_grade": ec.employee_grade,
        "max_salary": _num(ec.max_salary),
        "emergency_leave": ec.emergency_leave,
        "casual_leave": ec.casual_leave,
    }


def serialize_designation_template(t: DesignationCompensationTemplate) -> dict[str, Any]:
    return {
        "id": t.id,
        "school_id": t.school_id,
        "designation": t.designation,
        "basic_salary": _num(t.basic_salary),
        "hra": _num(t.hra),
        "special_allowance": _num(t.special_allowance),
        "travel_allowance": _num(t.travel_allowance),
        "medical_allowance": _num(t.medical_allowance),
        "employee_pf_contribution": _num(t.employee_pf_contribution),
        "additional_benefits": bool(t.additional_benefits),
        "extra_benefits": t.extra_benefits,
        "employee_grade": t.employee_grade,
        "max_salary": _num(t.max_salary),
        "emergency_leave": t.emergency_leave,
        "casual_leave": t.casual_leave,
    }


def _apply_template_fields(ec: EmployeeCompensation, template: DesignationCompensationTemplate) -> None:
    """Copy pay/benefits from template. Caller must set ec.designation before calling."""
    ec.basic_salary = template.basic_salary
    ec.hra = template.hra
    ec.special_allowance = template.special_allowance
    ec.travel_allowance = template.travel_allowance
    ec.medical_allowance = template.medical_allowance
    ec.employee_pf_contribution = template.employee_pf_contribution
    ec.additional_benefits = template.additional_benefits
    ec.extra_benefits = template.extra_benefits
    ec.employee_grade = template.employee_grade
    ec.max_salary = template.max_salary
    ec.emergency_leave = template.emergency_leave
    ec.casual_leave = template.casual_leave


def sync_employee_compensation_from_designation_template(db: Session, staff: Staff) -> Optional[EmployeeCompensation]:
    """
    Align Staff.designation with EmployeeCompensation and optional school template.

    Canonical key: non-empty Staff.designation (e.g. create / profile update) wins; otherwise use
    EmployeeCompensation.designation so designation can be owned by compensation when the staff row
    is empty. When a key exists, both Staff and EmployeeCompensation get that designation after strip.

    If the school has a DesignationCompensationTemplate matching the key, copy pay/benefit fields.
    """
    ec = db.query(EmployeeCompensation).filter(EmployeeCompensation.staff_id == staff.id).first()
    key_staff = (staff.designation or "").strip()
    key_comp = (ec.designation or "").strip() if ec else ""
    key = key_staff if key_staff else key_comp

    if not key:
        staff.designation = None
        if ec is not None:
            ec.designation = None
        return ec

    if ec is None:
        ec = EmployeeCompensation(staff_id=staff.id)
        db.add(ec)

    ec.designation = key

    template = None
    if staff.school_id:
        template = (
            db.query(DesignationCompensationTemplate)
            .filter(
                DesignationCompensationTemplate.school_id == staff.school_id,
                DesignationCompensationTemplate.designation == key,
            )
            .first()
        )
    if template is not None:
        _apply_template_fields(ec, template)
        # Keep Staff profile leave fields aligned with designation benefits when the school defined them.
        if template.emergency_leave is not None:
            staff.emergency_leave = template.emergency_leave
        if template.casual_leave is not None:
            staff.casual_leave = template.casual_leave

    staff.designation = key
    return ec
