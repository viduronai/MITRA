from __future__ import annotations

import pytest

from mitra_evals import metrics
from mitra_evals.results import CheckResult, ScenarioResult, TranscriptTurn


def test_percentile() -> None:
    values = [100.0, 200.0, 300.0, 400.0, 500.0]
    assert metrics.percentile(values, 50) == 300
    assert metrics.percentile(values, 95) == pytest.approx(480)
    assert metrics.percentile([], 50) is None


def test_first_audio_latency_prefers_audio_timings() -> None:
    turns = [
        TranscriptTurn(speaker="agent", text="hi", response_ms=50),
        TranscriptTurn(
            speaker="agent", text="a", caller_turn=0, response_ms=10, first_audio_ms=600
        ),
        TranscriptTurn(
            speaker="agent", text="b", caller_turn=1, response_ms=10, first_audio_ms=900
        ),
    ]
    stats = metrics.first_audio_latency(turns)
    assert stats.source == "first_audio_ms"
    assert stats.count == 2
    assert stats.p50 == 750
    text_only = [t.model_copy(update={"first_audio_ms": None}) for t in turns]
    assert metrics.first_audio_latency(text_only).source == "response_ms"


def test_early_hangup_rate() -> None:
    calls = [
        metrics.CallRecord(connected=True, duration_s=4, ended_by="caller"),
        metrics.CallRecord(connected=True, duration_s=4, ended_by="agent"),
        metrics.CallRecord(connected=True, duration_s=60, ended_by="caller"),
        metrics.CallRecord(connected=False, duration_s=0, ended_by="system"),
    ]
    assert metrics.early_hangup_rate(calls) == pytest.approx(1 / 3)
    assert metrics.early_hangup_rate([]) is None


def test_hangup_risk() -> None:
    quick = [TranscriptTurn(speaker="agent", text="Hello, AI assistant here.", response_ms=300)]
    slow = [quick[0].model_copy(update={"response_ms": 2500})]
    wordy = [quick[0].model_copy(update={"text": "word " * 40})]
    assert not metrics.hangup_risk(quick)
    assert metrics.hangup_risk(slow)
    assert metrics.hangup_risk(wordy)
    assert metrics.hangup_risk([])


def _result(reply: str, *, passed: bool, tts_stop_ms: float | None = None) -> ScenarioResult:
    return ScenarioResult(
        id="x",
        title="x",
        set="x",
        industry="clinic",
        language="en",
        persona="interrupter",
        passed=passed,
        task_success=passed,
        checks=[CheckResult(name="must_mention", kind="task", label="x", passed=passed, turn=1)],
        transcript=[
            TranscriptTurn(speaker="agent", text="Hi"),
            TranscriptTurn(speaker="caller", text="a", caller_turn=0),
            TranscriptTurn(speaker="agent", text="long answer", caller_turn=0),
            TranscriptTurn(speaker="caller", text="wait!", caller_turn=1, interrupt=True),
            TranscriptTurn(speaker="agent", text=reply, caller_turn=1, tts_stop_ms=tts_stop_ms),
        ],
    )


def test_interruption_score() -> None:
    assert metrics.interruption_score([_result("Sunday 10 AM.", passed=True)]) == 1.0
    assert metrics.interruption_score([_result("A. B. C.", passed=False)]) == 0.0
    fast = _result("Sunday 10 AM.", passed=True, tts_stop_ms=150)
    slow = _result("Sunday 10 AM.", passed=True, tts_stop_ms=600)
    assert metrics.interruption_score([fast]) == 1.0
    assert metrics.interruption_score([slow]) == pytest.approx((1 + 1 + 0.5) / 3)
    assert metrics.interruption_score([]) is None


def test_wer() -> None:
    assert metrics.wer("ఫీజు ఎంత అండి", "ఫీజు ఎంత అండి") == 0
    assert metrics.wer("the fee is five hundred", "the fee is nine hundred") == 0.2
    assert metrics.wer("ఫీజు ఎంత అండి?", "ఫీజు ఎంతో అండి") == pytest.approx(1 / 3)
    assert metrics.wer("a b", "") == 1.0
    assert metrics.corpus_wer([("a b c d", "a b c d"), ("a b", "a x")]) == pytest.approx(1 / 6)


def test_mos() -> None:
    score = metrics.mos([4, 4, 5, 3])
    assert score is not None
    assert score.mean == 4
    assert score.n == 4
    assert score.ci95 > 0
    assert metrics.mos([]) is None
    with pytest.raises(ValueError, match=r"1\.\.5"):
        metrics.mos([6])


def test_bakeoff_row_markdown() -> None:
    row = metrics.BakeoffRow(
        stt="stt-a",
        tts="tts-b",
        llm="llm-c",
        transport="pstn",
        latency=metrics.LatencyStats(10, 610, 790, "first_audio_ms"),
        wer_te=0.142,
        wer_hi=None,
        naturalness=metrics.MeanOpinion(4.1, 0.2, 10),
        cost_inr_per_min=2.35,
    )
    line = row.markdown()
    assert line.startswith("| stt-a | tts-b | llm-c | pstn | 610 | 790 | 14.2% | - |")
    assert "₹2.35" in line
