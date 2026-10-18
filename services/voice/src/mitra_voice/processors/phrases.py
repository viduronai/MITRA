"""Play fixed phrases (greeting, fillers) from the pre-rendered cache instead of live TTS.

Sits between ``SpeakableProcessor`` and the TTS. A ``TTSSpeakFrame`` whose text is cached in
the call's voice and current language becomes plain output audio: no TTS round trip, no
credits. A cache miss goes to the live TTS unchanged. Phrases played from cache are not added to
the LLM context here: ``greet`` adds the greeting itself, and fillers never belong there.
"""

from __future__ import annotations

from pipecat.frames.frames import Frame, OutputAudioRawFrame, TTSSpeakFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from mitra_voice.call_context import CallContext
from mitra_voice.providers.clips import PhraseCache
from mitra_voice.usage import UsageMeter

CHUNK_MS = 40


class CachedPhrasePlayer(FrameProcessor):
    def __init__(
        self, cache: PhraseCache | None, call: CallContext, usage: UsageMeter, sample_rate: int
    ) -> None:
        super().__init__()
        self._cache = cache
        self._call = call
        self._usage = usage
        self._sample_rate = sample_rate

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if (
            self._cache is not None
            and direction == FrameDirection.DOWNSTREAM
            and isinstance(frame, TTSSpeakFrame)
        ):
            audio = self._cache.get(self._call.language, frame.text)
            if audio is not None:
                self._usage.cache_hits += 1
                step = int(self._sample_rate * CHUNK_MS / 1000) * 2
                for i in range(0, len(audio), step):
                    await self.push_frame(
                        OutputAudioRawFrame(
                            audio=audio[i : i + step], sample_rate=self._sample_rate, num_channels=1
                        )
                    )
                return
        await self.push_frame(frame, direction)
