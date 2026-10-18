"""Caller-language tracking: right after STT, every final transcript updates ``CallContext``.

It runs before the user aggregator, so the call language is already updated when the turn's
``LLMContextFrame`` reaches the brain. Speech normalisation, TTS language, fillers and
back-channels all read ``call.language``.
"""

from __future__ import annotations

from pipecat.frames.frames import Frame, TranscriptionFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from mitra_voice.call_context import CallContext


class LanguageTracker(FrameProcessor):
    def __init__(self, call: CallContext) -> None:
        super().__init__()
        self._call = call

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, TranscriptionFrame) and direction == FrameDirection.DOWNSTREAM:
            code = frame.language.value if frame.language is not None else None
            await self._call.observe_utterance(frame.text, code)
        await self.push_frame(frame, direction)
