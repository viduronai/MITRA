"""Optional LLM judge for the rubric items. Off unless ``ANTHROPIC_API_KEY`` and
``MITRA_JUDGE_MODEL`` are both set and the ``anthropic`` package is installed (extra
``judge``). Judge scores are reported next to, never instead of, the deterministic checks."""

from __future__ import annotations

import json
import os
from typing import Any

from pydantic import BaseModel

from mitra_evals.results import JudgeResult, JudgeScore, TranscriptTurn
from mitra_evals.schema import EmployeePack, Scenario

RUBRIC: dict[str, str] = {
    "politeness": "Warm and respectful throughout (honorifics such as andi/garu/ji where a "
    "local receptionist would use them); never curt, pushy or salesy after a 'no'.",
    "natural_phrasing": "Sounds like a real Indian front-desk person on the phone in the "
    "caller's language or code-mix; spoken register, not a literal translation of English.",
    "grounded": "Every price, timing, name and availability claim comes from the facts pack; "
    "anything not in the pack is deferred (check and call/WhatsApp back), never invented.",
    "brevity": "Each reply is at most two short sentences and phone-friendly; one question "
    "at a time.",
    "persona_handling": "Adapts to the caller: patient repetition for elderly callers, crisp "
    "for impatient ones, drops the old thread after an interruption, confirms key details "
    "on a noisy line.",
}

_SYSTEM = (
    "You grade phone conversations between Mitra, an AI employee of an Indian small "
    "business, and a caller. Callers speak English, Hindi, Telugu or code-mixed Hinglish / "
    "Tenglish. Score each requested rubric item from 1 (unacceptable) to 5 (as good as a "
    "skilled human receptionist), with a one-sentence reason that quotes the agent. Grade "
    "only what the agent said. Rubric:\n" + "\n".join(f"- {k}: {v}" for k, v in RUBRIC.items())
)


class _Verdict(BaseModel):
    scores: list[JudgeScore]
    summary: str


def judge_model() -> str | None:
    """The judge model id from the environment, or None when judging is off."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    return os.environ.get("MITRA_JUDGE_MODEL") or None


def _prompt(scenario: Scenario, pack: EmployeePack, transcript: list[TranscriptTurn]) -> str:
    facts = {f.label: f.value for f in pack.facts}
    lines = [
        f"{'AGENT' if t.speaker == 'agent' else 'CALLER'}"
        f"{' (interrupting)' if t.interrupt else ''}: {t.text}"
        + (f"  [actions: {', '.join(a.name for a in t.actions)}]" if t.actions else "")
        for t in transcript
    ]
    return (
        f"Business: {pack.business_name} ({pack.industry}, {pack.city}).\n"
        f"Facts pack: {json.dumps(facts, ensure_ascii=False)}\n"
        f"Not in the pack (must be deferred): {', '.join(pack.missing_facts)}\n"
        f"Scenario: {scenario.title}; caller language {scenario.language}; persona "
        f"{scenario.persona}.\n"
        + (f"Notes for the grader: {scenario.rubric_notes}\n" if scenario.rubric_notes else "")
        + f"Score these items only: {', '.join(scenario.rubric)}.\n\nTranscript:\n"
        + "\n".join(lines)
    )


class Judge:
    def __init__(self, model: str, client: Any | None = None) -> None:
        if client is None:
            import anthropic  # optional dependency (extra "judge")

            client = anthropic.AsyncAnthropic()
        self.model, self._client = model, client

    async def __call__(
        self, scenario: Scenario, pack: EmployeePack, transcript: list[TranscriptTurn]
    ) -> JudgeResult:
        try:
            response = await self._client.messages.parse(
                model=self.model,
                max_tokens=4000,
                system=_SYSTEM,
                messages=[{"role": "user", "content": _prompt(scenario, pack, transcript)}],
                output_format=_Verdict,
            )
        except Exception as exc:  # a judge failure must not fail the run
            return JudgeResult(error=f"{type(exc).__name__}: {exc}")
        if response.stop_reason == "refusal" or response.parsed_output is None:
            return JudgeResult(error=f"no verdict (stop_reason={response.stop_reason})")
        verdict: _Verdict = response.parsed_output
        wanted = set(scenario.rubric)
        return JudgeResult(
            scores=[s for s in verdict.scores if s.item in wanted], summary=verdict.summary
        )
