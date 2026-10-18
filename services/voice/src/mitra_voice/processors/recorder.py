"""Dev-only: save each assistant utterance (greeting, filler, reply) as a WAV.

Enabled only when ``MITRA_RECORD_DIR`` is set. These are voice recordings, so never enable it in
an environment with real callers until recording consent and storage (S3 Mumbai) are in place.
"""

from __future__ import annotations

import wave
from pathlib import Path

from pipecat.frames.frames import Frame, TTSAudioRawFrame, TTSStartedFrame, TTSStoppedFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from mitra_voice.call_context import CallContext


class ReplyRecorder(FrameProcessor):
    def __init__(self, out_dir: Path, call: CallContext) -> None:
        super().__init__()
        self._dir = out_dir
        self._call = call
        self._audio = bytearray()
        self._rate = 24000
        self._count = 0

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if direction == FrameDirection.DOWNSTREAM:
            if isinstance(frame, TTSStartedFrame):
                self._audio.clear()
            elif isinstance(frame, TTSAudioRawFrame):
                self._audio += frame.audio
                self._rate = frame.sample_rate
            elif isinstance(frame, TTSStoppedFrame) and self._audio:
                self._write()
        await self.push_frame(frame, direction)

    def _write(self) -> None:
        self._count += 1
        self._dir.mkdir(parents=True, exist_ok=True)
        name = f"{self._call.session_id[:8]}-{self._count:02d}-{self._call.language}.wav"
        with wave.open(str(self._dir / name), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(self._rate)
            w.writeframes(bytes(self._audio))
        self._audio.clear()
