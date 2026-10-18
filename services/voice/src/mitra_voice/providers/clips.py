"""Pre-rendered speech in the call's voice: greeting, fillers and back-channels.

Fixed phrases are rendered once per voice (stock Bulbul speaker or team clone) and language
through Sarvam's REST API. They are cached in memory and on disk (``services/voice/.cache/
phrases``, gitignored), so repeated test calls spend no credits on them and play them without a
TTS round trip. Back-channel clips are additionally trimmed, capped and attenuated by 6 dB. With
mock TTS, back-channels are a quiet tone and nothing is pre-rendered.
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

import httpx
import numpy as np
import structlog

from mitra_human.backchannel import TOKENS
from mitra_voice.config import SERVICE_ROOT
from mitra_voice.pack import Lang
from mitra_voice.providers.mock_tts import backchannel_clip
from mitra_voice.voices import SARVAM_LANGUAGE

log = structlog.get_logger(__name__)

CACHE_DIR = SERVICE_ROOT / ".cache" / "phrases"
GAIN = 0.5  # back-channels: -6 dB relative to the voice
MAX_CLIP_S = 0.9
_SILENCE_LEVEL = 300  # int16 amplitude treated as silence when trimming
CLONE_REST_URL = "https://api.sarvam.ai/voices/clone"
RENDER_TIMEOUT_S = 15.0

Renderer = Callable[[str, Lang], Awaitable[bytes]]  # (text, lang) -> 16-bit mono PCM
Shaper = Callable[[bytes, int], bytes]
OnRender = Callable[[int], None]  # characters billed for a fresh render


class ClipSource(Protocol):
    def clip(self, lang: Lang, token: str) -> bytes | None: ...


class ToneClips:
    """Mock TTS: the same short quiet tone for every back-channel token."""

    def __init__(self, sample_rate: int) -> None:
        self._clip = backchannel_clip(sample_rate)

    def clip(self, lang: Lang, token: str) -> bytes | None:
        return self._clip


def trim_silence(pcm: bytes) -> np.ndarray:
    samples = np.frombuffer(pcm, dtype="<i2").astype(np.int32)
    voiced = np.flatnonzero(np.abs(samples) > _SILENCE_LEVEL)
    return samples[voiced[0] : voiced[-1] + 1] if voiced.size else samples


def shape_clip(pcm: bytes, sample_rate: int) -> bytes:
    """Back-channel shaping: trim leading/trailing silence, cap the length, attenuate 6 dB."""
    samples = trim_silence(pcm)[: int(MAX_CLIP_S * sample_rate)]
    return bytes((samples * GAIN).astype("<i2").tobytes())


def shape_phrase(pcm: bytes, sample_rate: int) -> bytes:
    """Greeting/filler shaping: only trim the silence the REST API pads around speech."""
    return bytes(trim_silence(pcm).astype("<i2").tobytes())


class PhraseCache:
    """Audio for fixed phrases in one voice: memory -> disk -> render (once)."""

    _memory: ClassVar[dict[str, bytes]] = {}  # process-wide: shared by every call

    def __init__(
        self,
        renderer: Renderer,
        *,
        voice_key: str,
        sample_rate: int,
        shaper: Shaper = shape_phrase,
        kind: str = "phrase",
        cache_dir: Path = CACHE_DIR,
    ) -> None:
        self._renderer = renderer
        self._voice_key = voice_key
        self._sample_rate = sample_rate
        self._shaper = shaper
        self._kind = kind
        self._cache_dir = cache_dir

    def _key(self, lang: Lang, text: str) -> str:
        digest = hashlib.sha1(f"{lang}:{text}".encode()).hexdigest()[:12]  # noqa: S324 - cache key
        return f"{self._voice_key}-{self._kind}-{lang}-{digest}-{self._sample_rate}"

    def get(self, lang: Lang, text: str) -> bytes | None:
        return self._memory.get(self._key(lang, text))

    async def prerender(
        self, items: Iterable[tuple[Lang, str]], *, on_render: OnRender | None = None
    ) -> int:
        """Make every (lang, text) available; returns how many were newly rendered (billed)."""
        jobs = list(dict.fromkeys(items))
        done = await asyncio.gather(*(self.ensure(lang, text, on_render) for lang, text in jobs))
        return sum(done)

    async def ensure(self, lang: Lang, text: str, on_render: OnRender | None = None) -> bool:
        key = self._key(lang, text)
        if key in self._memory:
            return False
        path = self._cache_dir / f"{key}.pcm"
        cached = await asyncio.to_thread(_read_if_exists, path)
        if cached is not None:
            self._memory[key] = cached
            return False
        try:
            pcm = self._shaper(await self._renderer(text, lang), self._sample_rate)
        except Exception as e:  # a missing phrase only means live TTS / no back-channel
            log.warning("phrases.render_failed", kind=self._kind, lang=lang, error=type(e).__name__)
            return False
        if on_render is not None:
            on_render(len(text))
        self._memory[key] = pcm
        await asyncio.to_thread(_write, path, pcm)
        return True


class BackchannelClips:
    """``ClipSource`` over a back-channel ``PhraseCache`` (shaped clips)."""

    def __init__(self, cache: PhraseCache) -> None:
        self.cache = cache

    def clip(self, lang: Lang, token: str) -> bytes | None:
        return self.cache.get(lang, token)

    async def prerender(self, languages: Iterable[Lang], on_render: OnRender | None = None) -> int:
        items = [(lang, token) for lang in dict.fromkeys(languages) for token in TOKENS[lang]]
        return await self.cache.prerender(items, on_render=on_render)


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
    """Stock Bulbul speaker via Sarvam's REST TTS (same speaker/model as the streaming TTS)."""
    from sarvamai import AsyncSarvamAI

    client = AsyncSarvamAI(api_subscription_key=api_key)

    async def render(text: str, lang: Lang) -> bytes:
        res = await client.text_to_speech.convert(
            text=text,
            target_language_code=SARVAM_LANGUAGE[lang],
            speaker=speaker,
            speech_sample_rate=sample_rate,
            **({"model": model} if model else {}),
        )
        return wav_to_pcm(base64.b64decode("".join(res.audios)), sample_rate)

    return render


def clone_renderer(
    api_key: str,
    *,
    voice_id: str,
    sample_rate: int,
    transport: httpx.AsyncBaseTransport | None = None,
) -> Renderer:
    """Team clone via Sarvam Instant Voice Cloning REST (``POST /voices/clone``, beta).

    Multipart form; exactly one of ``voice_id`` / ``ref_audio`` (we only ever send the saved
    ``svc-`` id, never reference audio). Max 1000 characters per request.
    """

    async def render(text: str, lang: Lang) -> bytes:
        form = {
            "voice_id": voice_id,
            "text": text,
            "language_code": SARVAM_LANGUAGE[lang],
            "output_audio_codec": "wav",
            "speech_sample_rate": str(sample_rate),
        }
        async with httpx.AsyncClient(timeout=RENDER_TIMEOUT_S, transport=transport) as client:
            res = await client.post(
                CLONE_REST_URL,
                headers={"api-subscription-key": api_key},
                files={name: (None, value) for name, value in form.items()},
            )
        res.raise_for_status()
        body = res.json()
        audio_b64 = body.get("audio_b64") or body.get("audio")
        if not isinstance(audio_b64, str):
            raise ValueError("no audio in clone response")
        return wav_to_pcm(base64.b64decode(audio_b64), sample_rate)

    return render
