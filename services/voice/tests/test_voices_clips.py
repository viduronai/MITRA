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
from mitra_voice.providers import make_clips, make_stt, make_tts, resolve_providers
from mitra_voice.providers.clips import GAIN, PrerenderedClips, ToneClips, shape_clip
from mitra_voice.voices import VOICES, VOICES_BY_ID, voice_for

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
    assert set(VOICES_BY_ID) == CORE_CATALOG_IDS
    speakers = {s.value for s in SarvamTTSSpeakerV3}
    for v in VOICES:
        assert v.sarvam_speaker in speakers, v
    assert len({v.sarvam_speaker for v in VOICES}) == len(VOICES)  # each voice sounds distinct


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


def test_clip_source_follows_the_tts_provider() -> None:
    pack = load_fixture(FIXTURES_DIR / "sunrise-clinic.json")
    mock = Settings()
    assert isinstance(make_clips(resolve_providers(mock), mock, pack, 24000), ToneClips)
    real = _sarvam_settings()
    assert isinstance(make_clips(resolve_providers(real), real, pack, 24000), PrerenderedClips)


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

    clips = PrerenderedClips(renderer, voice_key="test-a", sample_rate=24000, cache_dir=tmp_path)
    assert clips.clip("te", TOKENS["te"][0]) is None
    assert await clips.prerender(["te", "en", "te"]) == 6
    assert len(calls) == 6
    assert all(clips.clip(lang, tok) for lang in ("te", "en") for tok in TOKENS[lang])
    assert _pcm_files(tmp_path) == 6

    PrerenderedClips._memory.clear()  # a new process: memory empty, disk warm
    again = PrerenderedClips(renderer, voice_key="test-a", sample_rate=24000, cache_dir=tmp_path)
    assert await again.prerender(["te", "en"]) == 0
    assert len(calls) == 6
    assert again.clip("en", "okay") is not None


async def test_render_failure_leaves_no_clip(tmp_path: Path) -> None:
    async def broken(token: str, lang: Lang) -> bytes:
        raise TimeoutError

    clips = PrerenderedClips(broken, voice_key="test-b", sample_rate=24000, cache_dir=tmp_path)
    assert await clips.prerender(["hi"]) == 0
    assert clips.clip("hi", TOKENS["hi"][0]) is None


async def test_buffered_sarvam_stt_batches_audio_off_the_audio_path() -> None:
    from mitra_voice.providers.sarvam_stt import BufferedSarvamSTTService

    stt = BufferedSarvamSTTService(api_key="test-key", mode="codemix")
    stt._sample_rate = 16000  # normally set at StartFrame; no socket is opened here
    frame_20ms = bytes(640)
    for _ in range(4):
        assert [f async for f in stt.run_stt(frame_20ms)] == [None]
    assert stt._queue.empty()  # 80 ms buffered, nothing sent yet
    assert [f async for f in stt.run_stt(frame_20ms)] == [None]
    assert stt._queue.qsize() == 1  # one 100 ms chunk queued for the sender task
    assert len(stt._queue.get_nowait()) == 3200
