from __future__ import annotations

import pytest
from pipecat.services.anthropic.llm import AnthropicLLMService
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.elevenlabs.tts import ElevenLabsTTSService
from pipecat.services.sarvam.stt import SarvamSTTService
from pipecat.services.sarvam.tts import SarvamTTSService

from mitra_voice.config import Settings
from mitra_voice.pack import FIXTURES_DIR, load_fixture
from mitra_voice.providers import (
    ProviderConfigError,
    make_llm,
    make_stt,
    make_tts,
    resolve_providers,
)
from mitra_voice.providers.mock_llm import MockLLMService
from mitra_voice.providers.mock_stt import MockSTTService
from mitra_voice.providers.mock_tts import MockTTSService

PACK = load_fixture(FIXTURES_DIR / "sunrise-clinic.json")


def test_defaults_are_all_mock_with_no_messages() -> None:
    resolved = resolve_providers(Settings())
    assert (resolved.stt, resolved.llm, resolved.tts) == ("mock", "mock", "mock")
    assert resolved.messages == ()
    settings = Settings()
    assert isinstance(make_stt(resolved, settings, PACK, "clinic"), MockSTTService)
    assert isinstance(make_llm(resolved, settings, PACK), MockLLMService)
    assert isinstance(make_tts(resolved, settings, PACK), MockTTSService)


def test_selection_comes_from_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MITRA_STT", "sarvam")
    monkeypatch.setenv("MITRA_LLM", "anthropic")
    monkeypatch.setenv("MITRA_TTS", "elevenlabs")
    monkeypatch.setenv("SARVAM_API_KEY", "test-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("MITRA_LLM_MODEL", "test-model")
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    monkeypatch.setenv("MITRA_TTS_VOICE", "test-voice")
    settings = Settings()
    resolved = resolve_providers(settings)
    assert (resolved.stt, resolved.llm, resolved.tts) == ("sarvam", "anthropic", "elevenlabs")
    assert isinstance(make_stt(resolved, settings, PACK, "clinic"), SarvamSTTService)
    assert isinstance(make_llm(resolved, settings, PACK), AnthropicLLMService)
    assert isinstance(make_tts(resolved, settings, PACK), ElevenLabsTTSService)


def test_deepgram_and_sarvam_tts_are_built_when_keys_present() -> None:
    settings = Settings(
        mitra_stt="deepgram",
        mitra_tts="sarvam",
        deepgram_api_key="test-key",  # type: ignore[arg-type]
        sarvam_api_key="test-key",  # type: ignore[arg-type]
    )
    resolved = resolve_providers(settings)
    assert isinstance(make_stt(resolved, settings, PACK, "clinic"), DeepgramSTTService)
    assert isinstance(make_tts(resolved, settings, PACK), SarvamTTSService)


def test_local_env_falls_back_to_mock_with_a_clear_message() -> None:
    settings = Settings(mitra_stt="sarvam", mitra_llm="anthropic", mitra_tts="elevenlabs")
    resolved = resolve_providers(settings)
    assert (resolved.stt, resolved.llm, resolved.tts) == ("mock", "mock", "mock")
    joined = "\n".join(resolved.messages)
    assert "MITRA_STT=sarvam but SARVAM_API_KEY is not set" in joined
    assert "ANTHROPIC_API_KEY, MITRA_LLM_MODEL" in joined
    assert "ELEVENLABS_API_KEY, MITRA_TTS_VOICE" in joined
    assert "local env only" in joined


def test_anthropic_needs_the_model_from_env_even_with_a_key() -> None:
    settings = Settings(mitra_llm="anthropic", anthropic_api_key="test-key")  # type: ignore[arg-type]
    resolved = resolve_providers(settings)
    assert resolved.llm == "mock"
    assert "MITRA_LLM_MODEL" in resolved.messages[0]


def test_blank_key_counts_as_missing() -> None:
    settings = Settings(mitra_stt="sarvam", sarvam_api_key="  ")  # type: ignore[arg-type]
    assert resolve_providers(settings).stt == "mock"


@pytest.mark.parametrize("env", ["dev", "staging", "prod"])
def test_non_local_env_refuses_to_start_without_keys(env: str) -> None:
    settings = Settings(mitra_env=env, mitra_tts="sarvam")  # type: ignore[arg-type]
    with pytest.raises(ProviderConfigError, match="SARVAM_API_KEY"):
        resolve_providers(settings)


def test_non_local_env_with_mocks_is_allowed() -> None:
    assert resolve_providers(Settings(mitra_env="prod")).stt == "mock"


def test_invalid_provider_name_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MITRA_STT", "whisper")
    with pytest.raises(ValueError, match="mitra_stt"):
        Settings()
