"""Consent for pasted / uploaded campaign lists (lead consent policy, docs/08 section 8.5).

The owner ticks an attestation before a campaign can call anyone:

* service lists: "These people are my customers or asked to be contacted about this";
* promotional lists: additionally "I have explicit consent from every person on this list to get
  promotional calls" (DND scrub and the 140-series rules still apply at dial time).

The attestation is kept on the campaign (who, when, exact words, version). Every person queued
gets a consent record (source ``owner_attested_list``, purpose = the campaign) that expires when
the campaign ends, after 30 days at most. ``compliance.check`` at dial time stays the only
decider. Needs a legal check before launch (docs/08 section 8.5).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import or_, update
from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core.models import AppUser, ConsentRecord
from mitra_core.models.campaign import Campaign, CampaignContact
from mitra_core.telephony.enums import CallPurpose, ConsentScope, ConsentSource

IST = ZoneInfo("Asia/Kolkata")
VERSION = "list-attest-v1"
MAX_DAYS = 30
LANGS = ("en", "hi", "te")

SERVICE_TEXTS = {
    "en": "These people are my customers or asked to be contacted about this.",
    "hi": "ये लोग मेरे ग्राहक हैं या इन्होंने इस बारे में संपर्क करने को कहा है।",
    "te": "ఈ వ్యక్తులు నా కస్టమర్లు, లేదా దీని గురించి సంప్రదించమని అడిగారు.",
}
PROMOTIONAL_TEXTS = {
    "en": "I have explicit consent from every person on this list to get promotional calls "
    "from my business.",
    "hi": "इस लिस्ट के हर व्यक्ति से मेरे पास मेरे बिज़नेस से प्रमोशनल कॉल पाने की स्पष्ट सहमति है।",
    "te": "ఈ లిస్ట్‌లోని ప్రతి ఒక్కరి నుంచి నా బిజినెస్ ప్రమోషనల్ కాల్స్ పొందడానికి నా దగ్గర స్పష్టమైన అనుమతి ఉంది.",
}


def lang(value: str | None) -> str:
    return value if value in LANGS else "en"


def scope_for(campaign: Campaign) -> ConsentScope:
    promotional = campaign.purpose == CallPurpose.PROMOTIONAL
    return ConsentScope.PROMOTIONAL if promotional else ConsentScope.SERVICE


def wording(campaign: Campaign, language: str | None) -> str:
    """The exact words the owner ticks (both statements for a promotional list)."""
    words = SERVICE_TEXTS[lang(language)]
    if scope_for(campaign) == ConsentScope.PROMOTIONAL:
        words = f"{words} {PROMOTIONAL_TEXTS[lang(language)]}"
    return words


def attest(campaign: Campaign, user: AppUser, language: str | None, now: datetime) -> None:
    """Record the tick. Ticking again (e.g. when adding people) replaces who/when/words."""
    campaign.consent_scope = scope_for(campaign)
    campaign.consent_text = wording(campaign, language)
    campaign.consent_text_version = VERSION
    campaign.consent_by, campaign.consent_by_name = user.id, user.name
    campaign.consent_at = now


def is_attested(campaign: Campaign) -> bool:
    """The attestation must cover the campaign's current purpose (no stale service tick
    standing in for a promotional list)."""
    return campaign.consent_at is not None and campaign.consent_scope == scope_for(campaign)


def purpose_of(campaign: Campaign) -> str:
    return f"campaign:{campaign.id.hex[:31]}"  # fits consent_record.purpose (40)


def expires_at(campaign: Campaign, now: datetime) -> datetime:
    cap = now + timedelta(days=MAX_DAYS)
    if campaign.ends_on is None:
        return cap
    last = datetime.combine(campaign.ends_on + timedelta(days=1), time(0), tzinfo=IST)
    return max(min(cap, last), now)


def record_consents(
    session: AsyncSession, campaign: Campaign, contacts: Sequence[CampaignContact], now: datetime
) -> int:
    """One consent record per person being queued (rows are only added, never edited)."""
    if not contacts:
        return 0
    if not is_attested(campaign):
        raise ValueError("campaign list is not attested")
    until = expires_at(campaign, now)
    note = f"Owner confirmed the campaign list: {campaign.name}"[:200]
    session.add_all(
        ConsentRecord(
            business_id=campaign.business_id,
            phone_hash=c.phone_hash,
            scope=campaign.consent_scope,
            source=ConsentSource.OWNER_ATTESTED_LIST,
            note=note,
            captured_at=now,
            purpose=purpose_of(campaign),
            text_version=campaign.consent_text_version,
            consent_text=campaign.consent_text,
            expires_at=until,
        )
        for c in contacts
    )
    return len(contacts)


async def expire(session: AsyncSession, campaign: Campaign, now: datetime) -> None:
    """The campaign ended (finished or cancelled): its list consent ends with it."""
    await session.execute(
        update(ConsentRecord)
        .where(
            ConsentRecord.business_id == campaign.business_id,
            ConsentRecord.purpose == purpose_of(campaign),
            ConsentRecord.source == ConsentSource.OWNER_ATTESTED_LIST,
            or_(ConsentRecord.expires_at.is_(None), ConsentRecord.expires_at > now),
        )
        .values(expires_at=now)
    )
