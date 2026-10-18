"""Provider factories selected by env: ``MITRA_STT``, ``MITRA_LLM``, ``MITRA_TTS``.

``resolve_providers`` runs once at startup. A real provider is used only when everything it needs
is configured; otherwise ``MITRA_ENV=local`` falls back to the mock with a clear message and any
other env refuses to start. The ``make_*`` functions build per-call Pipecat services.
"""

from __future__ import annotations

import dataclasses
import importlib.util
from dataclasses import dataclass
from typing import Any, Literal

from pipecat.services.llm_service import LLMService
from pipecat.services.stt_service import STTService
from pipecat.services.tts_service import TTSService
from pipecat.transcriptions.language import Language
from pydantic import SecretStr

from mitra_voice.call_context import CallContext, stt_lock_language
from mitra_voice.config import LlmProvider, Settings, SttProvider, TtsProvider
from mitra_voice.pack import EmployeePack, Lang, Scenario
from mitra_voice.providers.clips import (
    BackchannelClips,
    ClipSource,
    PhraseCache,
    ToneClips,
    clone_renderer,
    sarvam_renderer,
    shape_clip,
)
from mitra_voice.providers.mock_llm import MockLLMService
from mitra_voice.providers.mock_stt import SCRIPTS, MockSTTService
from mitra_voice.providers.mock_tts import MockTTSService
from mitra_voice.usage import UsageMeter
from mitra_voice.voices import Voice, voice_registry

Kind = Literal["stt", "llm", "tts"]

_LANGUAGE: dict[Lang, Language] = {"en": Language.EN_IN, "hi": Language.HI_IN, "te": Language.TE_IN}


class ProviderConfigError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ResolvedProviders:
    stt: SttProvider
    llm: LlmProvider
    tts: TtsProvider
    messages: tuple[str, ...] = ()


def _requirements(settings: Settings, kind: Kind, name: str) -> list[tuple[str, object]]:
    """(env var, value) pairs a real provider needs; empty for mocks."""
    reqs: dict[tuple[Kind, str], list[tuple[str, object]]] = {
        ("stt", "sarvam"): [("SARVAM_API_KEY", settings.sarvam_api_key)],
        ("stt", "deepgram"): [("DEEPGRAM_API_KEY", settings.deepgram_api_key)],
        ("llm", "anthropic"): [
            ("ANTHROPIC_API_KEY", settings.anthropic_api_key),
            ("MITRA_LLM_MODEL", settings.mitra_llm_model),
        ],
        ("llm", "gemini"): [
            ("GEMINI_API_KEY", settings.gemini_api_key),
            ("MITRA_LLM_MODEL", settings.mitra_llm_model),
            ("the mitra_voice.brain package", _brain_available()),
        ],
        ("llm", "groq"): [
            ("GROQ_API_KEY", settings.groq_api_key),
            ("MITRA_LLM_MODEL", settings.mitra_llm_model),
            ("the mitra_voice.brain package", _brain_available()),
        ],
        ("tts", "sarvam"): [("SARVAM_API_KEY", settings.sarvam_api_key)],
        ("tts", "elevenlabs"): [
            ("ELEVENLABS_API_KEY", settings.elevenlabs_api_key),
            ("MITRA_TTS_VOICE", settings.mitra_tts_voice),
        ],
    }
    return reqs.get((kind, name), [])


def _brain_available() -> str | None:
    """The brain package (built in parallel) provides the Gemini LLM service."""
    return "ok" if importlib.util.find_spec("mitra_voice.brain") is not None else None


def _is_set(value: object) -> bool:
    if isinstance(value, SecretStr):
        return bool(value.get_secret_value().strip())
    return isinstance(value, str) and bool(value.strip())


def resolve_providers(settings: Settings) -> ResolvedProviders:
    messages: list[str] = []
    chosen: dict[Kind, str] = {}
    requested: dict[Kind, str] = {
        "stt": settings.mitra_stt,
        "llm": settings.mitra_llm,
        "tts": settings.mitra_tts,
    }
    for kind, name in requested.items():
        missing = [env for env, value in _requirements(settings, kind, name) if not _is_set(value)]
        if not missing:
            chosen[kind] = name
            continue
        problem = f"MITRA_{kind.upper()}={name} but {', '.join(missing)} is not set"
        if not settings.is_local:
            raise ProviderConfigError(f"{problem} (MITRA_ENV={settings.mitra_env})")
        messages.append(f"{problem}; using the mock {kind.upper()} (local env only).")
        chosen[kind] = "mock"
    return ResolvedProviders(
        stt=chosen["stt"],  # type: ignore[arg-type]
        llm=chosen["llm"],  # type: ignore[arg-type]
        tts=chosen["tts"],  # type: ignore[arg-type]
        messages=tuple(messages),
    )


def _secret(value: SecretStr | None) -> str:
    if value is None:  # resolve_providers guarantees presence for real providers
        raise ProviderConfigError("provider key missing")
    return value.get_secret_value()


def _given(**values: Any) -> dict[str, Any]:
    """Drop unset values so Pipecat's own defaults apply (its settings use NOT_GIVEN)."""
    return {k: v for k, v in values.items() if v is not None}


def make_stt(
    providers: ResolvedProviders,
    settings: Settings,
    pack: EmployeePack,
    scenario: Scenario,
    usage: UsageMeter | None = None,
) -> STTService:
    language = _LANGUAGE[pack.default_language]
    if providers.stt == "sarvam":
        from mitra_voice.providers.sarvam_stt import BufferedSarvamSTTService

        # Streaming websocket STT, flushed on our VAD stop; sends never block the audio path.
        # "codemix" keeps English words in Latin script inside Telugu/Hindi sentences. Packs
        # with one Indic language pin the STT to it (auto-detect misreads short Telugu as
        # Malayalam/Kannada); packs with several Indic languages auto-detect, and each
        # transcript's language drives CallContext.
        lock = stt_lock_language(pack.languages)
        return BufferedSarvamSTTService(
            api_key=_secret(settings.sarvam_api_key),
            usage=usage,
            mode="codemix",
            settings=BufferedSarvamSTTService.Settings(
                **_given(
                    model=settings.mitra_stt_model,
                    language=_LANGUAGE[lock] if lock else None,
                )
            ),
        )
    if providers.stt == "deepgram":
        from pipecat.services.deepgram.stt import DeepgramSTTService

        return DeepgramSTTService(
            api_key=_secret(settings.deepgram_api_key),
            settings=DeepgramSTTService.Settings(
                **_given(model=settings.mitra_stt_model, language=language)
            ),
        )
    return MockSTTService(SCRIPTS[scenario])


def make_llm(
    providers: ResolvedProviders,
    settings: Settings,
    pack: EmployeePack,
    call: CallContext | None = None,
) -> LLMService[Any]:
    if providers.llm in ("gemini", "groq"):  # the brain picks its backend from settings
        from mitra_voice.brain import make_brain_llm

        if call is None:
            raise ProviderConfigError("the brain LLM needs the call context")
        llm: LLMService[Any] = make_brain_llm(pack=pack, settings=settings, call=call)
        return llm
    if providers.llm == "anthropic":
        from pipecat.services.anthropic.llm import AnthropicLLMService

        # The model comes only from MITRA_LLM_MODEL (a fast Haiku-class model for live turns).
        return AnthropicLLMService(
            api_key=_secret(settings.anthropic_api_key),
            settings=AnthropicLLMService.Settings(
                model=settings.mitra_llm_model, enable_prompt_caching=True, max_tokens=200
            ),
        )
    return MockLLMService(
        pack,
        ttft_ms=settings.mock_llm_ttft_ms,
        token_ms=settings.mock_llm_token_ms,
        tool_latency_ms=settings.mock_tool_latency_ms,
    )


def call_voice(settings: Settings, pack: EmployeePack) -> Voice:
    """The voice this call speaks with: a consented team clone or a stock Bulbul speaker
    (registry in voices.py). ``MITRA_TTS_VOICE`` overrides a stock speaker for experiments."""
    voice = voice_registry(settings).resolve(pack.voice_id, pack.voice_gender)
    if settings.mitra_tts_voice and voice.kind == "stock":
        voice = dataclasses.replace(voice, sarvam_speaker=settings.mitra_tts_voice)
    return voice


def make_tts(
    providers: ResolvedProviders,
    settings: Settings,
    pack: EmployeePack,
    usage: UsageMeter | None = None,
) -> TTSService:
    language = _LANGUAGE[pack.default_language]
    if providers.tts == "sarvam":
        from mitra_voice.providers.sarvam_tts import (
            MeteredSarvamTTSService,
            SarvamCloneTTSService,
        )

        voice = call_voice(settings, pack)
        key = _secret(settings.sarvam_api_key)
        if voice.sarvam_voice_id:  # team clone: Instant Voice Cloning websocket
            return SarvamCloneTTSService(
                voice_id=voice.sarvam_voice_id,
                api_key=key,
                usage=usage,
                settings=SarvamCloneTTSService.Settings(
                    language=language, min_buffer_size=settings.mitra_tts_min_buffer
                ),
            )
        # Stock speaker: streaming Bulbul over websocket.
        return MeteredSarvamTTSService(
            api_key=key,
            usage=usage,
            settings=MeteredSarvamTTSService.Settings(
                **_given(
                    model=settings.mitra_tts_model,
                    voice=voice.sarvam_speaker,
                    language=language,
                    min_buffer_size=settings.mitra_tts_min_buffer,
                )
            ),
        )
    if providers.tts == "elevenlabs":
        from pipecat.services.elevenlabs.tts import ElevenLabsTTSService

        return ElevenLabsTTSService(
            api_key=_secret(settings.elevenlabs_api_key),
            settings=ElevenLabsTTSService.Settings(
                **_given(model=settings.mitra_tts_model, voice=settings.mitra_tts_voice)
            ),
        )
    return MockTTSService(
        ttfb_ms=settings.mock_tts_ttfb_ms, ms_per_char=settings.mock_tts_ms_per_char
    )


@dataclass(frozen=True, slots=True)
class Prerendered:
    """Fixed-phrase audio in the call's voice: back-channel clips and greeting/filler phrases."""

    backchannels: ClipSource
    phrases: PhraseCache | None  # None: no pre-rendering (mock or non-Sarvam TTS)


def make_prerendered(
    providers: ResolvedProviders, settings: Settings, pack: EmployeePack, sample_rate: int
) -> Prerendered:
    if providers.tts != "sarvam":
        # TODO(elevenlabs): pre-render through ElevenLabs too; a tone until then.
        return Prerendered(ToneClips(sample_rate), None)
    voice = call_voice(settings, pack)
    key = _secret(settings.sarvam_api_key)
    if voice.sarvam_voice_id:
        renderer = clone_renderer(key, voice_id=voice.sarvam_voice_id, sample_rate=sample_rate)
    else:
        renderer = sarvam_renderer(
            key,
            speaker=voice.sarvam_speaker or "",
            sample_rate=sample_rate,
            model=settings.mitra_tts_model,
        )
    voice_key = f"{voice.cache_key}-{settings.mitra_tts_model or 'default'}"
    return Prerendered(
        backchannels=BackchannelClips(
            PhraseCache(
                renderer,
                voice_key=voice_key,
                sample_rate=sample_rate,
                shaper=shape_clip,
                kind="bc",
            )
        ),
        phrases=PhraseCache(renderer, voice_key=voice_key, sample_rate=sample_rate),
    )


__all__ = [
    "ProviderConfigError",
    "ResolvedProviders",
    "call_voice",
    "make_llm",
    "make_prerendered",
    "make_stt",
    "make_tts",
    "resolve_providers",
]
