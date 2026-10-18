from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from mitra_core.models.enums import Industry, Locale, RoleTemplate, VoiceTier


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class RoleTemplateOut(_Frozen):
    id: RoleTemplate
    name: str
    description: str
    default_for: list[Industry]
    sample_audio_url: str | None = None


class VoiceOut(_Frozen):
    id: str
    name: str
    personality: str
    languages: list[Locale]
    dialect: str
    gender: str
    tier: VoiceTier
    sample_text: str
    sample_audio_url: str | None = None


class RateOut(_Frozen):
    tier: VoiceTier
    inr_per_min: float
