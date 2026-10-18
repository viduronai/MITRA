"""Catalog voices (services/core ``catalog.py``) -> Sarvam Bulbul v3 speakers, in one table.

Bulbul v3 speakers are multilingual: the language is set per request (``target_language_code``),
so one speaker covers every language of its catalog voice. Speakers were picked to match the
catalog persona (gender, warmth). TODO(founder): audition and swap speakers here; nothing else
needs to change.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from mitra_voice.pack import Lang

Gender = Literal["female", "male"]


@dataclass(frozen=True, slots=True)
class Voice:
    id: str
    name: str
    gender: Gender
    languages: tuple[Lang, ...]
    sarvam_speaker: str
    persona: str


VOICES: tuple[Voice, ...] = (
    Voice("priya-te-hyd", "Priya", "female", ("te", "en"), "priya", "Friendly, warm"),
    Voice("arjun-te-vij", "Arjun", "male", ("te", "en"), "aditya", "Calm, reassuring"),
    Voice(
        "lakshmi-te-sig", "Lakshmi", "female", ("te", "en", "hi"), "shreya", "Polished, gracious"
    ),
    Voice("ananya-hi-del", "Ananya", "female", ("hi", "en"), "neha", "Cheerful, energetic"),
    Voice("rohan-hi-mum", "Rohan", "male", ("hi", "en"), "rohan", "Confident, crisp"),
    Voice("meera-hi-sig", "Meera", "female", ("hi", "en"), "ritu", "Elegant, soothing"),
    Voice("kavya-en-blr", "Kavya", "female", ("en", "hi"), "kavya", "Professional, clear"),
    Voice("vikram-en-hyd", "Vikram", "male", ("en", "te"), "rahul", "Warm, patient"),
)
VOICES_BY_ID: dict[str, Voice] = {v.id: v for v in VOICES}
DEFAULT_VOICE: dict[Gender, Voice] = {"female": VOICES[0], "male": VOICES[1]}

SARVAM_LANGUAGE: dict[Lang, str] = {"en": "en-IN", "hi": "hi-IN", "te": "te-IN"}


def voice_for(voice_id: str | None, gender: Gender = "female") -> Voice:
    """The catalog voice, or the default voice of that gender for unknown/missing ids."""
    if voice_id and voice_id in VOICES_BY_ID:
        return VOICES_BY_ID[voice_id]
    return DEFAULT_VOICE[gender]
