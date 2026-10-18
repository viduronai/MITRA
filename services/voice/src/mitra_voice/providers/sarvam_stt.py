"""Sarvam streaming STT that never blocks the audio path.

Pipecat 1.12's ``SarvamSTTService.run_stt`` awaits one websocket send (base64 JSON) per 20 ms
audio frame, inline on the pipeline's audio path. When Sarvam's socket applies backpressure, each
frame takes longer than 20 ms. The pipeline then falls further and further behind real time:
in a live run, VAD saw speech 17 s late, transcripts arrived before their turn started, and the
greeting sat behind queued audio. Here audio is batched into 100 ms chunks and sent from a
background task. On VAD stop the pending audio is drained before Sarvam's flush, so the final
transcript still covers the whole utterance.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncGenerator
from typing import Any

from pipecat.frames.frames import (
    CancelFrame,
    EndFrame,
    Frame,
    StartFrame,
    VADUserStoppedSpeakingFrame,
)
from pipecat.processors.frame_processor import FrameDirection
from pipecat.services.sarvam.stt import SarvamSTTService

CHUNK_MS = 100
DRAIN_TIMEOUT_S = 2.0


class BufferedSarvamSTTService(SarvamSTTService):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._pending = bytearray()
        self._queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._sender: asyncio.Task[None] | None = None

    def _chunk_bytes(self) -> int:
        return int(self.sample_rate * CHUNK_MS / 1000) * 2

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

    async def run_stt(self, audio: bytes) -> AsyncGenerator[Frame | None]:
        self._pending += audio
        if len(self._pending) >= self._chunk_bytes():
            self._queue.put_nowait(bytes(self._pending))
            self._pending.clear()
        yield None

    async def _send_loop(self) -> None:
        while True:
            chunk = await self._queue.get()
            # If the socket fell behind, send everything queued as one message.
            while not self._queue.empty():
                chunk += self._queue.get_nowait()
                self._queue.task_done()
            try:
                async for frame in super().run_stt(chunk):
                    if frame is not None:
                        await self.push_frame(frame)
            finally:
                self._queue.task_done()

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        if isinstance(frame, VADUserStoppedSpeakingFrame):
            # Everything the caller said must reach Sarvam before the base class flushes.
            if self._pending:
                self._queue.put_nowait(bytes(self._pending))
                self._pending.clear()
            # On timeout flush anyway: a late transcript beats a stuck pipeline.
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._queue.join(), DRAIN_TIMEOUT_S)
        await super().process_frame(frame, direction)
