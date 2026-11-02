"""End-to-end through the real pipeline (mock providers, fake transport, energy VAD)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

from pipecat.workers.runner import WorkerRunner

from mitra_voice.config import Settings
from mitra_voice.pack import FIXTURES_DIR, load_fixture
from mitra_voice.pipeline import CallPipeline, build_call_pipeline, greet
from mitra_voice.providers import resolve_providers
from mitra_voice.session import CallSession
from tests.fakes import EnergyVAD, FakeInput, FakeOutput, wait_for, wait_until_quiet


def _settings(**overrides: Any) -> Settings:
    base: dict[str, Any] = {
        "mock_llm_ttft_ms": 60,
        "mock_llm_token_ms": 5,
        "mock_tool_latency_ms": 0,
        "mock_tts_ttfb_ms": 20,
        "mock_tts_ms_per_char": 15,
    }
    return Settings(_env_file=None, **{**base, **overrides})  # type: ignore[call-arg]


@asynccontextmanager
async def running_call(
    settings: Settings,
) -> AsyncIterator[tuple[CallSession, CallPipeline, FakeInput, list[dict[str, Any]]]]:
    # The fake output is reachable as ``inp.peer`` for quiet-waits.
    session = CallSession(
        scenario="clinic",
        pack=load_fixture(FIXTURES_DIR / "sunrise-clinic.json"),
        providers=resolve_providers(settings),
    )
    sent: list[dict[str, Any]] = []
    session.send = sent.append
    inp, out = FakeInput(), FakeOutput()
    inp.peer = out
    call = build_call_pipeline(
        session, settings, transport_input=inp, transport_output=out, vad=EnergyVAD(), turn="vad"
    )
    started = asyncio.Event()

    @call.worker.event_handler("on_pipeline_started")
    async def _started(*_: object) -> None:
        started.set()

    runner = WorkerRunner(handle_sigint=False)
    await runner.add_workers(call.worker)
    run = asyncio.create_task(runner.run())
    try:
        await asyncio.wait_for(started.wait(), 10)
        yield session, call, inp, sent
    finally:
        await call.worker.cancel()
        await asyncio.wait_for(run, 10)


async def _speak(inp: FakeInput, seconds: float) -> None:
    inp.speaking = True
    await asyncio.sleep(seconds)
    inp.speaking = False


def _has(sent: list[dict[str, Any]], pred: Callable[[dict[str, Any]], bool]) -> bool:
    return any(pred(m) for m in sent)


async def test_greets_then_answers_fee_from_the_pack() -> None:
    async with running_call(_settings()) as (session, call, inp, sent):
        await greet(call, session)
        await wait_until_quiet(inp.peer)  # let the greeting play out (load-independent)
        await _speak(inp, 0.8)

        await wait_for(lambda: len(session.tracker.completed()) >= 1, within=10)
        await wait_for(lambda: len(session.transcript) >= 3, within=10)

    greeting, user, answer = session.transcript[:3]
    assert greeting.role == "assistant"
    assert "AI assistant" in greeting.text
    assert "Sunrise Clinic" in greeting.text
    assert user.role == "user"
    assert user.text == "Hi, what is the consultation fee?"
    assert answer.role == "assistant"
    assert answer.text == "The consultation fee is five hundred rupees."
    assert not answer.interrupted

    # The answer is in the LLM context exactly as spoken.
    assistant_msgs = [m for m in call.context.get_messages() if m.get("role") == "assistant"]
    assert assistant_msgs[-1]["content"] == answer.text

    turn = session.tracker.completed()[0]
    metrics = session.metrics()["turns"][0]
    assert turn.turn == 1
    for key in ("stt_ms", "turn_detect_ms", "llm_ttft_ms", "tts_ttfb_ms", "first_audio_ms"):
        assert metrics[key] is not None, (key, metrics)
    assert metrics["llm_ttft_ms"] >= 60, repr(sorted(metrics.items()))
    assert metrics["first_audio_ms"] > metrics["turn_detect_ms"]
    assert _has(sent, lambda m: m["type"] == "metrics")
    assert session.metrics()["summary"]["first_audio_ms"]["n"] == 1


async def test_barge_in_truncates_the_reply_to_what_was_heard() -> None:
    # Slow speech so the caller can cut in mid-sentence.
    async with running_call(_settings(mock_tts_ms_per_char=70)) as (session, call, inp, sent):
        await _speak(inp, 0.8)  # no greeting: go straight to the question
        await wait_for(lambda: _has(sent, lambda m: m["type"] == "assistant_delta"), within=10)
        await wait_for(lambda: call.reply.words_played >= 2, within=10)
        await _speak(inp, 0.6)  # barge in
        await wait_for(
            lambda: any(e.interrupted for e in session.transcript),
            within=10,
        )

    cut = next(e for e in session.transcript if e.interrupted)
    full = "The consultation fee is five hundred rupees."
    assert cut.text.endswith("…")
    assert full.startswith(cut.text.removesuffix("…"))
    assert cut.text != full
    # The context now holds only what the caller heard.
    contents = [m.get("content") for m in call.context.get_messages()]
    assert cut.text in contents
    assert full not in contents
    assert session.tracker.turns[0].interrupted
