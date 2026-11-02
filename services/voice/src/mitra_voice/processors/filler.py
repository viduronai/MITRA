"""Instant acknowledgement ("Sure, one second.") when the answer is predicted to be slow (> 700 ms).

Sits between the user aggregator and the LLM: on each ``LLMContextFrame`` it predicts the answer
latency and, if ``FillerPolicy`` agrees, queues a ``TTSSpeakFrame`` ahead of the context so the
filler plays while the LLM (and any tool call) is still working. Fillers stay out of the context.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Literal

from pipecat.frames.frames import Frame, LLMContextFrame, TTSSpeakFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from mitra_human import FillerPolicy
from mitra_human import Lang as HumanLang
from mitra_voice.call_context import CallContext
from mitra_voice.intents import needs_tool
from mitra_voice.latency import LatencyTracker, derive, percentile
from mitra_voice.processors.reply import last_user_text

PRIOR_ANSWER_MS = 450  # LLM TTFT + TTS TTFB before any turn has been measured (WORKFLOWS §1)


class LatencyPredictor:
    """Expected ms from end of turn to first answer audio: measured median so far + tool time."""

    def __init__(self, tracker: LatencyTracker, *, tool_latency_ms: int) -> None:
        self._tracker = tracker
        self._tool_latency_ms = tool_latency_ms

    def expected_ms(self, user_text: str) -> int:
        samples: list[float] = []
        for turn in self._tracker.completed():
            if turn.filler:  # a filler turn's first audio is the filler, not the answer
                continue
            d = derive(turn)
            ttft, ttfb = d["llm_ttft_ms"], d["tts_ttfb_ms"]
            if ttft is not None and ttfb is not None:
                samples.append(ttft + ttfb)
        base = percentile(samples, 50) if samples else PRIOR_ANSWER_MS
        return int(base + (self._tool_latency_ms if needs_tool(user_text) else 0))


class FillerProcessor(FrameProcessor):
    def __init__(
        self,
        predictor: LatencyPredictor,
        *,
        call: CallContext,
        gender: Literal["female", "male"] = "female",
        on_filler: Callable[[str], Awaitable[None]] | None = None,
    ) -> None:
        super().__init__()
        self._predictor = predictor
        self._call = call
        self._gender = gender
        self._policies: dict[HumanLang, FillerPolicy] = {}
        self._on_filler = on_filler
        self._turn_index = 0

    def _policy(self, lang: HumanLang) -> FillerPolicy:
        if lang not in self._policies:
            self._policies[lang] = FillerPolicy(lang, gender=self._gender)
        return self._policies[lang]

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, LLMContextFrame) and direction == FrameDirection.DOWNSTREAM:
            self._turn_index += 1
            user_text = last_user_text(frame.context)
            expected = self._predictor.expected_ms(user_text)
            lang = self._call.human_lang
            filler = self._policy(lang).filler_for(expected, self._turn_index)
            self._call.filler_spoken = bool(filler)
            if filler:
                await self.push_frame(TTSSpeakFrame(filler, append_to_context=False))
                if self._on_filler is not None:
                    await self._on_filler(filler)
        await self.push_frame(frame, direction)
