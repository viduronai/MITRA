"""Static catalog (contract §2). Public: needed before sign-up to preview roles and voices."""

from __future__ import annotations

from fastapi import APIRouter, Query

from mitra_core.catalog import RATES, ROLE_TEMPLATES, voices_for
from mitra_core.models.enums import Locale
from mitra_core.schemas.catalog import RateOut, RoleTemplateOut, VoiceOut

router = APIRouter(prefix="/catalog", tags=["catalog"])


@router.get("/role-templates", response_model=list[RoleTemplateOut], summary="Employee roles")
async def list_role_templates() -> list[RoleTemplateOut]:
    return list(ROLE_TEMPLATES)


@router.get("/voices", response_model=list[VoiceOut], summary="Voices, optionally by language")
async def list_voices(language: Locale | None = Query(None)) -> list[VoiceOut]:
    return voices_for(language)


@router.get("/rates", response_model=list[RateOut], summary="Per-minute rates by voice tier")
async def list_rates() -> list[RateOut]:
    return list(RATES)
