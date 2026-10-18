"""Sarvam streaming STT that never blocks the audio path, sends only speech, and is metered.

1. Non-blocking: Pipecat 1.12's ``SarvamSTTService.run_stt`` awaits one websocket send per 20 ms
   frame, inline on the pipeline's audio path. Under backpressure each frame took longer than
   20 ms and the pipeline fell behind real time: in a live run VAD saw speech 17 s late,
   transcripts arrived before their turn started, and the greeting sat behind queued audio. Audio
   is now batched into 100 ms chunks and sent from a background task.
2. Speech-only (credits): Sarvam bills STT per second of audio sent. Silence is no longer
   streamed: audio is sent from VAD start (with a 1 s pre-roll, since our VAD decides
   ~0.2 s into speech and further downstream) until VAD stop. A 100 ms silence keepalive
   goes every 15 s when idle. On VAD stop, pending audio is drained before Sarvam's flush, so the
   final transcript covers the whole utterance.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections import deque
from collections.abc import AsyncGenerator
from typing import Any

from pipecat.frames.frames import (
    CancelFrame,
    EndFrame,
    Frame,
    StartFrame,
    VADUserStartedSpeakingFrame,
    VADUserStoppedSpeakingFrame,
)
from pipecat.processors.frame_processor import FrameDirection
from pipecat.services.sarvam.stt import SarvamSTTService

from mitra_voice.usage import UsageMeter

CHUNK_MS = 100
PREROLL_S = 1.0
KEEPALIVE_S = 15.0
DRAIN_TIMEOUT_S = 2.0


class BufferedSarvamSTTService(SarvamSTTService):
    def __init__(self, *, usage: UsageMeter | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._usage = usage
        self._pending = bytearray()
        self._preroll: deque[bytes] = deque()
        self._preroll_bytes = 0
        self._speaking = False
        self._last_sent = time.monotonic()
        self._queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._sender: asyncio.Task[None] | None = None

    def _bytes_for(self, seconds: float) -> int:
        return int(self.sample_rate * seconds) * 2

    async def start(self, frame: StartFrame) -> None:
        await super().start(frame)
        self._sender = self.create_task(self._send_loop())

    async def stop(self, frame: EndFrame) -> None:
        await self._stop_sender()
        await super().stop(frame)

    async def cancel(self, frame: CancelFrame) -> None:
        await self._stop_sender()
        await super().cancel(frame)

    async def _stop_sender(self) -> None:
        if self._sender is not None:
            await self.cancel_task(self._sender)
            self._sender = None

    def _enqueue(self, audio: bytes) -> None:
        self._queue.put_nowait(audio)
        self._last_sent = time.monotonic()

    async def run_stt(self, audio: bytes) -> AsyncGenerator[Frame | None]:
        if self._speaking:
            self._pending += audio
            if len(self._pending) >= self._bytes_for(CHUNK_MS / 1000):
                self._enqueue(bytes(self._pending))
                self._pending.clear()
        else:
            self._preroll.append(audio)
            self._preroll_bytes += len(audio)
            while self._preroll_bytes > self._bytes_for(PREROLL_S):
                self._preroll_bytes -= len(self._preroll.popleft())
            if time.monotonic() - self._last_sent > KEEPALIVE_S:
                self._enqueue(bytes(self._bytes_for(CHUNK_MS / 1000)))  # silence keepalive
        yield None

    async def _send_loop(self) -> None:
        while True:
            chunk = await self._queue.get()
            # If the socket fell behind, send everything queued as one message.
            while not self._queue.empty():
                chunk += self._queue.get_nowait()
                self._queue.task_done()
            try:
                if self._usage is not None:
                    self._usage.add_stt_audio(len(chunk), self.sample_rate)
                async for frame in super().run_stt(chunk):
                    if frame is not None:
                        await self.push_frame(frame)
            finally:
                self._queue.task_done()

    def begin_speech(self) -> None:
        """VAD start: send the pre-roll (speech onset), then stream until VAD stop."""
        if self._speaking:
            return
        self._speaking = True
        if self._preroll:
            self._enqueue(b"".join(self._preroll))
            self._preroll.clear()
            self._preroll_bytes = 0

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        if isinstance(frame, VADUserStartedSpeakingFrame):
            self.begin_speech()
        elif isinstance(frame, VADUserStoppedSpeakingFrame):
            # Everything the caller said must reach Sarvam before the base class flushes.
            self._speaking = False
            if self._pending:
                self._enqueue(bytes(self._pending))
                self._pending.clear()
            # On timeout flush anyway: a late transcript beats a stuck pipeline.
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._queue.join(), DRAIN_TIMEOUT_S)
        await super().process_frame(frame, direction)
