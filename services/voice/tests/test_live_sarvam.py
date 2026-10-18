"""Live Sarvam checks (opt-in: ``uv run pytest -m live``). About 3 API calls per run.

Keys are read from services/voice/.env through Settings, never printed.
"""

from __future__ import annotations

import asyncio
import time

import pytest
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.frames.frames import (
    Frame,
    InputAudioRawFrame,
    StartFrame,
    TranscriptionFrame,
    TTSAudioRawFrame,
    TTSSpeakFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.transports.base_input import BaseInputTransport
from pipecat.transports.base_transport import TransportParams
from pipecat.turns.user_stop import SpeechTimeoutUserTurnStopStrategy
from pipecat.turns.user_turn_strategies import UserTurnStrategies
from pipecat.workers.runner import WorkerRunner

from mitra_voice.call_context import detect_caller_language
from mitra_voice.config import SERVICE_ROOT, Settings
from mitra_voice.pack import FIXTURES_DIR, load_fixture
from mitra_voice.providers import make_stt, make_tts, resolve_providers
from mitra_voice.providers.clips import sarvam_renderer

pytestmark = pytest.mark.live


def _settings() -> Settings:
    settings = Settings(_env_file=SERVICE_ROOT / ".env", mitra_stt="sarvam", mitra_tts="sarvam")  # type: ignore[call-arg]
    key = settings.sarvam_api_key
    if key is None or not key.get_secret_value().strip():
        pytest.skip("SARVAM_API_KEY not configured in services/voice/.env")
    return settings


class _ClipInput(BaseInputTransport):
    def __init__(self, pcm: bytes) -> None:
        super().__init__(TransportParams(audio_in_enabled=True))
        self._pcm = pcm

    async def start(self, frame: StartFrame) -> None:
        await super().start(frame)
        await self.set_transport_ready(frame)
        self.create_task(self._feed())

    async def _feed(self) -> None:
        chunk, silence = 640, bytes(640)
        frames = [silence] * 25
        frames += [
            self._pcm[i : i + chunk].ljust(chunk, b"\0") for i in range(0, len(self._pcm), chunk)
        ]
        frames += [silence] * 150
        for audio in frames:
            await self.push_audio_frame(
                InputAudioRawFrame(audio=audio, sample_rate=16000, num_channels=1)
            )
            await asyncio.sleep(0.02)


class _Collect(FrameProcessor):
    def __init__(self) -> None:
        super().__init__()
        self.frames: list[tuple[float, Frame]] = []

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if direction == FrameDirection.DOWNSTREAM:
            self.frames.append((time.perf_counter(), frame))
        await self.push_frame(frame, direction)


async def _run(
    processors: list[FrameProcessor], seconds: float, initial: list[Frame] | None = None
) -> None:
    worker = PipelineWorker(
        Pipeline(processors),
        params=PipelineParams(audio_in_sample_rate=16000, audio_out_sample_rate=24000),
        enable_rtvi=False,
        idle_timeout_secs=None,
    )
    runner = WorkerRunner(handle_sigint=False)
    await runner.add_workers(worker)

    async def drive() -> None:
        await asyncio.sleep(1.0)
        if initial:
            await worker.queue_frames(initial)
        await asyncio.sleep(seconds)
        await worker.cancel()

    await asyncio.gather(runner.run(), drive())


async def test_bulbul_telugu_roundtrips_through_streaming_stt() -> None:
    settings = _settings()
    assert settings.sarvam_api_key is not None
    render = sarvam_renderer(
        settings.sarvam_api_key.get_secret_value(), speaker="rahul", sample_rate=16000, model=None
    )
    pcm = await render("నమస్కారం, కన్సల్టేషన్ ఫీజు ఎంత?", "te")
    pack = load_fixture(FIXTURES_DIR / "sunrise-clinic.json")
    stt = make_stt(resolve_providers(settings), settings, pack, "clinic")
    user = LLMContextAggregatorPair(
        LLMContext(),
        user_params=LLMUserAggregatorParams(
            vad_analyzer=SileroVADAnalyzer(params=VADParams(stop_secs=0.2)),
            user_turn_strategies=UserTurnStrategies(stop=[SpeechTimeoutUserTurnStopStrategy()]),
        ),
    ).user()
    collect = _Collect()
    await _run([_ClipInput(pcm), stt, collect, user], seconds=len(pcm) / 32000 + 5)

    finals = [f for _, f in collect.frames if isinstance(f, TranscriptionFrame)]
    assert finals, "no transcript from Sarvam"
    text = " ".join(f.text for f in finals)
    assert any("ఀ" <= ch <= "౿" for ch in text), text  # Telugu script came back
    code = finals[-1].language.value if finals[-1].language else None
    assert detect_caller_language(text, code, "en") == "te"


async def test_streaming_bulbul_returns_audio_quickly() -> None:
    settings = _settings()
    pack = load_fixture(FIXTURES_DIR / "sunrise-clinic.json")
    tts = make_tts(resolve_providers(settings), settings, pack)
    collect = _Collect()
    sent = time.perf_counter()
    await _run([tts, collect], seconds=4, initial=[TTSSpeakFrame("Namaskaram, ela unnaru?")])
    audio = [(t, f) for t, f in collect.frames if isinstance(f, TTSAudioRawFrame)]
    assert audio, "no audio from Bulbul"
    assert sum(len(f.audio) for _, f in audio) > 24000  # > 0.5 s of 24 kHz speech
    assert audio[0][0] - sent < 1.0 + 3.0  # 1 s pipeline start + generous network budget
