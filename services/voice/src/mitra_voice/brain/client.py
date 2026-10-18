"""Gemini client + brain config from settings. The API key is read only here, from ``Settings``
(``GEMINI_API_KEY`` in services/voice/.env); it is never logged."""

from __future__ import annotations

from datetime import datetime
from functools import lru_cache
from typing import Any

from google import genai

from mitra_voice.brain.engine import BrainConfig, StreamingModels
from mitra_voice.brain.tools import IST, Clock
from mitra_voice.config import Settings


class BrainNotConfiguredError(RuntimeError):
    pass


def brain_available(settings: Settings) -> bool:
    key = settings.gemini_api_key.get_secret_value().strip() if settings.gemini_api_key else ""
    return settings.mitra_llm == "gemini" and bool(key) and bool(settings.mitra_llm_model)


def brain_config(settings: Settings, *, text_mode: bool = False) -> BrainConfig:
    """Live calls fail fast on a 429 (apology + callback); text mode may wait it out."""
    if not settings.mitra_llm_model:
        raise BrainNotConfiguredError("MITRA_LLM_MODEL is not set")
    return BrainConfig(
        model=settings.mitra_llm_model,
        slow_model=settings.mitra_llm_model_slow or None,
        temperature=settings.mitra_llm_temperature,
        first_token_timeout_s=settings.mitra_llm_first_token_timeout_s,
        thinking_level=settings.mitra_llm_thinking_level or None,
        max_rpm=settings.mitra_llm_max_rpm,
        max_rate_limit_wait_s=settings.mitra_llm_rate_limit_wait_s if text_mode else 0.0,
    )


@lru_cache(maxsize=4)
def _client(api_key: str) -> Any:

    return genai.Client(api_key=api_key)


def gemini_models(settings: Settings) -> StreamingModels:
    """``client.aio.models`` for the configured key (one shared HTTP client per key)."""
    if settings.gemini_api_key is None or not settings.gemini_api_key.get_secret_value().strip():
        raise BrainNotConfiguredError("GEMINI_API_KEY is not set")
    models: StreamingModels = _client(settings.gemini_api_key.get_secret_value()).aio.models
    return models


def brain_clock(settings: Settings) -> Clock | None:
    """A frozen clock when ``MITRA_BRAIN_FIXED_NOW`` is set (reproducible evals), else None."""
    fixed = settings.mitra_brain_fixed_now
    if fixed is None:
        return None
    frozen = fixed if fixed.tzinfo else fixed.replace(tzinfo=IST)

    def clock() -> datetime:
        return frozen

    return clock


__all__ = [
    "BrainNotConfiguredError",
    "brain_available",
    "brain_clock",
    "brain_config",
    "gemini_models",
]
