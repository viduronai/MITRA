"""Mock STT: one scripted caller line per user turn, so the whole pipeline runs without keys.

Real audio still drives it: Silero VAD decides when the caller speaks, and each detected user turn
yields the next line of the scenario script. While the caller talks, words of the upcoming line
are revealed as interim transcripts (about 2.5 words/s) so back-channel logic sees partials.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Sequence
from typing import Any

from pipecat.frames.frames import (
    Frame,
    InterimTranscriptionFrame,
    TranscriptionFrame,
    UserStartedSpeakingFrame,
    VADUserStartedSpeakingFrame,
    VADUserStoppedSpeakingFrame,
)
from pipecat.processors.frame_processor import FrameDirection
from pipecat.services.settings import STTSettings
from pipecat.services.stt_service import SegmentedSTTService
from pipecat.transcriptions.language import Language
from pipecat.utils.time import time_now_iso8601

from mitra_voice.pack import Scenario

SCRIPTS: dict[Scenario, tuple[str, ...]] = {
    "clinic": (
        "Hi, what is the consultation fee?",
        "What are your timings?",
        "Book me for tomorrow evening.",
        "Where exactly are you located?",
        "Do you have parking near the clinic?",
    ),
    "real_estate": (
        "Hi, I saw your ad. What is the price range for a 2 BHK?",
        "Which projects do you have right now?",
        "Can I book a site visit this weekend?",
        "Is there a home loan tie-up?",
    ),
}

INTERIM_INTERVAL_S = 0.4


class MockSTTService(SegmentedSTTService):
    def __init__(self, script: Sequence[str], **kwargs: Any) -> None:
        if not script:
            raise ValueError("mock STT needs a non-empty script")
        # Pipecat expects every settings field initialised; None = not applicable to a mock.
        kwargs.setdefault("settings", STTSettings(model=None, language=Language.EN_IN))
        super().__init__(**kwargs)
        self._script = tuple(script)
        self._index = 0
        self._emitted_this_turn = False
        self._interim_task: asyncio.Task[None] | None = None

    @property
    def wants_wav_segments(self) -> bool:
        return False

    def can_generate_metrics(self) -> bool:
        return True

    def _upcoming(self) -> str:
        return self._script[self._index % len(self._script)]

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, UserStartedSpeakingFrame):
            self._emitted_this_turn = False
        elif isinstance(frame, VADUserStartedSpeakingFrame) and not self._emitted_this_turn:
            await self._stop_interims()
            self._interim_task = self.create_task(self._push_interims())
        elif isinstance(frame, VADUserStoppedSpeakingFrame):
            await self._stop_interims()

    async def cleanup(self) -> None:
        await self._stop_interims()
        await super().cleanup()

    async def _stop_interims(self) -> None:
        if self._interim_task is not None:
            await self.cancel_task(self._interim_task)
            self._interim_task = None

    async def _push_interims(self) -> None:
        words = self._upcoming().split()
        shown = 0
        while shown < len(words):
            await asyncio.sleep(INTERIM_INTERVAL_S)
            shown += 1
            await self.push_frame(
                InterimTranscriptionFrame(
                    " ".join(words[:shown]), self._user_id, time_now_iso8601(), Language.EN_IN
                )
            )

    async def run_stt(self, audio: bytes) -> AsyncGenerator[Frame | None]:
        # A turn can contain several VAD segments (the caller pauses mid-sentence); the scripted
        # line is the whole utterance, so only the first segment of a turn produces it.
        if self._emitted_this_turn:
            yield None
            return
        self._emitted_this_turn = True
        text = self._upcoming()
        self._index += 1
        yield TranscriptionFrame(text, self._user_id, time_now_iso8601(), Language.EN_IN)
