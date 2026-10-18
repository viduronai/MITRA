"""Test doubles: an in-memory transport that paces audio like a real one, and an energy VAD.

Silero is trained on speech and (correctly) ignores synthetic tones, so pipeline tests swap in a
plain RMS-threshold VAD; everything else in the pipeline is the production code path.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable

import numpy as np
from pipecat.audio.vad.vad_analyzer import VADAnalyzer, VADParams
from pipecat.frames.frames import InputAudioRawFrame, OutputAudioRawFrame, StartFrame
from pipecat.transports.base_input import BaseInputTransport
from pipecat.transports.base_output import BaseOutputTransport
from pipecat.transports.base_transport import TransportParams

IN_RATE = 16000
CHUNK_MS = 20


class EnergyVAD(VADAnalyzer):
    def __init__(self) -> None:
        super().__init__(
            sample_rate=IN_RATE,
            params=VADParams(confidence=0.5, start_secs=0.1, stop_secs=0.2, min_volume=0.0),
        )

    def num_frames_required(self) -> int:
        return 512

    def voice_confidence(self, buffer: bytes) -> float:
        samples = np.frombuffer(buffer, dtype=np.int16).astype(np.float32) / 32768
        rms = float(np.sqrt(np.mean(samples**2))) if samples.size else 0.0
        return 1.0 if rms > 0.02 else 0.0


def speech_chunk(rng: np.random.Generator) -> bytes:
    """20 ms of loud noise-modulated tone: 'speech' for the energy VAD."""
    n = IN_RATE * CHUNK_MS // 1000
    t = np.arange(n) / IN_RATE
    samples = 0.3 * np.sin(2 * np.pi * 180 * t) + 0.05 * rng.standard_normal(n)
    return bytes((samples * 32767).astype("<i2").tobytes())


SILENCE = bytes(IN_RATE * CHUNK_MS // 1000 * 2)


class FakeInput(BaseInputTransport):
    """Streams 20 ms frames in real time; ``speaking`` decides between speech and silence."""

    def __init__(self) -> None:
        super().__init__(TransportParams(audio_in_enabled=True))
        self.speaking = False
        self._task: asyncio.Task[None] | None = None
        self._rng = np.random.default_rng(7)

    async def start(self, frame: StartFrame) -> None:
        await super().start(frame)
        await self.set_transport_ready(frame)
        self._task = self.create_task(self._stream())

    async def cleanup(self) -> None:
        if self._task is not None:
            await self.cancel_task(self._task)
        await super().cleanup()

    async def _stream(self) -> None:
        while True:
            audio = speech_chunk(self._rng) if self.speaking else SILENCE
            await self.push_audio_frame(
                InputAudioRawFrame(audio=audio, sample_rate=IN_RATE, num_channels=1)
            )
            await asyncio.sleep(CHUNK_MS / 1000)


class FakeOutput(BaseOutputTransport):
    """'Plays' audio in real time so barge-in can land mid-reply."""

    def __init__(self) -> None:
        super().__init__(TransportParams(audio_out_enabled=True))
        self.audio_bytes = 0

    async def start(self, frame: StartFrame) -> None:
        await super().start(frame)
        await self.set_transport_ready(frame)

    async def write_audio_frame(self, frame: OutputAudioRawFrame) -> bool:
        self.audio_bytes += len(frame.audio)
        await asyncio.sleep(len(frame.audio) / 2 / frame.sample_rate)
        return True


async def wait_for(predicate: Callable[[], bool], within: float = 10.0) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + within
    while not predicate():
        if loop.time() > deadline:
            raise TimeoutError("condition not met in time")
        await asyncio.sleep(0.02)
