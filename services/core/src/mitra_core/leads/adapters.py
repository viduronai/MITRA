"""Turn each source's payload into one :class:`LeadInput` (pure functions, no I/O).

The generic shape (intake API, Sheets/Forms Apps Script, website form, Zapier/Make/Pabbly/n8n)
is forgiving on purpose: column names such as ``Phone Number`` or ``Mobile No.`` are recognised,
and every other column becomes a call variable (``{city}``, ``{budget}``) for the employee.
The phone number itself is never kept in ``fields``.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from mitra_core.leads.enums import LeadSourceKind
from mitra_core.leads.phone import normalize_indian_mobile

MAX_FIELDS = 30
MAX_KEY = 40
MAX_VALUE = 500

# Sources a generic payload may claim with ``"source": ...`` (portals have their own endpoints).
GENERIC_KINDS = frozenset(
    {
        LeadSourceKind.API,
        LeadSourceKind.GOOGLE_SHEETS,
        LeadSourceKind.GOOGLE_FORMS,
        LeadSourceKind.ZAPIER,
    }
)
PHONE_KEYS = (
    "phone",
    "phone_number",
    "mobile",
    "mobile_number",
    "mobile_no",
    "phone_no",
    "contact_number",
    "contact_no",
    "whatsapp",
    "whatsapp_number",
    "number",
    "sender_mobile",
)
NAME_KEYS = ("name", "full_name", "your_name", "customer_name", "sender_name")
_RESERVED = frozenset(
    {"source", "source_detail", "external_id", "consent", "consent_text", "fields", "first_name"}
    | {"consent_version", "consent_lang"}
    | {"last_name", "website", "secret", "key", "google_key"}
)
_KEY_CLEAN = re.compile(r"[^a-z0-9]+")


class AdapterError(ValueError):
    """The payload cannot become a lead (shown to the sender as a 422)."""


@dataclass(slots=True)
class LeadInput:
    phone_e164: str
    source: LeadSourceKind
    name: str | None = None
    fields: dict[str, str] = field(default_factory=dict)
    source_detail: str | None = None
    external_id: str | None = None
    consent: bool | None = None  # None: implied by the enquiry itself (lead form)
    consent_text: str | None = None
    consent_version: str | None = None  # Mitra-controlled forms: which checkbox text
    consent_lang: str | None = None


def field_key(raw: object) -> str:
    """``"Mobile No."`` -> ``"mobile_no"``."""
    return _KEY_CLEAN.sub("_", str(raw).strip().lower()).strip("_")[:MAX_KEY]


def _text(value: object, limit: int = MAX_VALUE) -> str | None:
    if value is None or isinstance(value, dict | list):
        return None
    out = str(value).strip()
    return out[:limit] or None


def _clean_fields(items: Iterable[tuple[str, object]]) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw_key, value in items:
        key = field_key(raw_key)
        val = _text(value)
        if not key or val is None or key in PHONE_KEYS or key in _RESERVED or key in NAME_KEYS:
            continue
        if len(out) >= MAX_FIELDS:
            break
        out.setdefault(key, val)
    return out


def consent_value(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        low = value.strip().lower()
        if low in {"true", "yes", "on", "1", "agreed", "y"}:
            return True
        if low in {"false", "no", "off", "0", "n"}:
            return False
    return None


def _explicit_consent(values: Mapping[str, object]) -> bool | None:
    """A portal form's own consent question, if it has one: any refusal wins."""
    answers = [consent_value(v) for k, v in values.items() if "consent" in k]
    if any(a is False for a in answers):
        return False
    return True if any(answers) else None


def _require_phone(raw: object) -> str:
    phone = normalize_indian_mobile(raw)
    if phone is None:
        raise AdapterError("A valid Indian mobile number is required")
    return phone


def parse_generic(body: Mapping[str, Any], default: LeadSourceKind) -> LeadInput:
    flat = {field_key(k): v for k, v in body.items()}
    nested = body.get("fields")
    extra = list(nested.items()) if isinstance(nested, Mapping) else []
    phone_raw = next((flat[k] for k in PHONE_KEYS if flat.get(k) not in (None, "")), None)
    if phone_raw is None:
        phone_raw = next(
            (v for k, v in extra if field_key(k) in PHONE_KEYS and v not in (None, "")), None
        )
    name = next((_text(flat[k], 120) for k in NAME_KEYS if _text(flat.get(k))), None)
    if name is None and (flat.get("first_name") or flat.get("last_name")):
        name = _text(f"{flat.get('first_name') or ''} {flat.get('last_name') or ''}", 120)
    source = default
    claimed = flat.get("source")
    if default == LeadSourceKind.API and isinstance(claimed, str):
        try:
            kind = LeadSourceKind(claimed.strip().lower())
        except ValueError:
            kind = None
        if kind in GENERIC_KINDS:
            source = kind
    return LeadInput(
        phone_e164=_require_phone(phone_raw),
        source=source,
        name=name,
        fields=_clean_fields([*body.items(), *extra]),
        source_detail=_text(flat.get("source_detail"), 120),
        external_id=_text(flat.get("external_id"), 80),
        consent=consent_value(flat.get("consent")),
        consent_text=_text(flat.get("consent_text"), 150),
        consent_version=_text(flat.get("consent_version"), 20),
        consent_lang=_text(flat.get("consent_lang"), 5),
    )


# ---- Google Ads lead form webhook ----------------------------------------------------------------


def parse_google_ads(body: Mapping[str, Any]) -> LeadInput:
    columns = body.get("user_column_data")
    if not isinstance(columns, list):
        raise AdapterError("user_column_data is missing")
    values: dict[str, str] = {}
    for col in columns:
        if isinstance(col, Mapping):
            key = field_key(col.get("column_id") or col.get("column_name") or "")
            val = _text(col.get("string_value"))
            if key and val:
                values[key] = val
    name = values.get("full_name") or _text(
        f"{values.get('first_name', '')} {values.get('last_name', '')}", 120
    )
    campaign = _text(body.get("campaign_id"), 60)
    consent = _explicit_consent(values)
    fields = _clean_fields((k, v) for k, v in values.items() if "consent" not in k)
    if body.get("is_test"):
        fields["is_test"] = "true"
    return LeadInput(
        phone_e164=_require_phone(values.get("phone_number")),
        source=LeadSourceKind.GOOGLE_ADS,
        name=_text(name, 120),
        fields=fields,
        source_detail=f"Google Ads campaign {campaign}" if campaign else None,
        external_id=_text(body.get("lead_id"), 80),
        consent=consent,
    )


# ---- IndiaMART (push webhook and pull API share the record shape) --------------------------------

_INDIAMART_FIELDS = {
    "SENDER_EMAIL": "email",
    "SENDER_COMPANY": "company",
    "SENDER_CITY": "city",
    "SENDER_STATE": "state",
    "SUBJECT": "subject",
    "QUERY_PRODUCT_NAME": "product",
    "QUERY_MESSAGE": "message",
    "QUERY_TYPE": "query_type",
}


def parse_indiamart_record(rec: Mapping[str, Any]) -> LeadInput:
    fields = _clean_fields((name, rec.get(key)) for key, name in _INDIAMART_FIELDS.items())
    phone = normalize_indian_mobile(rec.get("SENDER_MOBILE")) or normalize_indian_mobile(
        rec.get("SENDER_MOBILE_ALT")
    )
    product = _text(rec.get("QUERY_PRODUCT_NAME"), 100)
    return LeadInput(
        phone_e164=_require_phone(phone),
        source=LeadSourceKind.INDIAMART,
        name=_text(rec.get("SENDER_NAME"), 120),
        fields=fields,
        source_detail=f"IndiaMART: {product}" if product else "IndiaMART",
        external_id=_text(rec.get("UNIQUE_QUERY_ID"), 80),
        consent=_explicit_consent({field_key(k): v for k, v in rec.items()}),
    )


def parse_indiamart_push(body: Mapping[str, Any]) -> LeadInput:
    rec = body.get("RESPONSE")
    if not isinstance(rec, Mapping):
        raise AdapterError("RESPONSE is missing")
    return parse_indiamart_record(rec)


# ---- JustDial (push, form fields or JSON) --------------------------------------------------------

_JUSTDIAL_FIELDS = ("email", "category", "city", "area", "brancharea", "company", "pincode")


def parse_justdial(body: Mapping[str, Any]) -> LeadInput:
    flat = {field_key(k): v for k, v in body.items()}
    phone = normalize_indian_mobile(flat.get("mobile")) or normalize_indian_mobile(
        flat.get("phone")
    )
    category = _text(flat.get("category"), 100)
    return LeadInput(
        phone_e164=_require_phone(phone),
        source=LeadSourceKind.JUSTDIAL,
        name=_text(flat.get("name"), 120),
        fields=_clean_fields((k, flat.get(k)) for k in _JUSTDIAL_FIELDS),
        source_detail=f"JustDial: {category}" if category else "JustDial",
        external_id=_text(flat.get("leadid"), 80),
        consent=_explicit_consent(flat),
    )


# ---- Meta Lead Ads (the lead object fetched from the Graph API) ----------------------------------


def parse_meta_lead(lead: Mapping[str, Any]) -> LeadInput:
    values: dict[str, str] = {}
    for item in lead.get("field_data") or []:
        if isinstance(item, Mapping) and item.get("name"):
            vals = item.get("values") or []
            if vals:
                values[field_key(item["name"])] = str(vals[0])
    name = values.get("full_name") or _text(
        f"{values.get('first_name', '')} {values.get('last_name', '')}", 120
    )
    phone = next((values[k] for k in PHONE_KEYS if values.get(k)), None)
    # Meta forms always show the advertiser's privacy policy; custom consent boxes are optional.
    boxes = [b for b in lead.get("custom_disclaimer_responses") or [] if isinstance(b, Mapping)]
    consent = None if not boxes else all(consent_value(b.get("is_checked")) for b in boxes)
    campaign = _text(lead.get("campaign_name") or lead.get("ad_name"), 100)
    return LeadInput(
        phone_e164=_require_phone(phone),
        source=LeadSourceKind.META,
        name=_text(name, 120),
        fields=_clean_fields(values.items()),
        source_detail=campaign,
        external_id=_text(lead.get("id"), 80),
        consent=consent,
    )
