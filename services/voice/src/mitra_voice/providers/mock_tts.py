"""Mock TTS: real PCM audio (a soft, syllable-shaped tone) with a duration proportional to the text.

It reports word timestamps like a real streaming TTS, so the output transport releases each word
when it is played. That is what barge-in truncation counts ("words actually played").
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from typing import Any

import numpy as np
from pipecat.frames.frames import ErrorFrame, Frame, TTSAudioRawFrame
from pipecat.services.settings import TTSSettings
from pipecat.services.tts_service import TextAggregationMode, TTSService

CHUNK_MS = 40
WORD_GAP_MS = 60


def word_times(text: str, ms_per_char: int) -> tuple[list[tuple[str, float]], float]:
    """Start time (s) of each word, and total duration (s); word length drives its duration."""
    times: list[tuple[str, float]] = []
    t = 0.0
    for word in text.split():
        times.append((word, round(t, 3)))
        t += (len(word) * ms_per_char + WORD_GAP_MS) / 1000
    return times, max(t, 0.25)


def synth_tone(
    duration_s: float, sample_rate: int, *, pitch_hz: float = 210.0, gain: float = 0.12
) -> bytes:
    """16-bit mono PCM: a tone with a ~4 Hz syllable envelope, so it sounds speech-paced."""
    n = max(1, int(duration_s * sample_rate))
    t = np.arange(n, dtype=np.float64) / sample_rate
    carrier = np.sin(2 * np.pi * pitch_hz * t) + 0.35 * np.sin(2 * np.pi * 2 * pitch_hz * t)
    envelope = 0.5 * (1 - np.cos(2 * np.pi * 4.0 * t))
    fade = np.minimum(1.0, np.minimum(t, t[-1] - t) / 0.02)  # 20 ms fade in/out, no clicks
    samples = gain / 1.35 * carrier * envelope * fade
    return bytes((np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes())


def backchannel_clip(sample_rate: int, *, duration_s: float = 0.28) -> bytes:
    """A short, quieter (-6 dB vs speech) two-note "mm-hm" stand-in for pre-rendered clips."""
    half = duration_s / 2
    return synth_tone(half, sample_rate, pitch_hz=240, gain=0.06) + synth_tone(
        half, sample_rate, pitch_hz=200, gain=0.06
    )


class MockTTSService(TTSService):
    def __init__(self, *, ttfb_ms: int = 90, ms_per_char: int = 55, **kwargs: Any) -> None:
        super().__init__(
            # Text arrives already sentence-chunked and normalised (SpeakableProcessor).
            text_aggregation_mode=TextAggregationMode.TOKEN,
            push_text_frames=False,
            push_stop_frames=True,
            push_start_frame=True,
            settings=TTSSettings(model=None, voice=None, language=None),
            **kwargs,
        )
        self._ttfb_s = ttfb_ms / 1000
        self._ms_per_char = ms_per_char

    def can_generate_metrics(self) -> bool:
        return True

    async def run_tts(self, text: str, context_id: str) -> AsyncGenerator[Frame | None]:
        text = text.strip()
        if not text:
            return
        try:
            await self.start_tts_usage_metrics(text)
            await asyncio.sleep(self._ttfb_s)
            words, duration_s = word_times(text, self._ms_per_char)
            audio = synth_tone(duration_s, self.sample_rate)
            chunk = int(self.sample_rate * CHUNK_MS / 1000) * 2
            await self.stop_ttfb_metrics()
            for i in range(0, len(audio), chunk):
                yield TTSAudioRawFrame(
                    audio=audio[i : i + chunk],
                    sample_rate=self.sample_rate,
                    num_channels=1,
                    context_id=context_id,
                )
                if i == 0:
                    await self.add_word_timestamps(words, context_id)
        except Exception as e:  # pragma: no cover - defensive, mirrors Pipecat services
            yield ErrorFrame(error=f"mock TTS failed: {e}")
