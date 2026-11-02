"""Back-channels while the caller talks ("hmm", "achha", "avunu"), TRD §5 human layer.

Two processors share a ``UserSpeechState``:
- ``UserSpeechTap`` sits after STT and records turn start, VAD speech/pause and the partial text;
- ``BackchannelPlayer`` sits just before ``transport.output()``, polls ``BackchannelPolicy`` every
  100 ms during a user turn and plays a short low-volume clip straight to the output.

Clips bypass the LLM context and TTS on purpose: they are pre-rendered in the call's voice at
-6 dB (``providers/clips.py``) and must never become part of the conversation. Mock TTS: a short
quiet tone. The policy and the clip follow the caller's current language.

Partial text: Sarvam streaming STT has no interim transcripts, but it returns a final transcript
for each VAD segment (~300 ms into a pause), so segment finals are accumulated as the turn's
partial text, which is exactly when the policy looks for a clause-boundary pause.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from pipecat.frames.frames import (
    Frame,
    InterimTranscriptionFrame,
    OutputAudioRawFrame,
    StartFrame,
    TranscriptionFrame,
    UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame,
    VADUserStartedSpeakingFrame,
    VADUserStoppedSpeakingFrame,
)
from pipecat.processors.frame_processor import (
    FrameDirection,
    FrameProcessor,
    FrameProcessorSetup,
)

from mitra_human import BackchannelPolicy
from mitra_human import Lang as HumanLang
from mitra_voice.call_context import CallContext
from mitra_voice.providers.clips import ClipSource

POLL_INTERVAL_S = 0.1

TokenCallback = Callable[[str], Awaitable[None]]


@dataclass
class UserSpeechState:
    in_turn: bool = False
    turn_started_at: float = 0.0
    speaking: bool = False
    paused_at: float | None = None
    partial_text: str = ""

    def elapsed_ms(self, now: float) -> int:
        return int((now - self.turn_started_at) * 1000) if self.in_turn else 0

    def pause_ms(self, now: float) -> int:
        if self.speaking or self.paused_at is None:
            return 0
        return int((now - self.paused_at) * 1000)


class UserSpeechTap(FrameProcessor):
    def __init__(self, state: UserSpeechState) -> None:
        super().__init__()
        self._state = state

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        s, now = self._state, time.monotonic()
        if isinstance(frame, UserStartedSpeakingFrame):
            s.in_turn, s.turn_started_at, s.partial_text = True, now, ""
            s.speaking, s.paused_at = True, None
        elif isinstance(frame, UserStoppedSpeakingFrame):
            s.in_turn = s.speaking = False
        elif isinstance(frame, VADUserStartedSpeakingFrame):
            s.speaking, s.paused_at = True, None
        elif isinstance(frame, VADUserStoppedSpeakingFrame):
            # The VAD reports the stop after its stop window; the pause began that long ago.
            s.speaking, s.paused_at = False, now - frame.stop_secs
        elif isinstance(frame, InterimTranscriptionFrame):
            s.partial_text = frame.text
        elif isinstance(frame, TranscriptionFrame) and s.in_turn:
            s.partial_text = f"{s.partial_text} {frame.text}".strip()
        await self.push_frame(frame, direction)


class BackchannelPlayer(FrameProcessor):
    def __init__(
        self,
        state: UserSpeechState,
        call: CallContext,
        clips: ClipSource,
        *,
        seed: int | None = None,
        on_token: TokenCallback | None = None,
    ) -> None:
        super().__init__()
        self._state = state
        self._call = call
        self._clips = clips
        self._seed = seed
        self._policies: dict[HumanLang, BackchannelPolicy] = {}
        self._on_token = on_token
        self._task: asyncio.Task[None] | None = None
        self._sample_rate = 16000

    def _policy(self, lang: HumanLang) -> BackchannelPolicy:
        if lang not in self._policies:
            self._policies[lang] = BackchannelPolicy(lang, seed=self._seed)
        return self._policies[lang]

    # FrameProcessor.setup itself narrows BaseObject.setup; mirror its signature.
    async def setup(self, setup: FrameProcessorSetup) -> None:  # type: ignore[override]
        await super().setup(setup)
        self._sample_rate = setup.audio_out_sample_rate

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, StartFrame):
            self._task = self.create_task(self._poll())
        await self.push_frame(frame, direction)

    async def cleanup(self) -> None:
        if self._task is not None:
            await self.cancel_task(self._task)
            self._task = None
        await super().cleanup()

    async def _poll(self) -> None:
        was_in_turn = False
        while True:
            await asyncio.sleep(POLL_INTERVAL_S)
            s, now = self._state, time.monotonic()
            if not s.in_turn:
                was_in_turn = False
                continue
            lang = self._call.human_lang
            policy = self._policy(lang)
            if not was_in_turn:
                policy.new_turn()
                was_in_turn = True
            token = policy.on_user_speech(s.elapsed_ms(now), s.partial_text, s.pause_ms(now))
            clip = self._clips.clip(lang, token) if token else None
            if token is None or clip is None:
                continue  # no clip rendered (yet) for this token: stay silent, never a stand-in
            await self.push_frame(
                OutputAudioRawFrame(audio=clip, sample_rate=self._sample_rate, num_channels=1)
            )
            if self._on_token is not None:
                await self._on_token(token)
