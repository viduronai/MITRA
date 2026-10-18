from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from mitra_voice import voices
from mitra_voice.config import Settings, get_settings

_ENV_VARS = (
    "MITRA_ENV",
    "MITRA_STT",
    "MITRA_LLM",
    "MITRA_TTS",
    "MITRA_TURN",
    "MITRA_LLM_MODEL",
    "MITRA_STT_MODEL",
    "MITRA_TTS_MODEL",
    "MITRA_TTS_VOICE",
    "MITRA_CORE_URL",
    "MITRA_CORE_SERVICE_TOKEN",
    "SARVAM_API_KEY",
    "ANTHROPIC_API_KEY",
    "DEEPGRAM_API_KEY",
    "ELEVENLABS_API_KEY",
    "GEMINI_API_KEY",
    "MITRA_LLM_MODEL_SLOW",
    "MITRA_LLM_THINKING_LEVEL",
    "MITRA_BRAIN_FIXED_NOW",
    "MITRA_VAD_STOP_MS",
    "MITRA_SMART_TURN_MAX_SILENCE_MS",
    "MITRA_TTS_MIN_BUFFER",
    "MITRA_TTS_FIRST_CHUNK_WORDS",
    "MITRA_RECORD_DIR",
    "MITRA_LOOP_WATCHDOG",
    "MITRA_VOICES_FILE",
    "MITRA_VOICES_JSON",
    "GROQ_API_KEY",
    "GEMINI_MAX_RPM",
    "GEMINI_MAX_TPM",
    "GROQ_MAX_RPM",
    "GROQ_MAX_TPM",
    "MITRA_LLM_RATE_LIMIT_WAIT_S",
    "MITRA_LLM_CACHE_DIR",
)


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    """Tests never see the developer's real env or .env keys."""
    for name in _ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    # Never the developer's real team voices (voices.local.json) either.
    monkeypatch.setattr(voices, "LOCAL_VOICES_FILE", tmp_path / "no-voices.local.json")
    voices._cached_registry.cache_clear()
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
    voices._cached_registry.cache_clear()
