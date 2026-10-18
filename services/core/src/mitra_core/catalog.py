"""Static catalog: role templates, voices and per-minute rates (data in code for Step 2).

Voice ids are stored on ``employee.voice_id``; removing a voice here would orphan employees, so
retire voices by hiding them in a later step rather than deleting them.
"""

from __future__ import annotations

from mitra_core.models.enums import Industry, Locale, RoleTemplate, VoiceTier
from mitra_core.schemas.catalog import RateOut, RoleTemplateOut, VoiceOut

ROLE_TEMPLATES: tuple[RoleTemplateOut, ...] = (
    RoleTemplateOut(
        id=RoleTemplate.RECEPTIONIST,
        name="Receptionist",
        description="Answers every call, shares prices and timings, and books appointments.",
        default_for=[Industry.CLINIC, Industry.OTHER],
    ),
    RoleTemplateOut(
        id=RoleTemplate.LEAD_CALLER,
        name="Lead Caller",
        description="Calls new enquiries within minutes, qualifies them and books site visits.",
        default_for=[Industry.REAL_ESTATE, Industry.EDUCATION],
    ),
    RoleTemplateOut(
        id=RoleTemplate.REMINDER_CALLER,
        name="Reminder Caller",
        description="Reminds customers about appointments, visits and follow-ups so fewer miss.",
        default_for=[Industry.CLINIC],
    ),
    RoleTemplateOut(
        id=RoleTemplate.PAYMENT_CALLER,
        name="Payment Caller",
        description="Politely follows up on pending fees and dues, and shares payment links.",
        default_for=[Industry.EDUCATION],
    ),
)

VOICES: tuple[VoiceOut, ...] = (
    VoiceOut(
        id="priya-te-hyd",
        name="Priya",
        personality="Friendly, warm",
        languages=[Locale.TE, Locale.EN],
        dialect="Hyderabadi",
        gender="female",
        tier=VoiceTier.NATURAL,
        sample_text="నమస్కారం! నేను ప్రియ. మీకు ఎలా సహాయం చేయగలను?",
    ),
    VoiceOut(
        id="arjun-te-vij",
        name="Arjun",
        personality="Calm, reassuring",
        languages=[Locale.TE, Locale.EN],
        dialect="Coastal Andhra",
        gender="male",
        tier=VoiceTier.SMART,
        sample_text="నమస్కారం! నేను అర్జున్. చెప్పండి, మీకు ఎలా సహాయం చేయగలను?",
    ),
    VoiceOut(
        id="lakshmi-te-sig",
        name="Lakshmi",
        personality="Polished, gracious",
        languages=[Locale.TE, Locale.EN, Locale.HI],
        dialect="Standard Telugu",
        gender="female",
        tier=VoiceTier.SIGNATURE,
        sample_text="నమస్కారం! నేను లక్ష్మి. మీ కాల్‌కి ధన్యవాదాలు, మీకు ఏ విధంగా సహాయం చేయగలను?",
    ),
    VoiceOut(
        id="ananya-hi-del",
        name="Ananya",
        personality="Cheerful, energetic",
        languages=[Locale.HI, Locale.EN],
        dialect="Delhi Hindi",
        gender="female",
        tier=VoiceTier.NATURAL,
        sample_text="नमस्ते! मैं अनन्या बोल रही हूँ। बताइए, मैं आपकी क्या मदद कर सकती हूँ?",
    ),
    VoiceOut(
        id="rohan-hi-mum",
        name="Rohan",
        personality="Confident, crisp",
        languages=[Locale.HI, Locale.EN],
        dialect="Mumbai Hindi",
        gender="male",
        tier=VoiceTier.SMART,
        sample_text="नमस्ते! मैं रोहन बोल रहा हूँ। बताइए, मैं आपकी कैसे मदद कर सकता हूँ?",
    ),
    VoiceOut(
        id="meera-hi-sig",
        name="Meera",
        personality="Elegant, soothing",
        languages=[Locale.HI, Locale.EN],
        dialect="Lucknowi Hindi",
        gender="female",
        tier=VoiceTier.SIGNATURE,
        sample_text="नमस्कार! मैं मीरा हूँ। आपके कॉल के लिए धन्यवाद, कहिए मैं क्या सेवा करूँ?",
    ),
    VoiceOut(
        id="kavya-en-blr",
        name="Kavya",
        personality="Professional, clear",
        languages=[Locale.EN, Locale.HI],
        dialect="Indian English (Bengaluru)",
        gender="female",
        tier=VoiceTier.SIGNATURE,
        sample_text="Hello! This is Kavya. Thank you for calling, how may I help you today?",
    ),
    VoiceOut(
        id="vikram-en-hyd",
        name="Vikram",
        personality="Warm, patient",
        languages=[Locale.EN, Locale.TE],
        dialect="Indian English (Hyderabad)",
        gender="male",
        tier=VoiceTier.NATURAL,
        sample_text="Hi, this is Vikram. Happy to help, what can I do for you?",
    ),
)

RATES: tuple[RateOut, ...] = (
    RateOut(tier=VoiceTier.SMART, inr_per_min=3.0),
    RateOut(tier=VoiceTier.NATURAL, inr_per_min=4.5),
    RateOut(tier=VoiceTier.SIGNATURE, inr_per_min=6.0),
)

VOICES_BY_ID: dict[str, VoiceOut] = {v.id: v for v in VOICES}


def voices_for(language: Locale | None) -> list[VoiceOut]:
    return [v for v in VOICES if language is None or language in v.languages]
