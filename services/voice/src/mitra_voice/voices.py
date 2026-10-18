"""Voices: stock Sarvam Bulbul speakers per catalog voice, plus consented team-member clones.

Stock voices map the core catalog (``services/core`` ``catalog.py``) to Bulbul v3 speakers.
Bulbul speakers are multilingual (language set per request), so one speaker covers every
language of its catalog voice.

Team voices are the founder's team members, cloned with Sarvam Instant Voice Cloning (beta,
``svc-…`` voice ids, generated through ``/voices/clone``, not the Bulbul ``speaker`` field).
They live in a local, gitignored mapping file (``services/voice/voices.local.json``; schema in
``voices.example.json``) or the ``MITRA_VOICES_JSON`` env var. Every team voice must carry a
consent record (who, date, scope, evidence). An entry without one, or with consent revoked, is
refused and never loaded. A team voice can ``replace`` a catalog voice (every pack using that
catalog id then speaks with the clone) or be addressed by its own id (a core pack ``voice_id``).
"""

from __future__ import annotations

import datetime as dt
import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Literal

import structlog
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from mitra_voice.config import SERVICE_ROOT, Settings
from mitra_voice.pack import Lang

log = structlog.get_logger(__name__)

Gender = Literal["female", "male"]
VoiceKind = Literal["stock", "team"]
LOCAL_VOICES_FILE = SERVICE_ROOT / "voices.local.json"
SARVAM_LANGUAGE: dict[Lang, str] = {"en": "en-IN", "hi": "hi-IN", "te": "te-IN"}


# --- consent + mapping file schema (validated at the boundary) ---------------------------------


class ConsentRecord(BaseModel):
    """Who agreed, when, to what, and where the signed evidence lives (never the recording)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    person: str = Field(min_length=2, max_length=120)
    date: dt.date
    scope: str = Field(min_length=10, max_length=500)
    evidence: str = Field(min_length=3, max_length=300)  # e.g. signed form id / document path
    revoked: bool = False

    @field_validator("date")
    @classmethod
    def _not_in_future(cls, value: dt.date) -> dt.date:
        if value > dt.date.today():  # noqa: DTZ011 - a calendar date, compared as one
            raise ValueError("consent date is in the future")
        return value


class TeamVoiceEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{2,63}$")
    name: str = Field(min_length=1, max_length=60)
    gender: Gender
    languages: tuple[Lang, ...] = Field(min_length=1)
    sarvam_voice_id: str = Field(pattern=r"^svc-[A-Za-z0-9-]{8,64}$")
    replaces: str | None = None
    persona: str = Field(default="Team voice", max_length=120)
    consent: ConsentRecord | None = None


class VoiceConfigError(ValueError):
    pass


# --- voices ------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Voice:
    id: str
    name: str
    gender: Gender
    languages: tuple[Lang, ...]
    persona: str
    kind: VoiceKind = "stock"
    sarvam_speaker: str | None = None  # stock Bulbul speaker
    sarvam_voice_id: str | None = None  # team clone (svc-…)
    replaces: str | None = None
    consent: ConsentRecord | None = None

    @property
    def cache_key(self) -> str:
        """Identifies the sound of this voice for pre-rendered audio caches."""
        return (
            f"clone-{self.sarvam_voice_id}"
            if self.sarvam_voice_id
            else f"bulbul-{self.sarvam_speaker}"
        )


STOCK_VOICES: tuple[Voice, ...] = (
    Voice(
        "priya-te-hyd", "Priya", "female", ("te", "en"), "Friendly, warm", sarvam_speaker="priya"
    ),
    Voice(
        "arjun-te-vij", "Arjun", "male", ("te", "en"), "Calm, reassuring", sarvam_speaker="aditya"
    ),
    Voice(
        "lakshmi-te-sig",
        "Lakshmi",
        "female",
        ("te", "en", "hi"),
        "Polished, gracious",
        sarvam_speaker="shreya",
    ),
    Voice(
        "ananya-hi-del",
        "Ananya",
        "female",
        ("hi", "en"),
        "Cheerful, energetic",
        sarvam_speaker="neha",
    ),
    Voice(
        "rohan-hi-mum", "Rohan", "male", ("hi", "en"), "Confident, crisp", sarvam_speaker="rohan"
    ),
    Voice(
        "meera-hi-sig", "Meera", "female", ("hi", "en"), "Elegant, soothing", sarvam_speaker="ritu"
    ),
    Voice(
        "kavya-en-blr",
        "Kavya",
        "female",
        ("en", "hi"),
        "Professional, clear",
        sarvam_speaker="kavya",
    ),
    Voice("vikram-en-hyd", "Vikram", "male", ("en", "te"), "Warm, patient", sarvam_speaker="rahul"),
)
STOCK_BY_ID: dict[str, Voice] = {v.id: v for v in STOCK_VOICES}
DEFAULT_STOCK: dict[Gender, str] = {"female": "priya-te-hyd", "male": "arjun-te-vij"}


def team_voice(entry: TeamVoiceEntry) -> Voice:
    """A loadable team voice; raises ``VoiceConfigError`` unless consent is on record."""
    if entry.consent is None:
        raise VoiceConfigError(f"team voice {entry.id!r} has no consent record; refusing to load")
    if entry.consent.revoked:
        raise VoiceConfigError(f"team voice {entry.id!r}: consent revoked; refusing to load")
    if entry.id in STOCK_BY_ID:
        raise VoiceConfigError(f"team voice id {entry.id!r} collides with a stock voice id")
    if entry.replaces is not None and entry.replaces not in STOCK_BY_ID:
        raise VoiceConfigError(f"team voice {entry.id!r} replaces unknown voice {entry.replaces!r}")
    return Voice(
        id=entry.id,
        name=entry.name,
        gender=entry.gender,
        languages=entry.languages,
        persona=entry.persona,
        kind="team",
        sarvam_voice_id=entry.sarvam_voice_id,
        replaces=entry.replaces,
        consent=entry.consent,
    )


@dataclass
class VoiceRegistry:
    team: dict[str, Voice] = field(default_factory=dict)
    refused: list[str] = field(default_factory=list)  # reasons, safe to show (no voice ids)

    @property
    def replacements(self) -> dict[str, Voice]:
        return {v.replaces: v for v in self.team.values() if v.replaces}

    def all(self) -> list[Voice]:
        return [*self.team.values(), *STOCK_VOICES]

    def get(self, voice_id: str) -> Voice | None:
        return self.team.get(voice_id) or STOCK_BY_ID.get(voice_id)

    def resolve(self, voice_id: str | None, gender: Gender = "female") -> Voice:
        """The voice a call speaks with: a team voice by id, a catalog voice (or its team
        replacement), else the gender's default catalog voice (or its replacement)."""
        if voice_id and voice_id in self.team:
            return self.team[voice_id]
        stock_id = voice_id if voice_id in STOCK_BY_ID else DEFAULT_STOCK[gender]
        return self.replacements.get(stock_id) or STOCK_BY_ID[stock_id]


def parse_registry(data: object) -> VoiceRegistry:
    """Build a registry from mapping-file data. Invalid entries are refused one by one."""
    registry = VoiceRegistry()
    entries = data.get("team_voices", []) if isinstance(data, dict) else None
    if not isinstance(entries, list):
        raise VoiceConfigError('voice mapping must be {"team_voices": [...]}')
    for i, raw in enumerate(entries):
        label = raw.get("id", f"#{i}") if isinstance(raw, dict) else f"#{i}"
        try:
            voice = team_voice(TeamVoiceEntry.model_validate(raw))
        except (ValidationError, VoiceConfigError) as e:
            reason = _short_reason(e)
            registry.refused.append(f"{label}: {reason}")
            log.error("voices.refused", voice=label, reason=reason)
            continue
        if voice.id in registry.team:
            registry.refused.append(f"{label}: duplicate id")
            continue
        registry.team[voice.id] = voice
    return registry


def _short_reason(e: Exception) -> str:
    if isinstance(e, ValidationError):
        first = e.errors()[0]
        where = ".".join(str(p) for p in first["loc"])
        return f"{where}: {first['msg']}"
    return re.sub(r"\s+", " ", str(e))


def load_registry(path: Path | None, inline_json: str | None = None) -> VoiceRegistry:
    if inline_json:
        return parse_registry(json.loads(inline_json))
    if path is None or not path.exists():
        return VoiceRegistry()
    return parse_registry(json.loads(path.read_text(encoding="utf-8")))


@lru_cache(maxsize=8)
def _cached_registry(path: Path | None, inline_json: str | None) -> VoiceRegistry:
    return load_registry(path, inline_json)


def voice_registry(settings: Settings) -> VoiceRegistry:
    """The process-wide registry for these settings (loaded once; restart to pick up edits)."""
    return _cached_registry(
        settings.mitra_voices_file or LOCAL_VOICES_FILE, settings.mitra_voices_json
    )


def voice_for(voice_id: str | None, gender: Gender = "female") -> Voice:
    """Stock-only resolution (no team voices): the catalog voice or the gender default."""
    return VoiceRegistry().resolve(voice_id, gender)
