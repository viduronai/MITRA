"""Domain enums shared by ORM models (Postgres native enums) and API schemas."""

from __future__ import annotations

from enum import StrEnum


class Industry(StrEnum):
    CLINIC = "clinic"
    REAL_ESTATE = "real_estate"
    EDUCATION = "education"
    OTHER = "other"


class Locale(StrEnum):
    EN = "en"
    TE = "te"
    HI = "hi"


class MemberRole(StrEnum):
    OWNER = "owner"
    MANAGER = "manager"
    STAFF = "staff"
    AGENCY_ADMIN = "agency_admin"


class RoleTemplate(StrEnum):
    RECEPTIONIST = "receptionist"
    LEAD_CALLER = "lead_caller"
    REMINDER_CALLER = "reminder_caller"
    PAYMENT_CALLER = "payment_caller"


class VoiceTier(StrEnum):
    SMART = "smart"
    NATURAL = "natural"
    SIGNATURE = "signature"


class EmployeeStatus(StrEnum):
    WORKING = "working"
    PAUSED = "paused"
    TRAINING = "training"


class KnowledgeSourceType(StrEnum):
    URL = "url"
    TEXT = "text"


class KnowledgeSourceStatus(StrEnum):
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class FactCategory(StrEnum):
    SERVICES = "services"
    PRICES = "prices"
    TIMINGS = "timings"
    LOCATION = "location"
    CONTACT = "contact"
    FAQ = "faq"
    POLICY = "policy"


class FactStatus(StrEnum):
    SUGGESTED = "suggested"
    CONFIRMED = "confirmed"


class TestCallStatus(StrEnum):
    """Not stored: derived from the call's age while calls are simulated."""

    __test__ = False

    QUEUED = "queued"
    RINGING = "ringing"
    CONNECTED = "connected"
    COMPLETED = "completed"
