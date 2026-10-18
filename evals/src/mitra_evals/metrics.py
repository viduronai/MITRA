"""Metric definitions for runs and the voice bake-off (TRD §12-13, §16; PRD §8).

All latencies are milliseconds measured from the caller's end of speech (VAD end-of-turn) to
the event. Percentiles use linear interpolation between closest ranks (numpy's default).

=========================  ==================================================================
Metric                     Definition
=========================  ==================================================================
first-audio latency        p50/p95 of ``first_audio_ms`` over all agent replies (not the
                           greeting). Target p95 <= 800 ms (TRD §12). Text-mode runs fall
                           back to ``response_ms`` (wall-clock to the full reply) and say so.
early hang-up rate         Live calls: share of connected calls the *caller* ended within
                           10 s of connect (PRD §8 target <= 8%).
early hang-up proxy        Offline: share of simulated calls with a hang-up risk in the first
                           10 s: greeting longer than ~10 s of speech (> 30 words), or the
                           greeting or first reply arriving later than 1.5 s.
task success               Share of scenarios whose ``task`` checks all pass (facts mentioned,
                           required actions taken, every caller turn answered).
wrong-fact rate            Ungrounded ₹ amounts / all ₹ amounts the agent said (amounts not in
                           the pack and not said by the caller).
interruption handling      Mean over barge-in turns of: addressed the new utterance (the
                           checks scoped to that turn pass), stayed brief (<= 2 sentences),
                           and, with audio timings, TTS stopped fast (1.0 at <= 200 ms, linear
                           to 0.0 at 1,000 ms). 0..1, higher is better.
WER                        Word error rate: word-level Levenshtein distance / reference words,
                           after :func:`mitra_evals.text.words` (normalised, punctuation dropped).
MOS                        Mean of 1-5 naturalness ratings with a 95% normal-approx interval.
=========================  ==================================================================
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Literal

from mitra_evals.results import ScenarioResult, TranscriptTurn
from mitra_evals.text import sentence_count, words

BARGE_IN_TARGET_MS = 200.0
BARGE_IN_ZERO_MS = 1000.0
EARLY_HANGUP_WINDOW_S = 10.0
HANGUP_RISK_LATENCY_MS = 1500.0
HANGUP_RISK_GREETING_WORDS = 30


def percentile(values: Sequence[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    pos = (len(ordered) - 1) * q / 100
    lo, hi = math.floor(pos), math.ceil(pos)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo)


@dataclass(frozen=True, slots=True)
class LatencyStats:
    count: int
    p50: float | None
    p95: float | None
    source: Literal["first_audio_ms", "response_ms", "none"]


def first_audio_latency(turns: Iterable[TranscriptTurn]) -> LatencyStats:
    replies = [t for t in turns if t.speaker == "agent" and t.caller_turn is not None]
    audio = [t.first_audio_ms for t in replies if t.first_audio_ms is not None]
    if audio:
        return LatencyStats(
            len(audio), percentile(audio, 50), percentile(audio, 95), "first_audio_ms"
        )
    wall = [t.response_ms for t in replies if t.response_ms is not None]
    if wall:
        return LatencyStats(len(wall), percentile(wall, 50), percentile(wall, 95), "response_ms")
    return LatencyStats(0, None, None, "none")


@dataclass(frozen=True, slots=True)
class CallRecord:
    """A live call as the voice plane logs it."""

    connected: bool
    duration_s: float
    ended_by: Literal["caller", "agent", "system"]


def early_hangup_rate(calls: Iterable[CallRecord]) -> float | None:
    connected = [c for c in calls if c.connected]
    if not connected:
        return None
    early = [
        c for c in connected if c.ended_by == "caller" and c.duration_s < EARLY_HANGUP_WINDOW_S
    ]
    return len(early) / len(connected)


def _latency(turn: TranscriptTurn) -> float | None:
    return turn.first_audio_ms if turn.first_audio_ms is not None else turn.response_ms


def hangup_risk(transcript: list[TranscriptTurn]) -> bool:
    agent = [t for t in transcript if t.speaker == "agent"]
    if not agent:
        return True
    greeting = next((t for t in agent if t.caller_turn is None), None)
    first_reply = next((t for t in agent if t.caller_turn is not None), None)
    if greeting is None or len(greeting.text.split()) > HANGUP_RISK_GREETING_WORDS:
        return True
    return any(
        (ms := _latency(t)) is not None and ms > HANGUP_RISK_LATENCY_MS
        for t in (greeting, first_reply)
        if t is not None
    )


def early_hangup_proxy(results: Sequence[ScenarioResult]) -> float | None:
    if not results:
        return None
    return sum(hangup_risk(r.transcript) for r in results) / len(results)


def task_success_rate(results: Sequence[ScenarioResult]) -> float | None:
    return sum(r.task_success for r in results) / len(results) if results else None


def wrong_fact_rate(wrong: int, total: int) -> float | None:
    return wrong / total if total else None


def _stop_score(ms: float) -> float:
    if ms <= BARGE_IN_TARGET_MS:
        return 1.0
    return max(0.0, 1 - (ms - BARGE_IN_TARGET_MS) / (BARGE_IN_ZERO_MS - BARGE_IN_TARGET_MS))


def interruption_score(results: Sequence[ScenarioResult]) -> float | None:
    events: list[float] = []
    for r in results:
        interrupts = {t.caller_turn for t in r.transcript if t.speaker == "caller" and t.interrupt}
        for i in interrupts:
            reply = next(
                (t for t in r.transcript if t.speaker == "agent" and t.caller_turn == i), None
            )
            if reply is None:
                events.append(0.0)
                continue
            scoped = [c for c in r.checks if c.turn == i]
            parts = [
                float(all(c.passed for c in scoped)) if scoped else float(bool(reply.text.strip())),
                float(sentence_count(reply.text) <= 2),
            ]
            if reply.tts_stop_ms is not None:
                parts.append(_stop_score(reply.tts_stop_ms))
            events.append(sum(parts) / len(parts))
    return sum(events) / len(events) if events else None


def wer(reference: str, hypothesis: str) -> float:
    ref, hyp = words(reference), words(hypothesis)
    if not ref:
        return 0.0 if not hyp else 1.0
    prev = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        cur = [i]
        for j, h in enumerate(hyp, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (r != h)))
        prev = cur
    return prev[-1] / len(ref)


def corpus_wer(pairs: Iterable[tuple[str, str]]) -> float | None:
    """Errors summed over the corpus / reference words summed (not a mean of per-clip WER)."""
    errors = total = 0.0
    for ref, hyp in pairs:
        n = len(words(ref))
        errors += wer(ref, hyp) * n
        total += n
    return errors / total if total else None


@dataclass(frozen=True, slots=True)
class MeanOpinion:
    mean: float
    ci95: float
    n: int


def mos(ratings: Sequence[int]) -> MeanOpinion | None:
    if not ratings:
        return None
    if any(not 1 <= r <= 5 for r in ratings):
        raise ValueError("MOS ratings must be 1..5")
    n = len(ratings)
    mean = sum(ratings) / n
    sd = math.sqrt(sum((r - mean) ** 2 for r in ratings) / (n - 1)) if n > 1 else 0.0
    return MeanOpinion(mean, 1.96 * sd / math.sqrt(n), n)


@dataclass(frozen=True, slots=True)
class BakeoffRow:
    """One row of ``bakeoff.md``: a full STT x TTS x LLM x transport combination."""

    stt: str
    tts: str
    llm: str
    transport: str
    latency: LatencyStats
    wer_te: float | None
    wer_hi: float | None
    naturalness: MeanOpinion | None
    cost_inr_per_min: float | None

    def markdown(self) -> str:
        def ms(v: float | None) -> str:
            return "-" if v is None else f"{v:.0f}"

        def pct(v: float | None) -> str:
            return "-" if v is None else f"{v:.1%}"

        nat = (
            "-"
            if self.naturalness is None
            else (
                f"{self.naturalness.mean:.2f} ± {self.naturalness.ci95:.2f} "
                f"(n={self.naturalness.n})"
            )
        )
        cost = "-" if self.cost_inr_per_min is None else f"₹{self.cost_inr_per_min:.2f}"
        cells = [
            self.stt,
            self.tts,
            self.llm,
            self.transport,
            ms(self.latency.p50),
            ms(self.latency.p95),
            pct(self.wer_te),
            pct(self.wer_hi),
            nat,
            cost,
        ]
        return "| " + " | ".join(cells) + " |"
