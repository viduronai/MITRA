"""Result models: what a run produces and what ``report.json`` contains."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, computed_field

from mitra_evals.schema import Industry, Language, Persona

CheckKind = Literal["compliance", "task", "accuracy", "style"]


class ActionRecord(BaseModel):
    name: str
    args: dict[str, Any] = Field(default_factory=dict)


class TranscriptTurn(BaseModel):
    speaker: Literal["agent", "caller"]
    text: str
    # Caller turns: their index. Agent turns: the caller turn they answer (None = greeting).
    caller_turn: int | None = None
    interrupt: bool = False
    actions: list[ActionRecord] = Field(default_factory=list)
    end_call: bool = False
    response_ms: float | None = None
    first_audio_ms: float | None = None
    tts_stop_ms: float | None = None


class CheckResult(BaseModel):
    name: str
    kind: CheckKind
    label: str
    passed: bool
    detail: str = ""
    turn: int | None = None


class JudgeScore(BaseModel):
    item: str
    score: int = Field(ge=1, le=5)
    reason: str


class JudgeResult(BaseModel):
    scores: list[JudgeScore] = Field(default_factory=list)
    summary: str = ""
    error: str | None = None


class ScenarioResult(BaseModel):
    id: str
    title: str
    set: str
    industry: Industry
    language: Language
    persona: Persona
    passed: bool
    task_success: bool
    checks: list[CheckResult]
    transcript: list[TranscriptTurn]
    judge: JudgeResult | None = None
    error: str | None = None


class Rate(BaseModel):
    total: int = 0
    passed: int = 0

    @computed_field  # type: ignore[prop-decorator]
    @property
    def rate(self) -> float:
        return self.passed / self.total if self.total else 0.0

    def add(self, passed: bool) -> None:
        self.total += 1
        self.passed += int(passed)


class RunSummary(BaseModel):
    overall: Rate
    by_industry: dict[str, Rate]
    by_language: dict[str, Rate]
    by_persona: dict[str, Rate]
    by_check: dict[str, Rate]
    metrics: dict[str, float | None]
    judge_means: dict[str, float] = Field(default_factory=dict)


class RunReport(BaseModel):
    run_id: str
    created_at: str
    agent: str
    sets: list[str]
    judge_enabled: bool
    judge_model: str | None = None
    notes: list[str] = Field(default_factory=list)
    summary: RunSummary
    scenarios: list[ScenarioResult]
