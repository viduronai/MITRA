"""Startup warm-up: pay one-time import and model-load costs before the first call.

Several imports happen lazily on first use (the OpenAI types pulled in by Pipecat's default LLM
adapter, the Sarvam SDK, provider modules) and onnxruntime loads its DLLs on the first
session. On the shared event loop that froze every call: 3.5 s and 10.5 s stalls were measured
on the first live call after a restart. ``warm_up`` runs in a worker thread at startup instead.
"""

from __future__ import annotations

import importlib
import time

import structlog

from mitra_voice.config import Settings
from mitra_voice.providers import ResolvedProviders

log = structlog.get_logger(__name__)

_ALWAYS = (
    "pipecat.adapters.services.open_ai_adapter",
    "pipecat.audio.vad.silero",
    "pipecat.audio.turn.smart_turn.local_smart_turn_v3",
)
_BY_PROVIDER = {
    "sarvam": (
        "sarvamai",
        "pipecat.services.sarvam.stt",
        "pipecat.services.sarvam.tts",
        "mitra_voice.providers.sarvam_stt",
    ),
    "deepgram": ("pipecat.services.deepgram.stt",),
    "elevenlabs": ("pipecat.services.elevenlabs.tts",),
    "anthropic": ("pipecat.services.anthropic.llm",),
    "gemini": ("mitra_voice.brain",),
    "groq": ("mitra_voice.brain",),
}


def warm_up(providers: ResolvedProviders, settings: Settings) -> None:
    started = time.perf_counter()
    modules = list(_ALWAYS)
    for name in {providers.stt, providers.llm, providers.tts}:
        modules += _BY_PROVIDER.get(name, ())
    for module in modules:
        importlib.import_module(module)

    from mitra_voice.pipeline import make_turn_analyzers

    make_turn_analyzers(settings)  # first ONNX sessions load the runtime DLLs
    log.info("voice.warmed_up", ms=round((time.perf_counter() - started) * 1000))
