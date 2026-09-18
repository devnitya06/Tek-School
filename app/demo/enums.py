"""
Demo Management System — Enums
"""
from enum import Enum


class DemoDay(str, Enum):
    MONDAY = "MONDAY"
    TUESDAY = "TUESDAY"
    WEDNESDAY = "WEDNESDAY"
    THURSDAY = "THURSDAY"
    FRIDAY = "FRIDAY"
    SATURDAY = "SATURDAY"
    SUNDAY = "SUNDAY"


class DemoUserCategory(str, Enum):
    SCHOOL = "SCHOOL"
    TUITION = "TUITION"
    COLLEGE = "COLLEGE"
    INDIVIDUAL = "INDIVIDUAL"
    EDUCATOR = "EDUCATOR"
    OTHER = "OTHER"


class DemoStatus(str, Enum):
    PENDING = "PENDING"
    RESCHEDULED = "RESCHEDULED"
    ACCEPTED = "ACCEPTED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    NO_SHOW = "NO_SHOW"


# Statuses that block a new booking from the same email
ACTIVE_DEMO_STATUSES = {
    DemoStatus.PENDING,
    DemoStatus.RESCHEDULED,
    DemoStatus.ACCEPTED,
}

# Statuses from which rescheduling is allowed
RESCHEDULABLE_STATUSES = {
    DemoStatus.PENDING,
    DemoStatus.RESCHEDULED,
    DemoStatus.ACCEPTED,
}

# Terminal statuses — cannot be changed further
TERMINAL_STATUSES = {
    DemoStatus.COMPLETED,
    DemoStatus.CANCELLED,
    DemoStatus.NO_SHOW,
}

# Allowed status transitions: current_status -> set of allowed next statuses
ALLOWED_STATUS_TRANSITIONS: dict[DemoStatus, set[DemoStatus]] = {
    DemoStatus.PENDING: {
        DemoStatus.ACCEPTED,
        DemoStatus.CANCELLED,
        DemoStatus.RESCHEDULED,
    },
    DemoStatus.RESCHEDULED: {
        DemoStatus.ACCEPTED,
        DemoStatus.CANCELLED,
    },
    DemoStatus.ACCEPTED: {
        DemoStatus.COMPLETED,
        DemoStatus.NO_SHOW,
        DemoStatus.CANCELLED,
    },
    DemoStatus.COMPLETED: set(),
    DemoStatus.CANCELLED: set(),
    DemoStatus.NO_SHOW: set(),
}
