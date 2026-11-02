"""Service settings, read from the environment and ``services/voice/.env`` (gitignored).

Provider keys are never required: with ``MITRA_ENV=local`` a provider whose key is missing falls
back to its mock (with a clear startup message); in every other env it is a startup error.
The live-turn LLM model is never defaulted in code: it must come from ``MITRA_LLM_MODEL``.
"""

from __future__ import annotations

from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

SERVICE_ROOT = Path(__file__).resolve().parents[2]

Env = Literal["local", "dev", "staging", "prod"]
SttProvider = Literal["mock", "sarvam", "deepgram"]
LlmProvider = Literal["mock", "anthropic", "gemini", "groq"]
TtsProvider = Literal["mock", "sarvam", "elevenlabs"]
TurnStrategy = Literal["smart", "vad"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=SERVICE_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_ignore_empty=True,  # "KEY=" in .env means unset, never an empty string
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
    # Silero VAD stop window. It also triggers Sarvam's transcript flush, so it sits directly on
    # the latency path; Smart Turn keeps short pauses from ending the turn.
    mitra_vad_stop_ms: int = Field(default=200, ge=80, le=1_000)
    # Smart Turn silence cap for every language; unset = per-language table (turn_tuning.py).
    mitra_smart_turn_max_silence_ms: int | None = Field(default=None, ge=300, le=5_000)
    # Sarvam Bulbul streaming: characters buffered before synthesis starts (API minimum 30).
    mitra_tts_min_buffer: int = Field(default=30, ge=30, le=200)
    # Send a reply's first words to TTS early (after this many words; 0 = whole first clause).
    # Bulbul's first-byte time grows with chunk length, so a short first chunk starts audio sooner.
    mitra_tts_first_chunk_words: int = Field(default=5, ge=0, le=20)
    # Dev only: save each assistant utterance as WAV here (unset = off).
    mitra_record_dir: Path | None = None
    # Dev only: log the event-loop thread's stack whenever the loop stalls for > 1 s.
    mitra_loop_watchdog: bool = False

    # Provider credentials (empty in .env.example).
    sarvam_api_key: SecretStr | None = None
    anthropic_api_key: SecretStr | None = None
    gemini_api_key: SecretStr | None = None
    groq_api_key: SecretStr | None = None
    deepgram_api_key: SecretStr | None = None
    elevenlabs_api_key: SecretStr | None = None

    # Model / voice identifiers come from env only. Empty STT/TTS values use the provider
    # adapter's own default; the LLM has no default and must be set to use a real LLM.
    mitra_llm_model: str | None = None
    # Optional slower/stronger model for background or hard turns (brain); empty = unused.
    mitra_llm_model_slow: str | None = None
    # Live-turn brain: give up on the first token after this long, then retry once.
    mitra_llm_first_token_timeout_s: float = Field(default=1.5, gt=0, le=30)
    mitra_llm_temperature: float = Field(default=0.3, ge=0, le=1)
    # Reasoning level: Gemini thinking_level (unset = "minimal", the fastest) or Groq
    # reasoning_effort (unset = the model default; non-reasoning models reject it).
    mitra_llm_thinking_level: str | None = None
    # Freeze the brain's clock (ISO datetime, IST if no offset) for reproducible evals.
    mitra_brain_fixed_now: datetime | None = None
    # Rate limits per provider (free tiers; they vary by model): requests and estimated
    # tokens per minute, 0 = no pacing. Text mode also waits out 429s up to this long.
    gemini_max_rpm: int = Field(default=0, ge=0, le=100_000)
    gemini_max_tpm: int = Field(default=0, ge=0, le=100_000_000)
    groq_max_rpm: int = Field(default=0, ge=0, le=100_000)
    groq_max_tpm: int = Field(default=0, ge=0, le=100_000_000)
    mitra_llm_rate_limit_wait_s: float = Field(default=0, ge=0, le=600)
    # Text mode only: replay identical LLM requests from this directory (eval re-runs).
    mitra_llm_cache_dir: Path | None = None
    mitra_stt_model: str | None = None
    mitra_tts_model: str | None = None
    mitra_tts_voice: str | None = None
    # Team voices (consented Sarvam clones): local mapping file (default voices.local.json,
    # gitignored) or the same JSON inline. See voices.example.json.
    mitra_voices_file: Path | None = None
    mitra_voices_json: str | None = None

    # Employee pack source: services/core when both are set, else a local fixture.
    mitra_core_url: str | None = None
    mitra_core_service_token: SecretStr | None = None

    # Telephony (transports/telephony.py, carriers/, docs/telephony.md). ``sim`` = the local
    # carrier simulator: outbound "calls" dial nothing. Values below come from the carrier
    # dashboards once the account's KYC is approved (empty in .env.example).
    mitra_telephony_carrier: Literal["sim", "exotel", "plivo"] = "sim"
    # Public https base of this service, used to build wss:// stream URLs for the carrier.
    mitra_public_base_url: str | None = None
    # Exotel: Dashboard > API settings (SID, key, token, subdomain) and App Bazaar (flow id).
    exotel_account_sid: str | None = None
    exotel_api_key: str | None = None
    exotel_api_token: SecretStr | None = None
    exotel_subdomain: str = "api.in.exotel.com"  # Mumbai cluster; api.exotel.com = Singapore
    exotel_app_id: str | None = None  # the call flow holding the Voicebot applet
    exotel_caller_id: str | None = None  # default ExoPhone for outbound
    # Audio Exotel streams to us: 8000 | 16000 | 24000 (Voicebot applet sample-rate setting).
    exotel_sample_rate: Literal[8000, 16000, 24000] = 8000
    # Plivo (secondary carrier): Console > Overview (Auth ID / token) and a Plivo number.
    plivo_auth_id: str | None = None
    plivo_auth_token: SecretStr | None = None
    plivo_caller_id: str | None = None

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
