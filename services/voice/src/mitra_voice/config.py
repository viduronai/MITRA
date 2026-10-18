"""Service settings, read from the environment and ``services/voice/.env`` (gitignored).

Provider keys are never required: with ``MITRA_ENV=local`` a provider whose key is missing falls
back to its mock (with a clear startup message); in every other env it is a startup error.
The live-turn LLM model is never defaulted in code: it must come from ``MITRA_LLM_MODEL``.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

SERVICE_ROOT = Path(__file__).resolve().parents[2]

Env = Literal["local", "dev", "staging", "prod"]
SttProvider = Literal["mock", "sarvam", "deepgram"]
LlmProvider = Literal["mock", "anthropic"]
TtsProvider = Literal["mock", "sarvam", "elevenlabs"]
TurnStrategy = Literal["smart", "vad"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=SERVICE_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    mitra_env: Env = "local"
    host: str = "127.0.0.1"
    port: int = 8200
    log_level: str = "INFO"
    # Pipecat logs through loguru and is very chatty at DEBUG.
    pipecat_log_level: str = "WARNING"

    # Provider selection.
    mitra_stt: SttProvider = "mock"
    mitra_llm: LlmProvider = "mock"
    mitra_tts: TtsProvider = "mock"
    mitra_turn: TurnStrategy = "smart"

    # Provider credentials (empty in .env.example).
    sarvam_api_key: SecretStr | None = None
    anthropic_api_key: SecretStr | None = None
    deepgram_api_key: SecretStr | None = None
    elevenlabs_api_key: SecretStr | None = None

    # Model / voice identifiers come from env only. Empty STT/TTS values use the provider
    # adapter's own default; the LLM has no default and must be set to use a real LLM.
    mitra_llm_model: str | None = None
    mitra_stt_model: str | None = None
    mitra_tts_model: str | None = None
    mitra_tts_voice: str | None = None

    # Employee pack source: services/core when both are set, else a local fixture.
    mitra_core_url: str | None = None
    mitra_core_service_token: SecretStr | None = None

    # Mock tuning (latency simulation).
    mock_llm_ttft_ms: int = Field(default=250, ge=0, le=10_000)
    mock_llm_token_ms: int = Field(default=20, ge=0, le=1_000)
    mock_tool_latency_ms: int = Field(default=600, ge=0, le=10_000)
    mock_tts_ttfb_ms: int = Field(default=90, ge=0, le=5_000)
    mock_tts_ms_per_char: int = Field(default=55, ge=10, le=500)

    @property
    def is_local(self) -> bool:
        return self.mitra_env == "local"


@lru_cache
def get_settings() -> Settings:
    return Settings()
