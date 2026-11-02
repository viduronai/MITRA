"""Lead payload adapters, phone normalisation and webhook signatures (pure, no database)."""

from __future__ import annotations

import pytest

from mitra_core.leads import adapters
from mitra_core.leads.adapters import AdapterError
from mitra_core.leads.enums import LeadSourceKind
from mitra_core.leads.phone import normalize_indian_mobile
from mitra_core.leads.samples import SAMPLES, sample_lead
from mitra_core.leads.service import call_variables
from mitra_core.webhooks import signing
from mitra_core.webhooks.sender import UnsafeUrlError, validate_url


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("9876543210", "+919876543210"),
        ("98765 43210", "+919876543210"),
        ("098765-43210", "+919876543210"),
        ("+91-9876543210", "+919876543210"),
        ("+91 98765 43210", "+919876543210"),
        ("919876543210", "+919876543210"),
        ("00919876543210", "+919876543210"),
        (9876543210, "+919876543210"),
        ("5876543210", None),  # not a mobile series
        ("+14155550123", None),  # not Indian
        ("12345", None),
        ("", None),
        (None, None),
    ],
)
def test_normalize_indian_mobile(raw: object, expected: str | None) -> None:
    assert normalize_indian_mobile(raw) == expected


def test_generic_recognises_sheet_columns_and_keeps_extras_as_variables() -> None:
    data = adapters.parse_generic(
        {
            "Full Name": "Ravi Kumar",
            "Mobile No.": "98765 43210",
            "City": "Kondapur",
            "Budget (Lakhs)": 80,
            "source": "google_sheets",
            "external_id": "row-12",
            "consent": "yes",
        },
        LeadSourceKind.API,
    )
    assert data.phone_e164 == "+919876543210"
    assert data.name == "Ravi Kumar"
    assert data.source == LeadSourceKind.GOOGLE_SHEETS
    assert data.external_id == "row-12"
    assert data.consent is True
    # The phone number never lands in the call variables.
    assert data.fields == {"city": "Kondapur", "budget_lakhs": "80"}


def test_generic_rejects_portal_kinds_and_missing_phone() -> None:
    data = adapters.parse_generic({"phone": "9876543210", "source": "meta"}, LeadSourceKind.API)
    assert data.source == LeadSourceKind.API  # a generic payload cannot pose as Meta
    with pytest.raises(AdapterError):
        adapters.parse_generic({"name": "No phone"}, LeadSourceKind.API)


def test_generic_nested_fields_and_first_last_name() -> None:
    data = adapters.parse_generic(
        {"first_name": "Lakshmi", "last_name": "R", "fields": {"phone": "9123456789", "plot": "A"}},
        LeadSourceKind.API,
    )
    assert data.phone_e164 == "+919123456789"
    assert data.name == "Lakshmi R"
    assert data.fields == {"plot": "A"}


def test_field_limits() -> None:
    body = {"phone": "9876543210"} | {f"col{i}": "x" * 900 for i in range(50)}
    data = adapters.parse_generic(body, LeadSourceKind.API)
    assert len(data.fields) == adapters.MAX_FIELDS
    assert all(len(v) == adapters.MAX_VALUE for v in data.fields.values())


def test_google_ads_payload() -> None:
    data = adapters.parse_google_ads(
        {
            "lead_id": "TeSter-123",
            "campaign_id": 987,
            "google_key": "secret",
            "user_column_data": [
                {"column_id": "FULL_NAME", "string_value": "Arjun Rao"},
                {"column_id": "PHONE_NUMBER", "string_value": "+919876543210"},
                {"column_id": "CITY", "string_value": "Gachibowli"},
            ],
        }
    )
    assert (data.name, data.phone_e164, data.external_id) == (
        "Arjun Rao",
        "+919876543210",
        "TeSter-123",
    )
    assert data.source_detail == "Google Ads campaign 987"
    assert data.fields == {"city": "Gachibowli"}


def test_indiamart_push_payload() -> None:
    data = adapters.parse_indiamart_push(
        {
            "CODE": 200,
            "STATUS": "SUCCESS",
            "RESPONSE": {
                "UNIQUE_QUERY_ID": "2546378912",
                "SENDER_NAME": "Suresh",
                "SENDER_MOBILE": "+91-9988776655",
                "SENDER_CITY": "Vijayawada",
                "QUERY_PRODUCT_NAME": "Steel Almirah",
                "QUERY_MESSAGE": "Need 10 pieces",
            },
        }
    )
    assert data.source == LeadSourceKind.INDIAMART
    assert data.phone_e164 == "+919988776655"
    assert data.external_id == "2546378912"
    assert data.source_detail == "IndiaMART: Steel Almirah"
    assert data.fields["product"] == "Steel Almirah"
    with pytest.raises(AdapterError):
        adapters.parse_indiamart_push({"CODE": 200})


def test_justdial_payload() -> None:
    data = adapters.parse_justdial(
        {"leadid": "JD1", "name": "Mohan", "mobile": "9988776655", "category": "Dentists"}
    )
    assert (data.phone_e164, data.external_id, data.source_detail) == (
        "+919988776655",
        "JD1",
        "JustDial: Dentists",
    )
    assert data.fields == {"category": "Dentists"}


def test_meta_lead_and_consent_boxes() -> None:
    lead = {
        "id": "LG1",
        "campaign_name": "Diwali offer",
        "field_data": [
            {"name": "full_name", "values": ["Priya"]},
            {"name": "phone_number", "values": ["+919876543210"]},
            {"name": "which_bhk?", "values": ["3BHK"]},
        ],
        "custom_disclaimer_responses": [{"checkbox_key": "c1", "is_checked": "1"}],
    }
    data = adapters.parse_meta_lead(lead)
    assert data.source_detail == "Diwali offer"
    assert data.fields == {"which_bhk": "3BHK"}
    assert data.consent is True
    lead["custom_disclaimer_responses"] = [{"checkbox_key": "c1", "is_checked": "0"}]
    assert adapters.parse_meta_lead(lead).consent is False


def test_call_variables_are_valid_dialer_names() -> None:
    data = adapters.parse_generic(
        {"phone": "9876543210", "name": "Ravi", "2bhk": "yes", "area": "Kokapet"},
        LeadSourceKind.API,
    )
    variables = call_variables(data)
    assert variables["lead_name"] == "Ravi"
    assert variables["lead_source"] == "api"
    assert variables["f_2bhk"] == "yes"
    assert variables["area"] == "Kokapet"


def test_every_source_has_a_sample() -> None:
    assert set(SAMPLES) == set(LeadSourceKind)
    for kind in LeadSourceKind:
        data = sample_lead(kind, "+919876543210")
        assert data.source == kind
        assert data.phone_e164 == "+919876543210"


def test_signature_roundtrip_and_replay_window() -> None:
    secret = signing.generate_secret()
    body = b'{"event":"lead.created"}'
    header = signing.header_value(secret, 1_700_000_000, body)
    assert signing.verify(secret, header, body, now=1_700_000_100)
    assert not signing.verify(secret, header, body + b" ", now=1_700_000_100)
    assert not signing.verify("whsec_other", header, body, now=1_700_000_100)
    assert not signing.verify(secret, header, body, now=1_700_001_000)  # too old
    assert not signing.verify(secret, "garbage", body, now=1_700_000_000)


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/hook",
        "https://localhost/hook",
        "https://127.0.0.1/hook",
        "https://10.0.0.5/hook",
        "https://169.254.169.254/latest",
        "https://user:pw@example.com/hook",
        "ftp://example.com",
    ],
)
def test_unsafe_webhook_urls_refused(url: str) -> None:
    with pytest.raises(UnsafeUrlError):
        validate_url(url, allow_private=False)


def test_public_webhook_url_allowed() -> None:
    assert validate_url("https://hooks.zapier.com/x/1", allow_private=False)
    assert validate_url("http://localhost:9000/hook", allow_private=True)
