"""Per-session Sarvam usage, so the founder sees what each test call costs in free credits.

Prices from https://docs.sarvam.ai/api/getting-started/pricing (2026-10-18): Bulbul v3 TTS and
Instant Voice Cloning both ₹30 per 10K characters; streaming STT ₹30 per hour, billed per second
of audio sent. New accounts get ₹100 of credit that never expires
(https://docs.sarvam.ai/api/getting-started/ratelimits).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

INR_PER_10K_TTS_CHARS = 30.0
INR_PER_STT_HOUR = 30.0


@dataclass
class UsageMeter:
    tts_chars_live: int = 0  # streamed through the TTS websocket during the call
    tts_chars_prerender: int = 0  # REST renders for the phrase cache (first time per voice)
    cache_hits: int = 0  # greeting/filler/back-channel plays served from cache (free)
    stt_seconds: float = 0.0  # audio actually sent to Sarvam STT

    def add_tts_live(self, chars: int) -> None:
        self.tts_chars_live += chars

    def add_prerender(self, chars: int) -> None:
        self.tts_chars_prerender += chars

    def add_stt_audio(self, num_bytes: int, sample_rate: int) -> None:
        self.stt_seconds += num_bytes / (2 * sample_rate)  # 16-bit mono PCM

    @property
    def estimated_inr(self) -> float:
        chars = self.tts_chars_live + self.tts_chars_prerender
        return chars / 10_000 * INR_PER_10K_TTS_CHARS + self.stt_seconds / 3600 * INR_PER_STT_HOUR

    def summary(self) -> dict[str, Any]:
        return {
            "tts_chars_live": self.tts_chars_live,
            "tts_chars_prerender": self.tts_chars_prerender,
            "cache_hits": self.cache_hits,
            "stt_seconds": round(self.stt_seconds, 1),
            "estimated_inr": round(self.estimated_inr, 3),
        }
