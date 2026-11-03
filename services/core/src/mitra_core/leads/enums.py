"""Lead intake enums (stored as text with CHECK constraints, migration 0005_leads)."""

from __future__ import annotations

from enum import StrEnum


class LeadSourceKind(StrEnum):
    """Where a lead came from; kept on every lead for source ROI reports (REP-04)."""

    API = "api"  # INT-12 generic intake API (custom code, CRMs)
    WEBSITE_FORM = "website_form"  # INT-02 copy-paste form snippet
    GOOGLE_SHEETS = "google_sheets"  # INT-03 Apps Script on a Sheet
    GOOGLE_FORMS = "google_forms"  # INT-14 Apps Script on a Form
    META = "meta"  # INT-01 Facebook / Instagram Lead Ads
    GOOGLE_ADS = "google_ads"  # INT-14 Google Ads lead form webhook
    INDIAMART = "indiamart"  # INT-14 push or pull
    JUSTDIAL = "justdial"  # INT-14 push
    ZAPIER = "zapier"  # INT-06 Zapier / Make / Pabbly / n8n (generic webhook)


class LeadStatus(StrEnum):
    QUEUED = "queued"  # call queued, dialled as soon as the dialer picks it up
    SCHEDULED = "scheduled"  # outside calling hours: queued for the next allowed window
    DUPLICATE = "duplicate"  # same phone within the dedupe window: no second call
    NOT_CALLED = "not_called"  # auto-call is off for this source
    BLOCKED = "blocked"  # compliance gate refused (opt-out, no caller id, wallet...)
    NO_CONSENT = "no_consent"  # the form said consent was NOT given (or no checkbox)
    NO_ATTESTATION = "no_attestation"  # generic source the owner has not vouched for
    NO_EMPLOYEE = "no_employee"  # nobody to make the call
    FAILED = "failed"  # the dialer refused the job
