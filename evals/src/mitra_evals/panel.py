"""Scores listener-panel answer files (``panel/index.html`` downloads) for PRD G1:
>= 70% of listeners cannot reliably tell Mitra from a human.

A listener "reliably tells" when their AI-identification accuracy is significantly above
chance: one-sided binomial test, p < 0.05, over the trials whose clips both played.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mitra_evals.metrics import MeanOpinion, mos

G1_TARGET = 0.70
ALPHA = 0.05


def binomial_tail(k: int, n: int, p: float = 0.5) -> float:
    """P(X >= k) for X ~ Binomial(n, p)."""
    return sum(math.comb(n, i) * p**i * (1 - p) ** (n - i) for i in range(k, n + 1))


@dataclass(frozen=True, slots=True)
class ListenerScore:
    listener: str
    trials: int
    correct: int
    p_value: float

    @property
    def reliably_tells(self) -> bool:
        return self.trials > 0 and self.p_value < ALPHA


@dataclass(frozen=True, slots=True)
class PanelSummary:
    listeners: list[ListenerScore]
    accuracy_by_language: dict[str, float]
    naturalness: dict[str, MeanOpinion | None]  # "mitra" / "human"
    skipped_missing: int

    @property
    def g1_rate(self) -> float | None:
        scored = [s for s in self.listeners if s.trials]
        return sum(not s.reliably_tells for s in scored) / len(scored) if scored else None

    @property
    def g1_pass(self) -> bool:
        rate = self.g1_rate
        return rate is not None and rate >= G1_TARGET


def summarise(files: Iterable[dict[str, Any]]) -> PanelSummary:
    listeners: list[ListenerScore] = []
    by_lang: dict[str, list[bool]] = defaultdict(list)
    ratings: dict[str, list[int]] = defaultdict(list)
    skipped = 0
    for data in files:
        answers = [a for a in data.get("answers", []) if not a.get("clip_missing")]
        skipped += len(data.get("answers", [])) - len(answers)
        correct = sum(bool(a.get("correct")) for a in answers)
        listeners.append(
            ListenerScore(
                listener=str(data.get("listener", {}).get("id", "?")),
                trials=len(answers),
                correct=correct,
                p_value=binomial_tail(correct, len(answers)) if answers else 1.0,
            )
        )
        for a in answers:
            by_lang[str(a.get("language"))].append(bool(a.get("correct")))
            for source, score in (a.get("naturalness_by_source") or {}).items():
                if isinstance(score, int):
                    ratings[source].append(score)
    return PanelSummary(
        listeners=listeners,
        accuracy_by_language={k: sum(v) / len(v) for k, v in sorted(by_lang.items())},
        naturalness={s: mos(ratings.get(s, [])) for s in ("mitra", "human")},
        skipped_missing=skipped,
    )


def load_files(paths: Iterable[Path]) -> list[dict[str, Any]]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in paths]


def render(summary: PanelSummary) -> str:
    lines = [f"{len(summary.listeners)} listeners"]
    for s in summary.listeners:
        verdict = "can tell" if s.reliably_tells else "cannot reliably tell"
        lines.append(
            f"  {s.listener}: {s.correct}/{s.trials} correct, p={s.p_value:.3f} ({verdict})"
        )
    rate = summary.g1_rate
    lines.append(
        "G1: "
        + ("no scored trials" if rate is None else f"{rate:.0%} cannot reliably tell")
        + f" (target >= {G1_TARGET:.0%}: {'PASS' if summary.g1_pass else 'FAIL'})"
    )
    for lang, acc in summary.accuracy_by_language.items():
        lines.append(f"  {lang}: AI identified in {acc:.0%} of trials (chance 50%)")
    for source, score in summary.naturalness.items():
        if score:
            lines.append(
                f"  naturalness {source}: {score.mean:.2f} ± {score.ci95:.2f} (n={score.n})"
            )
    if summary.skipped_missing:
        lines.append(f"  skipped {summary.skipped_missing} trials with missing clips")
    return "\n".join(lines)
