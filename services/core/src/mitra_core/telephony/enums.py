"""Telephony and compliance enums (Postgres native enums + API schemas).

Kept apart from ``models/enums.py`` so the telephony area can evolve on its own branch.
"""

from __future__ import annotations

from enum import StrEnum


class NumberType(StrEnum):
    """Number options from 08-COMPLIANCE-SECURITY section 8.2 (plus the 140 promotional series)."""

    LOCAL = "local"  # city-code landline (040 Hyderabad, 0866 Vijayawada)
    MOBILE_VIRTUAL = "mobile_virtual"  # 10-digit mobile-series virtual number
    BYO_SIP = "byo_sip"  # the business's own landline/PRI/SIP number
    SERIES_1600 = "1600"  # BFSI / government service calls
    SERIES_1601 = "1601"  # other mandated sectors (phased, TRAI 10 Aug 2026)
    SERIES_140 = "140"  # promotional, registered telemarketer only


class Carrier(StrEnum):
    EXOTEL = "exotel"
    PLIVO = "plivo"
    SIP = "sip"  # bring-your-own trunk
    SIM = "sim"  # local carrier simulator (dev / tests); never dials anyone


class KycStatus(StrEnum):
    PENDING_KYC = "pending_kyc"  # requested, waiting for the owner's documents
    SUBMITTED = "submitted"  # documents sent to the carrier
    APPROVED = "approved"  # number live
    REJECTED = "rejected"


class VerificationStatus(StrEnum):
    """Truecaller Verified Business (NUM-04) and CNAP name registration (NUM-06)."""

    NOT_STARTED = "not_started"
    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"


class NumberHealth(StrEnum):
    HEALTHY = "healthy"
    WATCH = "watch"
    PAUSED = "paused"


class CallPurpose(StrEnum):
    """Outbound purpose (WORKFLOWS section 11b); decides consent, hours and caller ID."""

    CALLBACK = "callback"  # missed-call rescue: the customer called us first
    SERVICE = "service"  # consenting customer: lead follow-up, reminder, payment due
    MANDATED_SERVICE = "mandated_service"  # sector mandated onto 1600/1601
    PROMOTIONAL = "promotional"  # no prior relationship: 140 series only, off by default


class ConsentScope(StrEnum):
    """What a consent record covers. Every non-promotional purpose needs ``service``."""

    SERVICE = "service"
    PROMOTIONAL = "promotional"


class ConsentSource(StrEnum):
    LEAD_FORM = "lead_form"
    EXISTING_CUSTOMER = "existing_customer"
    EXPLICIT_OPT_IN = "explicit_opt_in"
    INBOUND_CALL = "inbound_call"


class OptOutSource(StrEnum):
    VOICE = "voice"  # "don't call me" during a call (CMP-06)
    WHATSAPP = "whatsapp"
    OWNER = "owner"


class AttemptOutcome(StrEnum):
    ANSWERED = "answered"
    NO_ANSWER = "no_answer"
    BUSY = "busy"
    VOICEMAIL = "voicemail"
    FAILED = "failed"


class Decision(StrEnum):
    ALLOW = "allow"
    BLOCK = "block"
    DEFER = "defer"  # allowed later (calling hours, frequency cap)


class DndStatus(StrEnum):
    REGISTERED = "registered"
    NOT_REGISTERED = "not_registered"
    UNKNOWN = "unknown"  # provider down: promotional calls fail closed
