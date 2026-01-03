"""
Utility functions for payment calculations.
"""

from datetime import date
from app.models.students import InstallmentType


def calculate_installment_pending_amount(
    course_fee: float,
    course_fee_paid: float,
    transport_fee: float,
    transport_fee_paid: float,
    tek_school_fee: float,
    tek_school_fee_paid: float,
    installment_type: str | None,
    class_start_date: date | None,
    class_end_date: date | None
) -> float:
    """
    Calculate the installment pending amount based on installment type and class dates.
    
    Args:
        course_fee: Total course fee
        course_fee_paid: Amount paid for course fee
        transport_fee: Total transport fee
        transport_fee_paid: Amount paid for transport fee
        tek_school_fee: Total tek school fee
        tek_school_fee_paid: Amount paid for tek school fee
        installment_type: Installment type (monthly, quarterly, half_yearly, yearly)
        class_start_date: Class start date
        class_end_date: Class end date
    
    Returns:
        The installment pending amount (rounded to 2 decimal places)
    """
    # Calculate total fees and total paid
    total_fees = course_fee + transport_fee + tek_school_fee
    total_paid = course_fee_paid + transport_fee_paid + tek_school_fee_paid
    
    # If no class dates, return total remaining
    if not class_start_date or not class_end_date:
        return round(max(0.0, total_fees - total_paid), 2)
    
    today = date.today()
    installment_type_value = installment_type if installment_type else InstallmentType.YEARLY.value
    
    # Calculate per-period amount and periods passed based on installment type
    if installment_type_value == InstallmentType.MONTHLY.value:
        # Calculate total months in class period (inclusive)
        total_months = (class_end_date.year - class_start_date.year) * 12 + (class_end_date.month - class_start_date.month) + 1
        if total_months <= 0:
            total_months = 1
        
        # Calculate which month we're currently in (1-based, where month 1 is the start month)
        months_passed = (today.year - class_start_date.year) * 12 + (today.month - class_start_date.month) + 1
        if months_passed <= 0:
            months_passed = 1
        
        # Ensure we don't exceed total months
        if months_passed > total_months:
            months_passed = total_months
        
        # Per month amount
        per_period_amount = total_fees / total_months
        
        # Expected payment for periods passed (cumulative)
        expected_payment = per_period_amount * months_passed
        
        # Pending amount = expected payment - total paid (but not less than 0)
        installment_pending_amount = max(0.0, expected_payment - total_paid)
        
    elif installment_type_value == InstallmentType.QUARTERLY.value:
        # Calculate total quarters in class period
        start_quarter = (class_start_date.month - 1) // 3 + 1
        end_quarter = (class_end_date.month - 1) // 3 + 1
        today_quarter = (today.month - 1) // 3 + 1
        
        total_quarters = (class_end_date.year - class_start_date.year) * 4 + (end_quarter - start_quarter) + 1
        if total_quarters <= 0:
            total_quarters = 1
        
        # Calculate quarters passed
        if today.year == class_start_date.year:
            quarters_passed = today_quarter - start_quarter + 1
        else:
            quarters_passed = (today.year - class_start_date.year - 1) * 4 + (4 - start_quarter + 1) + today_quarter
        
        if quarters_passed <= 0:
            quarters_passed = 1
        
        # Per quarter amount
        per_period_amount = total_fees / total_quarters
        
        # Expected payment for quarters passed
        expected_payment = per_period_amount * quarters_passed
        
        # Pending amount
        installment_pending_amount = max(0.0, expected_payment - total_paid)
        
    elif installment_type_value == InstallmentType.HALF_YEARLY.value:
        # Calculate total half-years in class period
        start_half = 1 if class_start_date.month <= 6 else 2
        end_half = 1 if class_end_date.month <= 6 else 2
        today_half = 1 if today.month <= 6 else 2
        
        total_half_years = (class_end_date.year - class_start_date.year) * 2 + (end_half - start_half) + 1
        if total_half_years <= 0:
            total_half_years = 1
        
        # Calculate half-years passed
        if today.year == class_start_date.year:
            half_years_passed = today_half - start_half + 1
        else:
            half_years_passed = (today.year - class_start_date.year - 1) * 2 + (2 - start_half + 1) + today_half
        
        if half_years_passed <= 0:
            half_years_passed = 1
        
        # Per half-year amount
        per_period_amount = total_fees / total_half_years
        
        # Expected payment for half-years passed
        expected_payment = per_period_amount * half_years_passed
        
        # Pending amount
        installment_pending_amount = max(0.0, expected_payment - total_paid)
        
    elif installment_type_value == InstallmentType.YEARLY.value:
        # For yearly, if class hasn't ended, check if full year payment is due
        if today < class_end_date:
            # Expected payment is the full year amount
            expected_payment = total_fees
            installment_pending_amount = max(0.0, expected_payment - total_paid)
        else:
            # Class ended, no pending amount
            installment_pending_amount = 0.0
    else:
        # Default: use total remaining
        installment_pending_amount = max(0.0, total_fees - total_paid)
    
    return round(installment_pending_amount, 2)

