"""Unit tests for the deterministic extractors (no database)."""

from __future__ import annotations

import pytest

from mitra_core.knowledge.extract import (
    extract_from_html,
    extract_from_text,
    guess_category,
    phones_in,
)
from mitra_core.knowledge.gaps import missing_gaps
from mitra_core.models.enums import FactCategory, FactStatus, Industry

PAGE = """<!doctype html><html><head>
<title> Sunrise Multispeciality Clinic | Hyderabad </title>
<meta name="description" content="Family doctors and paediatrics in Madhapur.">
<style>.x{color:red}</style><script>var phone = "9999999999";</script>
</head><body>
<nav><a href="tel:+91-98480-12345">Call</a> <a href="mailto:Care@SunriseClinic.in">Mail</a></nav>
<h1>Welcome</h1>
<p>Consultation fee: ₹500 (follow-up free within 7 days)</p>
<p>Timings: Mon - Sat, 9:00 AM - 8:00 PM</p>
<div>Plot 12, Road No. 3, Madhapur, Hyderabad 500081</div>
<p>Front desk: 040-23456789 or toll free 1800 123 4567</p>
</body></html>"""


def _facts(page: str) -> dict[tuple[FactCategory, str], list[str]]:
    out: dict[tuple[FactCategory, str], list[str]] = {}
    for f in extract_from_html(page).facts:
        out.setdefault((f.category, f.key), []).append(f.value)
    return out


def test_html_extraction() -> None:
    result = extract_from_html(PAGE)
    assert result.title == "Sunrise Multispeciality Clinic | Hyderabad"
    facts = _facts(PAGE)
    assert facts[(FactCategory.SERVICES, "About")] == [
        "Family doctors and paediatrics in Madhapur."
    ]
    phones = facts[(FactCategory.CONTACT, "Phone")]
    assert "+919848012345" in phones
    assert "040-23456789" in phones
    assert "1800-123-4567" in phones
    assert "+919999999999" not in phones  # inside <script>
    assert facts[(FactCategory.CONTACT, "Email")] == ["care@sunriseclinic.in"]
    assert facts[(FactCategory.PRICES, "Consultation fee")] == [
        "₹500 (follow-up free within 7 days)"
    ]
    assert facts[(FactCategory.TIMINGS, "Opening hours")] == [
        "Timings: Mon - Sat, 9:00 AM - 8:00 PM"
    ]
    assert facts[(FactCategory.LOCATION, "Address")] == [
        "Plot 12, Road No. 3, Madhapur, Hyderabad 500081"
    ]
    assert all(f.status == FactStatus.SUGGESTED for f in result.facts)


def test_html_extraction_dedupes_and_tolerates_garbage() -> None:
    page = "<p>Call 98480 12345</p><p>Call +91 9848012345</p><p><b>unclosed"
    phones = _facts(page)[(FactCategory.CONTACT, "Phone")]
    assert phones == ["+919848012345"]
    assert extract_from_html("").facts == []


def test_text_key_value_lines_are_confirmed() -> None:
    text = """Sunrise Clinic
    Consultation fee: Rs. 500
    Doctors: Dr. Rao (General), Dr. Meena (Paediatrics)
    Parking: Free basement parking
    Timings: 9 AM to 8 PM
    Insurance: Cashless with Star Health
    Ask for appointment on WhatsApp 98480 12345
    """
    result = extract_from_text(text)
    assert result.title == "Sunrise Clinic"
    by_key = {f.key: f for f in result.facts}
    assert by_key["Consultation fee"].category == FactCategory.PRICES
    assert by_key["Consultation fee"].status == FactStatus.CONFIRMED
    assert by_key["Doctors"].category == FactCategory.SERVICES
    assert by_key["Parking"].category == FactCategory.LOCATION
    assert by_key["Timings"].category == FactCategory.TIMINGS
    assert by_key["Insurance"].category == FactCategory.POLICY
    assert by_key["Phone"].value == "+919848012345"
    assert by_key["Phone"].status == FactStatus.SUGGESTED


@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        ("WhatsApp", "98480 12345", FactCategory.CONTACT),
        ("Price range", "₹45 L - ₹1.2 Cr", FactCategory.PRICES),
        ("Site visit timings", "Sat-Sun 10 AM to 5 PM", FactCategory.TIMINGS),
        ("Landmark", "Opposite Inorbit Mall", FactCategory.LOCATION),
        ("Refund", "Within 7 days", FactCategory.POLICY),
        ("Projects", "Green Meadows villas", FactCategory.SERVICES),
        ("Team", "Our doctors are friendly", FactCategory.SERVICES),
        ("Languages", "Telugu, Hindi", FactCategory.FAQ),
        ("Open hours", "24x7", FactCategory.TIMINGS),
    ],
)
def test_guess_category(key: str, value: str, expected: FactCategory) -> None:
    assert guess_category(key, value) == expected


def test_phone_patterns() -> None:
    assert phones_in("Pincode 500081, year 2024") == []
    assert phones_in("Order 12345 67890") == []  # mobiles start with 6-9
    assert phones_in("098480-12345") == ["+919848012345"]


def test_gaps_by_industry() -> None:
    clinic = [g.key for g in missing_gaps(Industry.CLINIC, [])]
    assert clinic == ["Consultation fee", "Timings", "Doctors", "Address", "Parking"]
    have = [
        (FactCategory.PRICES, "Consultation fee", "₹500"),
        (FactCategory.LOCATION, "Parking", "Free"),
        (FactCategory.SERVICES, "Team", "Dr. Rao"),
    ]
    assert [g.key for g in missing_gaps(Industry.CLINIC, have)] == ["Timings", "Address"]
    realty = [g.key for g in missing_gaps(Industry.REAL_ESTATE, [])]
    assert realty == ["Projects", "Price range", "Address", "Site-visit timings"]
    generic = [g.key for g in missing_gaps(Industry.EDUCATION, [])]
    assert generic == ["Services", "Prices", "Timings", "Address", "Phone"]
