from __future__ import annotations

from collections.abc import Iterator

import pytest

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
)


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Tests never see the developer's real env or .env keys."""
    for name in _ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
