"""Runs selected scenarios against an agent under test and builds a :class:`RunReport`."""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from mitra_evals import metrics
from mitra_evals.agents import AgentReply, AgentUnderTest, CallContext
from mitra_evals.checks import run_checks, wrong_amounts
from mitra_evals.judge import Judge
from mitra_evals.loader import Suite
from mitra_evals.results import (
    ActionRecord,
    Rate,
    RunReport,
    RunSummary,
    ScenarioResult,
    TranscriptTurn,
)
from mitra_evals.schema import EmployeePack, Scenario


def _agent_turn(reply: AgentReply, caller_turn: int | None, elapsed_ms: float) -> TranscriptTurn:
    return TranscriptTurn(
        speaker="agent",
        text=reply.text,
        caller_turn=caller_turn,
        actions=[ActionRecord(name=a.name, args=a.args) for a in reply.actions],
        end_call=reply.end_call,
        response_ms=round(elapsed_ms, 1),
        first_audio_ms=reply.timings.first_audio_ms,
        tts_stop_ms=reply.timings.tts_stop_ms,
    )


async def _converse(
    agent: AgentUnderTest, scenario: Scenario, pack: EmployeePack
) -> tuple[list[TranscriptTurn], str | None]:
    transcript: list[TranscriptTurn] = []
    context = CallContext(
        scenario_id=scenario.id, language=scenario.language, direction=scenario.direction
    )
    try:
        session = await agent.open(pack, context)
    except Exception as exc:  # the adapter's failure is this scenario's failure
        return transcript, f"open failed: {type(exc).__name__}: {exc}"
    try:
        started = time.perf_counter()
        greeting = await session.start()
        transcript.append(_agent_turn(greeting, None, (time.perf_counter() - started) * 1000))
        for i, turn in enumerate(scenario.turns):
            if transcript[-1].end_call:
                break
            transcript.append(
                TranscriptTurn(
                    speaker="caller", text=turn.text, caller_turn=i, interrupt=turn.interrupt
                )
            )
            started = time.perf_counter()
            reply = await session.send(turn.text, interrupt=turn.interrupt)
            transcript.append(_agent_turn(reply, i, (time.perf_counter() - started) * 1000))
    except Exception as exc:
        return transcript, f"{type(exc).__name__}: {exc}"
    finally:
        await session.close()
    return transcript, None


async def run_scenario(
    agent: AgentUnderTest,
    set_name: str,
    scenario: Scenario,
    pack: EmployeePack,
    judge: Judge | None = None,
) -> tuple[ScenarioResult, tuple[int, int]]:
    transcript, error = await _converse(agent, scenario, pack)
    checks = run_checks(scenario, pack, transcript)
    verdict = await judge(scenario, pack, transcript) if judge and transcript else None
    result = ScenarioResult(
        id=scenario.id,
        title=scenario.title,
        set=set_name,
        industry=scenario.industry,
        language=scenario.language,
        persona=scenario.persona,
        passed=error is None and all(c.passed for c in checks),
        task_success=error is None and all(c.passed for c in checks if c.kind == "task"),
        checks=checks,
        transcript=transcript,
        judge=verdict,
        error=error,
    )
    return result, wrong_amounts(pack, transcript)


def summarise(results: Sequence[ScenarioResult], wrong: int, amounts: int) -> RunSummary:
    overall = Rate()
    by: dict[str, dict[str, Rate]] = {"industry": {}, "language": {}, "persona": {}, "check": {}}
    judge_scores: dict[str, list[int]] = {}
    for r in results:
        overall.add(r.passed)
        for dim, key in (
            ("industry", r.industry),
            ("language", r.language),
            ("persona", r.persona),
        ):
            by[dim].setdefault(key, Rate()).add(r.passed)
        for c in r.checks:
            by["check"].setdefault(c.name, Rate()).add(c.passed)
        for s in r.judge.scores if r.judge else []:
            judge_scores.setdefault(s.item, []).append(s.score)
    latency = metrics.first_audio_latency(t for r in results for t in r.transcript)
    return RunSummary(
        overall=overall,
        by_industry=dict(sorted(by["industry"].items())),
        by_language=dict(sorted(by["language"].items())),
        by_persona=dict(sorted(by["persona"].items())),
        by_check=dict(sorted(by["check"].items())),
        metrics={
            "task_success": metrics.task_success_rate(results),
            "wrong_fact_rate": metrics.wrong_fact_rate(wrong, amounts),
            "interruption_score": metrics.interruption_score(results),
            "early_hangup_proxy": metrics.early_hangup_proxy(results),
            f"latency_p50_ms ({latency.source})": latency.p50,
            f"latency_p95_ms ({latency.source})": latency.p95,
        },
        judge_means={k: round(sum(v) / len(v), 2) for k, v in sorted(judge_scores.items())},
    )


async def run_suite(
    agent: AgentUnderTest,
    suite: Suite,
    selected: Sequence[tuple[str, Scenario]],
    *,
    judge: Judge | None = None,
    concurrency: int = 4,
    notes: Sequence[str] = (),
) -> RunReport:
    gate = asyncio.Semaphore(max(1, concurrency))

    async def one(set_name: str, scenario: Scenario) -> tuple[ScenarioResult, tuple[int, int]]:
        async with gate:
            return await run_scenario(agent, set_name, scenario, suite.packs[scenario.pack], judge)

    outcomes = await asyncio.gather(*(one(n, s) for n, s in selected))
    results = [r for r, _ in outcomes]
    wrong = sum(w for _, (w, _t) in outcomes)
    amounts = sum(t for _, (_w, t) in outcomes)
    return RunReport(
        run_id=uuid.uuid4().hex[:12],
        created_at=datetime.now(UTC).isoformat(timespec="seconds"),
        agent=agent.name,
        sets=sorted({n for n, _ in selected}),
        judge_enabled=judge is not None,
        judge_model=judge.model if judge else None,
        notes=list(notes),
        summary=summarise(results, wrong, amounts),
        scenarios=results,
    )
