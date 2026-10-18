"""Back-channel clips ("mm-hmm", "अच्छा", "సరే") pre-rendered in the call's TTS voice.

At call start every ``BackchannelPolicy`` token of the call's languages is rendered once with the
call's speaker, trimmed, attenuated by 6 dB and cached in memory and on disk
(``services/voice/.cache/clips``, gitignored), so later calls with the same voice cost no API
calls. Playback then needs no TTS round trip. With mock TTS the clip is a quiet tone.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import wave
from collections.abc import Awaitable, Callable, Iterable
from pathlib import Path
from typing import ClassVar, Protocol

import numpy as np
import structlog

from mitra_human.backchannel import TOKENS
from mitra_voice.config import SERVICE_ROOT
from mitra_voice.pack import Lang
from mitra_voice.providers.mock_tts import backchannel_clip
from mitra_voice.voices import SARVAM_LANGUAGE

log = structlog.get_logger(__name__)

CACHE_DIR = SERVICE_ROOT / ".cache" / "clips"
GAIN = 0.5  # -6 dB relative to the voice
MAX_CLIP_S = 0.9
_SILENCE_LEVEL = 300  # int16 amplitude treated as silence when trimming

Renderer = Callable[[str, Lang], Awaitable[bytes]]  # (token, lang) -> 16-bit mono PCM


class ClipSource(Protocol):
    def clip(self, lang: Lang, token: str) -> bytes | None: ...


class ToneClips:
    """Mock TTS: the same short quiet tone for every token."""

    def __init__(self, sample_rate: int) -> None:
        self._clip = backchannel_clip(sample_rate)

    def clip(self, lang: Lang, token: str) -> bytes | None:
        return self._clip


def shape_clip(pcm: bytes, sample_rate: int) -> bytes:
    """Trim leading/trailing silence, cap the length and attenuate by 6 dB."""
    samples = np.frombuffer(pcm, dtype="<i2").astype(np.int32)
    voiced = np.flatnonzero(np.abs(samples) > _SILENCE_LEVEL)
    if voiced.size:
        samples = samples[voiced[0] : voiced[-1] + 1]
    samples = samples[: int(MAX_CLIP_S * sample_rate)]
    return bytes((samples * GAIN).astype("<i2").tobytes())


class PrerenderedClips:
    """Clips rendered by ``renderer``; memory -> disk -> render, keyed by voice/lang/token."""

    _memory: ClassVar[dict[str, bytes]] = {}  # process-wide: shared by every call

    def __init__(
        self, renderer: Renderer, *, voice_key: str, sample_rate: int, cache_dir: Path = CACHE_DIR
    ) -> None:
        self._renderer = renderer
        self._voice_key = voice_key
        self._sample_rate = sample_rate
        self._cache_dir = cache_dir

    def _key(self, lang: Lang, token: str) -> str:
        digest = hashlib.sha1(f"{lang}:{token}".encode()).hexdigest()[:12]  # noqa: S324 - cache key
        return f"{self._voice_key}-{lang}-{digest}-{self._sample_rate}"

    def clip(self, lang: Lang, token: str) -> bytes | None:
        return self._memory.get(self._key(lang, token))

    async def prerender(self, languages: Iterable[Lang]) -> int:
        """Make every token of ``languages`` available; returns how many were newly rendered."""
        jobs = [(lang, token) for lang in dict.fromkeys(languages) for token in TOKENS[lang]]
        rendered = await asyncio.gather(*(self._ensure(lang, token) for lang, token in jobs))
        return sum(rendered)

    async def _ensure(self, lang: Lang, token: str) -> bool:
        key = self._key(lang, token)
        if key in self._memory:
            return False
        path = self._cache_dir / f"{key}.pcm"
        cached = await asyncio.to_thread(_read_if_exists, path)
        if cached is not None:
            self._memory[key] = cached
            return False
        try:
            pcm = shape_clip(await self._renderer(token, lang), self._sample_rate)
        except Exception as e:  # a missing clip only means no back-channel for that token
            log.warning("clips.render_failed", lang=lang, error=type(e).__name__)
            return False
        self._memory[key] = pcm
        await asyncio.to_thread(_write, path, pcm)
        return True


def _read_if_exists(path: Path) -> bytes | None:
    return path.read_bytes() if path.exists() else None


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def wav_to_pcm(wav_bytes: bytes, sample_rate: int) -> bytes:
    with wave.open(io.BytesIO(wav_bytes)) as w:
        if w.getframerate() != sample_rate or w.getsampwidth() != 2 or w.getnchannels() != 1:
            raise ValueError("unexpected clip format")
        return bytes(w.readframes(w.getnframes()))


def sarvam_renderer(api_key: str, *, speaker: str, sample_rate: int, model: str | None) -> Renderer:
    """Render with Sarvam's REST TTS (same speaker and model as the call's streaming TTS)."""
    from sarvamai import AsyncSarvamAI

    client = AsyncSarvamAI(api_subscription_key=api_key)

    async def render(token: str, lang: Lang) -> bytes:
        res = await client.text_to_speech.convert(
            text=token,
            target_language_code=SARVAM_LANGUAGE[lang],
            speaker=speaker,
            speech_sample_rate=sample_rate,
            **({"model": model} if model else {}),
        )
        return wav_to_pcm(base64.b64decode("".join(res.audios)), sample_rate)

    return render
