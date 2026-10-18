"""Brain backends + config from settings (``MITRA_LLM=gemini|groq``). API keys are read only
here, from ``Settings`` (services/voice/.env); they are never logged."""

from __future__ import annotations

from datetime import datetime
from functools import lru_cache
from typing import Any

from google import genai
from pydantic import SecretStr

from mitra_voice.brain.backend import ChatBackend
from mitra_voice.brain.engine import BrainConfig
from mitra_voice.brain.gemini_backend import GeminiBackend
from mitra_voice.brain.openai_backend import OpenAICompatBackend, groq_client
from mitra_voice.brain.tools import IST, Clock
from mitra_voice.config import Settings

BRAIN_PROVIDERS = ("gemini", "groq")


class BrainNotConfiguredError(RuntimeError):
    pass


def _key(settings: Settings) -> str:
    secret: SecretStr | None = (
        settings.gemini_api_key if settings.mitra_llm == "gemini" else settings.groq_api_key
    )
    return secret.get_secret_value().strip() if secret else ""


def brain_available(settings: Settings) -> bool:
    return (
        settings.mitra_llm in BRAIN_PROVIDERS
        and bool(_key(settings))
        and bool(settings.mitra_llm_model)
    )


def brain_config(settings: Settings, *, text_mode: bool = False) -> BrainConfig:
    """Live calls fail fast on a 429 (apology + callback); text mode may wait it out."""
    if not settings.mitra_llm_model:
        raise BrainNotConfiguredError("MITRA_LLM_MODEL is not set")
    provider = settings.mitra_llm
    reasoning = settings.mitra_llm_thinking_level or ("minimal" if provider == "gemini" else None)
    rpm, tpm = (
        (settings.groq_max_rpm, settings.groq_max_tpm)
        if provider == "groq"
        else (settings.gemini_max_rpm, settings.gemini_max_tpm)
    )
    return BrainConfig(
        model=settings.mitra_llm_model,
        slow_model=settings.mitra_llm_model_slow or None,
        temperature=settings.mitra_llm_temperature,
        first_token_timeout_s=settings.mitra_llm_first_token_timeout_s,
        reasoning=reasoning,
        max_rpm=rpm,
        max_tpm=tpm,
        max_rate_limit_wait_s=settings.mitra_llm_rate_limit_wait_s if text_mode else 0.0,
    )


@lru_cache(maxsize=4)
def _gemini_client(api_key: str) -> Any:
    return genai.Client(api_key=api_key)


@lru_cache(maxsize=4)
def _groq_client(api_key: str) -> Any:
    return groq_client(api_key)


def make_backend(settings: Settings) -> ChatBackend:
    """The configured provider's backend (one shared HTTP client per key)."""
    key = _key(settings)
    if not key:
        raise BrainNotConfiguredError(f"no API key for MITRA_LLM={settings.mitra_llm}")
    if settings.mitra_llm == "gemini":
        return GeminiBackend(_gemini_client(key).aio.models)
    if settings.mitra_llm == "groq":
        return OpenAICompatBackend(_groq_client(key), provider="groq")
    raise BrainNotConfiguredError(f"MITRA_LLM={settings.mitra_llm} is not a brain provider")


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
    "BRAIN_PROVIDERS",
    "BrainNotConfiguredError",
    "brain_available",
    "brain_clock",
    "brain_config",
    "make_backend",
]
