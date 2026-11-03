"""The founder's lead consent policy (docs/08 "Lead consent policy"). Pure, no I/O.

1. Forms Mitra controls (website form snippet, Google Forms script): an unticked, required
   checkbox with :data:`CONSENT_TEXTS`. The exact text, its version and the time are stored.
   No tick (or an unknown version) -> no call, no message.
2. Third-party lead forms (Meta, Google Ads, IndiaMART, JustDial): the enquiry itself counts as
   SERVICE consent for answering that enquiry (``enquiry_response``), recorded with the portal as
   source, expiring after ``lead_portal_consent_days`` (30). An explicit ``false`` -> no contact.
3. Generic sources (lead API, Sheets, Zapier/Make/Pabbly/n8n): the owner must tick
   :data:`ATTESTATION_TEXTS` for the source. Without it leads are stored, not called.
4. Promotional contact is untouched: every record here is scope SERVICE only.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from mitra_core.leads.adapters import LeadInput
from mitra_core.leads.enums import LeadSourceKind, LeadStatus
from mitra_core.telephony.enums import ConsentSource

CONSENT_VERSION = "lead-v1"
ATTESTATION_VERSION = "attest-v1"
ENQUIRY_PURPOSE = "enquiry_response"
LANGS = ("en", "hi", "te")

CONSENT_TEXTS = {
    "en": "I agree to get a call or WhatsApp from {business}, possibly from an AI assistant, "
    "about my enquiry.",
    "hi": "मैं सहमत हूँ कि {business} मेरी enquiry के बारे में मुझे call या WhatsApp कर सकता है, "
    "जो एक AI assistant से भी हो सकता है।",
    "te": "నా enquiry గురించి {business} నుంచి call లేదా WhatsApp రావడానికి నేను అంగీకరిస్తున్నాను, "
    "అది AI assistant నుంచి కూడా రావచ్చు.",
}
ATTESTATION_TEXTS = {
    "en": "These people asked to be contacted about their enquiry.",
    "hi": "इन लोगों ने अपनी enquiry के बारे में संपर्क करने को कहा है।",
    "te": "ఈ వ్యక్తులు తమ enquiry గురించి సంప్రదించమని అడిగారు.",
}

FORM_SOURCES = frozenset({LeadSourceKind.WEBSITE_FORM, LeadSourceKind.GOOGLE_FORMS})
PORTAL_SOURCES = frozenset(
    {
        LeadSourceKind.META,
        LeadSourceKind.GOOGLE_ADS,
        LeadSourceKind.INDIAMART,
        LeadSourceKind.JUSTDIAL,
    }
)
GENERIC_SOURCES = frozenset(
    {LeadSourceKind.API, LeadSourceKind.GOOGLE_SHEETS, LeadSourceKind.ZAPIER}
)


def policy_of(kind: LeadSourceKind) -> str:
    if kind in FORM_SOURCES:
        return "form_checkbox"
    if kind in PORTAL_SOURCES:
        return "portal_enquiry"
    return "owner_attestation"


def lang(value: str | None) -> str:
    return value if value in LANGS else "en"


def consent_text(business_name: str, language: str | None) -> str:
    return CONSENT_TEXTS[lang(language)].format(business=business_name)


@dataclass(frozen=True, slots=True)
class Attestation:
    text_version: str
    text: str


@dataclass(frozen=True, slots=True)
class ConsentOutcome:
    """Either a record to write (``refused`` is None) or the lead status explaining why not."""

    refused: LeadStatus | None
    source: ConsentSource | None = None
    text_version: str | None = None
    text: str | None = None
    expires_at: datetime | None = None
    note: str | None = None


def decide(
    data: LeadInput,
    *,
    business_name: str,
    attestation: Attestation | None,
    now: datetime,
    portal_days: int,
) -> ConsentOutcome:
    if data.consent is False:
        return ConsentOutcome(LeadStatus.NO_CONSENT)
    kind = data.source
    if kind in FORM_SOURCES:
        if data.consent is not True or data.consent_version != CONSENT_VERSION:
            return ConsentOutcome(LeadStatus.NO_CONSENT)
        return ConsentOutcome(
            None,
            source=ConsentSource(kind.value),
            text_version=CONSENT_VERSION,
            text=consent_text(business_name, data.consent_lang),
            note=f"Ticked the consent box on the {kind.value.replace('_', ' ')}",
        )
    if kind in PORTAL_SOURCES:
        return ConsentOutcome(
            None,
            source=ConsentSource(kind.value),
            text=data.consent_text,
            expires_at=now + timedelta(days=portal_days),
            note=f"Enquiry via {kind.value.replace('_', ' ')}: service contact about it only",
        )
    if attestation is None:
        return ConsentOutcome(LeadStatus.NO_ATTESTATION)
    return ConsentOutcome(
        None,
        source=ConsentSource.OWNER_ATTESTED,
        text_version=attestation.text_version,
        text=attestation.text,
        note=f"Owner confirmed {kind.value} leads asked to be contacted",
    )
