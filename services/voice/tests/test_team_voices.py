"""Team voices (consented Sarvam clones), clone TTS wiring, phrase cache playback and usage."""

from __future__ import annotations

import base64
import dataclasses
import io
import json
import wave
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from pipecat.frames.frames import OutputAudioRawFrame, TTSSpeakFrame
from pipecat.tests.utils import run_test
from pipecat.transcriptions.language import Language

from mitra_voice.call_context import CallContext
from mitra_voice.config import Settings
from mitra_voice.pack import FIXTURES_DIR, Lang, load_fixture
from mitra_voice.processors.phrases import CachedPhrasePlayer
from mitra_voice.providers import call_voice, make_prerendered, make_tts, resolve_providers
from mitra_voice.providers.clips import PhraseCache, clone_renderer
from mitra_voice.providers.sarvam_stt import BufferedSarvamSTTService
from mitra_voice.providers.sarvam_tts import (
    CLONE_WS_URL,
    MeteredSarvamTTSService,
    SarvamCloneTTSService,
)
from mitra_voice.usage import UsageMeter
from mitra_voice.voices import (
    VoiceConfigError,
    load_registry,
    parse_registry,
    voice_registry,
)

SVC = "svc-123e4567-e89b-12d3-a456-426614174000"
CLINIC = load_fixture(FIXTURES_DIR / "sunrise-clinic.json")  # voice priya-te-hyd


def _consent(**overrides: Any) -> dict[str, Any]:
    base = {
        "person": "Priya K",
        "date": "2026-10-01",
        "scope": "Mitra AI voice employee for business calls; revocable.",
        "evidence": "consent-forms/priya-k.pdf",
    }
    return {**base, **overrides}


def _entry(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "team-priya-k",
        "name": "Priya K",
        "gender": "female",
        "languages": ["te", "en"],
        "sarvam_voice_id": SVC,
        "replaces": "priya-te-hyd",
        "consent": _consent(),
    }
    return {**base, **overrides}


def _registry(*entries: dict[str, Any]) -> Any:
    return parse_registry({"team_voices": list(entries)})


# --- consent gate -------------------------------------------------------------------------------


def test_a_consented_team_voice_loads() -> None:
    registry = _registry(_entry())
    voice = registry.team["team-priya-k"]
    assert voice.kind == "team"
    assert voice.sarvam_voice_id == SVC
    assert voice.consent is not None
    assert voice.consent.person == "Priya K"
    assert registry.refused == []


@pytest.mark.parametrize(
    ("entry", "reason"),
    [
        (_entry(consent=None), "no consent record"),
        (_entry(consent=_consent(revoked=True)), "consent revoked"),
        (_entry(consent=_consent(person="")), "consent.person"),
        (_entry(consent=_consent(scope="calls")), "consent.scope"),
        (_entry(consent=_consent(evidence="")), "consent.evidence"),
        (
            _entry(
                consent=_consent(date=(datetime.now(UTC).date() + timedelta(days=2)).isoformat())
            ),
            "in the future",
        ),
        (_entry(sarvam_voice_id="priya"), "sarvam_voice_id"),
        (_entry(replaces="nobody-xx"), "unknown voice"),
        (_entry(id="kavya-en-blr"), "collides"),
        (_entry(consent={**_consent(), "phone": "9876543210"}), "consent.phone"),  # no extras
    ],
)
def test_entries_without_valid_consent_are_refused(entry: dict[str, Any], reason: str) -> None:
    registry = _registry(entry)
    assert registry.team == {}
    assert len(registry.refused) == 1
    assert reason in registry.refused[0]


def test_one_bad_entry_does_not_block_the_good_ones() -> None:
    good = _entry()
    bad = _entry(id="team-ravi", replaces=None, consent=None)
    registry = _registry(good, bad, good)
    assert list(registry.team) == ["team-priya-k"]
    assert [r.split(":")[0] for r in registry.refused] == ["team-ravi", "team-priya-k"]  # dup


def test_mapping_shape_is_validated() -> None:
    with pytest.raises(VoiceConfigError):
        parse_registry([1, 2])


# --- resolution ---------------------------------------------------------------------------------


def test_resolution_prefers_team_voices() -> None:
    registry = _registry(_entry(), _entry(id="team-ravi", gender="male", replaces=None))
    assert registry.resolve("team-ravi").id == "team-ravi"  # core pack voice_id = team id
    assert registry.resolve("priya-te-hyd").id == "team-priya-k"  # catalog id replaced
    assert registry.resolve(None, "female").id == "team-priya-k"  # gender default replaced
    assert registry.resolve("rohan-hi-mum").sarvam_speaker == "rohan"  # stock untouched
    assert registry.resolve("unknown", "male").id == "arjun-te-vij"
    assert registry.get("team-ravi") is not None
    assert [v.kind for v in registry.all()][:2] == ["team", "team"]


def test_registry_loads_from_file_and_inline_env(tmp_path: Path) -> None:
    path = tmp_path / "voices.local.json"
    path.write_text(json.dumps({"team_voices": [_entry()]}), encoding="utf-8")
    assert "team-priya-k" in load_registry(path).team
    assert load_registry(tmp_path / "missing.json").team == {}
    inline = json.dumps({"team_voices": [_entry(id="team-inline")]})
    assert "team-inline" in load_registry(path, inline).team


def _team_settings(**extra: Any) -> Settings:
    return Settings(
        mitra_stt="sarvam",
        mitra_tts="sarvam",
        sarvam_api_key="test-key",  # type: ignore[arg-type]
        mitra_voices_json=json.dumps({"team_voices": [_entry()]}),
        **extra,
    )


# --- clone TTS wiring ---------------------------------------------------------------------------


def test_a_team_voice_speaks_through_the_clone_websocket() -> None:
    settings = _team_settings()
    assert voice_registry(settings).team  # loaded from MITRA_VOICES_JSON
    providers = resolve_providers(settings)
    assert call_voice(settings, CLINIC).id == "team-priya-k"
    tts = make_tts(providers, settings, CLINIC, UsageMeter())
    assert isinstance(tts, SarvamCloneTTSService)
    assert tts._websocket_url == f"{CLONE_WS_URL}?send_completion_event=true"
    tts._speech_sample_rate = "24000"
    config = tts.clone_config()
    assert config["voice_id"] == SVC
    assert config["target_language_code"] == Language.TE_IN
    assert config["output_audio_codec"] == "linear16"
    assert 50 <= config["max_chunk_length"] <= 500
    assert "speaker" not in config
    assert "model" not in config


def test_stock_voices_still_use_bulbul_speakers() -> None:
    settings = _team_settings()
    pack = dataclasses.replace(CLINIC, voice_id="rohan-hi-mum")
    tts = make_tts(resolve_providers(settings), settings, pack)
    assert type(tts) is MeteredSarvamTTSService
    assert tts._settings.voice == "rohan"


def test_clone_ids_are_checked() -> None:
    with pytest.raises(ValueError, match="svc-"):
        SarvamCloneTTSService(voice_id="priya", api_key="k")


def _wav(pcm: bytes, rate: int = 24000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


async def test_clone_renderer_posts_the_voice_id_and_decodes_audio() -> None:
    seen: list[httpx.Request] = []
    pcm = b"\x10\x27" * 2400  # 100 ms

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"audio_b64": base64.b64encode(_wav(pcm)).decode()})

    render = clone_renderer(
        "test-key", voice_id=SVC, sample_rate=24000, transport=httpx.MockTransport(handler)
    )
    assert await render("అవును", "te") == pcm
    request = seen[0]
    assert str(request.url) == "https://api.sarvam.ai/voices/clone"
    assert request.headers["api-subscription-key"] == "test-key"
    body = request.content.decode()
    assert "multipart/form-data" in request.headers["content-type"]
    for field in (
        'name="voice_id"',
        SVC,
        'name="language_code"',
        "te-IN",
        'name="output_audio_codec"',
    ):
        assert field in body
    assert "ref_audio" not in body  # only the saved, consented voice id is ever sent


def test_team_voice_phrases_render_with_the_clone() -> None:
    settings = _team_settings()
    pre = make_prerendered(resolve_providers(settings), settings, CLINIC, 24000)
    assert pre.phrases is not None
    assert pre.phrases._voice_key.startswith(f"clone-{SVC}")


# --- phrase cache playback + credit use --------------------------------------------------------


async def test_cached_phrases_play_without_tts(tmp_path: Path) -> None:
    async def renderer(text: str, lang: Lang) -> bytes:
        return b"\x00\x10" * 4800  # 200 ms

    cache = PhraseCache(renderer, voice_key="test-phr", sample_rate=24000, cache_dir=tmp_path)
    usage = UsageMeter()
    assert await cache.prerender([("te", "నమస్కారం")], on_render=usage.add_prerender) == 1
    assert usage.tts_chars_prerender == len("నమస్కారం")
    player = CachedPhrasePlayer(cache, CallContext(session_id="s", language="te"), usage, 24000)
    down, _ = await run_test(
        player, frames_to_send=[TTSSpeakFrame("నమస్కారం"), TTSSpeakFrame("not cached")]
    )
    audio = [f for f in down if isinstance(f, OutputAudioRawFrame)]
    assert sum(len(f.audio) for f in audio) == 9600
    assert [f.text for f in down if isinstance(f, TTSSpeakFrame)] == ["not cached"]  # live TTS
    assert usage.cache_hits == 1


def test_usage_meter_estimates_rupees() -> None:
    usage = UsageMeter()
    usage.add_tts_live(9000)
    usage.add_prerender(1000)
    usage.add_stt_audio(16000 * 2 * 120, 16000)  # 2 minutes of 16 kHz audio
    summary = usage.summary()
    assert summary["stt_seconds"] == 120.0
    assert summary["estimated_inr"] == pytest.approx(30 + 1)  # ₹30/10K chars + ₹30/h


async def test_stt_sends_only_speech_with_preroll() -> None:
    stt = BufferedSarvamSTTService(api_key="test-key", mode="codemix", usage=UsageMeter())
    stt._sample_rate = 16000
    frame = bytes(640)  # 20 ms
    for _ in range(100):  # 2 s of silence before the caller speaks
        [_ async for _ in stt.run_stt(frame)]
    assert stt._queue.empty()  # silence is not sent (billed per second)
    assert stt._preroll_bytes <= 32000  # only the last 1 s is kept
    stt.begin_speech()  # VAD start: the pre-roll goes out first
    assert stt._queue.qsize() == 1
    assert len(stt._queue.get_nowait()) == 32000  # 1 s of speech onset
    for _ in range(5):
        [_ async for _ in stt.run_stt(frame)]
    assert stt._queue.qsize() == 1  # then speech streams in 100 ms chunks


def test_the_example_mapping_is_valid() -> None:
    example = Path(__file__).resolve().parents[1] / "voices.example.json"
    registry = load_registry(example)
    assert registry.refused == []
    assert registry.team["team-priya-k"].replaces == "priya-te-hyd"
