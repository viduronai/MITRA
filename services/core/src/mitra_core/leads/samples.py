"""Sample payloads for "Send a test lead": each one runs through the real adapter for its
source, so the owner sees exactly what a real lead from that portal turns into. The phone is the
owner's own, so the instant call (when a number is live) rings the owner, not a stranger."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from mitra_core.leads import adapters
from mitra_core.leads.adapters import LeadInput
from mitra_core.leads.enums import LeadSourceKind


def _generic(kind: LeadSourceKind) -> Callable[[str], LeadInput]:
    def build(phone: str) -> LeadInput:
        data = adapters.parse_generic(
            {"name": "Test Lead", "phone": phone, "city": "Hyderabad", "interest": "Enquiry"},
            LeadSourceKind.API,
        )
        data.source = kind
        data.source_detail = "Test lead from Mitra"
        return data

    return build


def _google_ads(phone: str) -> LeadInput:
    body: dict[str, Any] = {
        "lead_id": None,
        "campaign_id": "test",
        "is_test": True,
        "user_column_data": [
            {"column_id": "FULL_NAME", "string_value": "Test Lead"},
            {"column_id": "PHONE_NUMBER", "string_value": phone},
            {"column_id": "CITY", "string_value": "Hyderabad"},
        ],
    }
    return adapters.parse_google_ads(body)


def _indiamart(phone: str) -> LeadInput:
    return adapters.parse_indiamart_record(
        {
            "SENDER_NAME": "Test Lead",
            "SENDER_MOBILE": "+91-" + phone[3:],
            "SENDER_CITY": "Hyderabad",
            "QUERY_PRODUCT_NAME": "Test product",
            "QUERY_MESSAGE": "Test enquiry from Mitra",
        }
    )


def _justdial(phone: str) -> LeadInput:
    return adapters.parse_justdial(
        {"name": "Test Lead", "mobile": phone[3:], "category": "Test", "city": "Hyderabad"}
    )


def _meta(phone: str) -> LeadInput:
    return adapters.parse_meta_lead(
        {
            "campaign_name": "Test lead from Mitra",
            "field_data": [
                {"name": "full_name", "values": ["Test Lead"]},
                {"name": "phone_number", "values": [phone]},
                {"name": "city", "values": ["Hyderabad"]},
            ],
        }
    )


SAMPLES: dict[LeadSourceKind, Callable[[str], LeadInput]] = {
    LeadSourceKind.API: _generic(LeadSourceKind.API),
    LeadSourceKind.WEBSITE_FORM: _generic(LeadSourceKind.WEBSITE_FORM),
    LeadSourceKind.GOOGLE_SHEETS: _generic(LeadSourceKind.GOOGLE_SHEETS),
    LeadSourceKind.GOOGLE_FORMS: _generic(LeadSourceKind.GOOGLE_FORMS),
    LeadSourceKind.ZAPIER: _generic(LeadSourceKind.ZAPIER),
    LeadSourceKind.GOOGLE_ADS: _google_ads,
    LeadSourceKind.INDIAMART: _indiamart,
    LeadSourceKind.JUSTDIAL: _justdial,
    LeadSourceKind.META: _meta,
}


def sample_lead(kind: LeadSourceKind, phone: str) -> LeadInput:
    data = SAMPLES[kind](phone)
    data.external_id = None  # every test is a new lead
    data.fields["is_test"] = "true"
    return data
