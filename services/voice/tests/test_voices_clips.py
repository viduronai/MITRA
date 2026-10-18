"""Voice table, Sarvam provider wiring (no network) and back-channel clip pre-rendering."""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

import numpy as np
from pipecat.services.sarvam.stt import SarvamSTTService
from pipecat.services.sarvam.tts import SarvamTTSService, SarvamTTSSpeakerV3
from pipecat.transcriptions.language import Language

from mitra_human.backchannel import TOKENS
from mitra_voice.config import Settings
from mitra_voice.pack import FIXTURES_DIR, Lang, load_fixture
from mitra_voice.providers import make_prerendered, make_stt, make_tts, resolve_providers
from mitra_voice.providers.clips import (
    GAIN,
    BackchannelClips,
    PhraseCache,
    ToneClips,
    shape_clip,
)
from mitra_voice.voices import STOCK_BY_ID, STOCK_VOICES, voice_for

CORE_CATALOG_IDS = {
    "priya-te-hyd",
    "arjun-te-vij",
    "lakshmi-te-sig",
    "ananya-hi-del",
    "rohan-hi-mum",
    "meera-hi-sig",
    "kavya-en-blr",
    "vikram-en-hyd",
}


def test_every_catalog_voice_maps_to_a_bulbul_v3_speaker() -> None:
    assert set(STOCK_BY_ID) == CORE_CATALOG_IDS
    speakers = {s.value for s in SarvamTTSSpeakerV3}
    for v in STOCK_VOICES:
        assert v.sarvam_speaker in speakers, v
    assert len({v.sarvam_speaker for v in STOCK_VOICES}) == len(
        STOCK_VOICES
    )  # each voice sounds distinct


def test_voice_fallback_by_gender() -> None:
    assert voice_for("rohan-hi-mum").sarvam_speaker == "rohan"
    assert voice_for("nope", "male").gender == "male"
    assert voice_for(None).gender == "female"


def _sarvam_settings(**extra: Any) -> Settings:
    return Settings(mitra_stt="sarvam", mitra_tts="sarvam", sarvam_api_key="test-key", **extra)  # type: ignore[arg-type]


def test_sarvam_services_use_codemix_autodetect_and_the_catalog_speaker() -> None:
    settings = _sarvam_settings()
    providers = resolve_providers(settings)
    pack = load_fixture(FIXTURES_DIR / "greenfield-realty.json")  # arjun-te-vij
    stt = make_stt(providers, settings, pack, "real_estate")
    assert isinstance(stt, SarvamSTTService)
    assert stt._settings.language == Language.TE_IN  # one Indic language: pinned
    multi = dataclasses.replace(pack, languages=["te", "hi", "en"])
    auto = make_stt(providers, settings, multi, "real_estate")
    assert auto._settings.language is None  # several Indic languages: auto-detect
    tts = make_tts(providers, settings, pack)
    assert isinstance(tts, SarvamTTSService)
    assert tts._settings.voice == "aditya"
    assert tts._settings.min_buffer_size == 30
    override = make_tts(providers, _sarvam_settings(mitra_tts_voice="kabir"), pack)
    assert override._settings.voice == "kabir"


def test_prerendered_audio_follows_the_tts_provider() -> None:
    pack = load_fixture(FIXTURES_DIR / "sunrise-clinic.json")
    mock = Settings()
    mock_pre = make_prerendered(resolve_providers(mock), mock, pack, 24000)
    assert isinstance(mock_pre.backchannels, ToneClips)
    assert mock_pre.phrases is None
    real = _sarvam_settings()
    real_pre = make_prerendered(resolve_providers(real), real, pack, 24000)
    assert isinstance(real_pre.backchannels, BackchannelClips)
    assert isinstance(real_pre.phrases, PhraseCache)


def _speechy(seconds: float, rate: int = 24000) -> bytes:
    t = np.arange(int(seconds * rate)) / rate
    voiced = (0.5 * np.sin(2 * np.pi * 200 * t) * 32767).astype("<i2")
    pad = np.zeros(rate // 5, dtype="<i2")  # 200 ms silence each side
    return bytes(np.concatenate([pad, voiced, pad]).tobytes())


def test_shape_clip_trims_caps_and_attenuates() -> None:
    shaped = np.frombuffer(shape_clip(_speechy(0.4), 24000), dtype="<i2")
    assert len(shaped) <= int(0.41 * 24000)
    assert np.abs(shaped).max() <= int(0.5 * 32767 * GAIN) + 1
    long_clip = shape_clip(_speechy(3.0), 24000)
    assert len(long_clip) <= int(0.9 * 24000) * 2


def _pcm_files(path: Path) -> int:
    return len(list(path.glob("*.pcm")))


async def test_prerender_renders_each_token_once_then_uses_the_disk_cache(tmp_path: Path) -> None:
    calls: list[tuple[str, Lang]] = []

    async def renderer(token: str, lang: Lang) -> bytes:
        calls.append((token, lang))
        return _speechy(0.3)

    def bc_clips(voice_key: str) -> BackchannelClips:
        cache = PhraseCache(
            renderer, voice_key=voice_key, sample_rate=24000, shaper=shape_clip, cache_dir=tmp_path
        )
        return BackchannelClips(cache)

    clips = bc_clips("test-a")
    assert clips.clip("te", TOKENS["te"][0]) is None
    billed: list[int] = []
    assert await clips.prerender(["te", "en", "te"], billed.append) == 6
    assert sum(billed) == sum(len(t) for lang in ("te", "en") for t in TOKENS[lang])
    assert len(calls) == 6
    assert all(clips.clip(lang, tok) for lang in ("te", "en") for tok in TOKENS[lang])
    assert _pcm_files(tmp_path) == 6

    PhraseCache._memory.clear()  # a new process: memory empty, disk warm
    again = bc_clips("test-a")
    assert await again.prerender(["te", "en"]) == 0
    assert len(calls) == 6
    assert again.clip("en", "okay") is not None
    # Another voice (e.g. a team clone) gets its own clips: rendered again, in that voice.
    assert await bc_clips("clone-svc-team").prerender(["en"]) == 3
    assert len(calls) == 9


async def test_render_failure_leaves_no_clip(tmp_path: Path) -> None:
    async def broken(token: str, lang: Lang) -> bytes:
        raise TimeoutError

    clips = BackchannelClips(
        PhraseCache(broken, voice_key="test-b", sample_rate=24000, cache_dir=tmp_path)
    )
    assert await clips.prerender(["hi"]) == 0
    assert clips.clip("hi", TOKENS["hi"][0]) is None


async def test_buffered_sarvam_stt_batches_audio_off_the_audio_path() -> None:
    from mitra_voice.providers.sarvam_stt import BufferedSarvamSTTService

    stt = BufferedSarvamSTTService(api_key="test-key", mode="codemix")
    stt._sample_rate = 16000  # normally set at StartFrame; no socket is opened here
    stt._speaking = True  # within a VAD speech segment
    frame_20ms = bytes(640)
    for _ in range(4):
        assert [f async for f in stt.run_stt(frame_20ms)] == [None]
    assert stt._queue.empty()  # 80 ms buffered, nothing sent yet
    assert [f async for f in stt.run_stt(frame_20ms)] == [None]
    assert stt._queue.qsize() == 1  # one 100 ms chunk queued for the sender task
    assert len(stt._queue.get_nowait()) == 3200
