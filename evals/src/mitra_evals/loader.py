"""Loads and cross-validates golden sets (``sets/*.yaml``) and packs (``fixtures/*.json``)."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

import yaml

from mitra_evals.schema import EmployeePack, Scenario, ScenarioSet

ROOT = Path(os.environ.get("MITRA_EVALS_ROOT") or Path(__file__).resolve().parents[2])


@dataclass(frozen=True, slots=True)
class Suite:
    sets: dict[str, ScenarioSet]
    packs: dict[str, EmployeePack]

    def scenarios(self) -> list[tuple[str, Scenario]]:
        return [(name, s) for name, st in self.sets.items() for s in st.scenarios]

    def select(self, selector: str) -> list[tuple[str, Scenario]]:
        """``all``, an industry (``clinic``/``real_estate``), set names, or scenario ids;
        comma-separated values are unioned."""
        wanted = {part.strip() for part in selector.split(",") if part.strip()}
        unknown = wanted - {"all", "clinic", "real_estate"} - set(self.sets)
        unknown -= {s.id for _, s in self.scenarios()}
        if unknown:
            raise ValueError(f"unknown set or scenario: {sorted(unknown)}")
        return [
            (name, s)
            for name, s in self.scenarios()
            if "all" in wanted or name in wanted or s.industry in wanted or s.id in wanted
        ]


def load_pack(path: Path) -> EmployeePack:
    return EmployeePack.model_validate(json.loads(path.read_text(encoding="utf-8")))


def load_set(path: Path) -> ScenarioSet:
    return ScenarioSet.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def cross_check(suite: Suite) -> list[str]:
    """Problems the per-file schema cannot see: dangling pack/fact refs, industry mismatch,
    duplicate ids across sets."""
    problems: list[str] = []
    seen: dict[str, str] = {}
    for name, s in suite.scenarios():
        if s.id in seen:
            problems.append(f"{s.id}: duplicated in {seen[s.id]} and {name}")
        seen[s.id] = name
        pack = suite.packs.get(s.pack)
        if pack is None:
            problems.append(f"{s.id}: unknown pack {s.pack!r}")
            continue
        if pack.industry != s.industry:
            problems.append(f"{s.id}: industry {s.industry} but pack is {pack.industry}")
        for m in s.assertions.must_mention:
            if m.fact is not None and pack.fact(m.fact) is None:
                problems.append(f"{s.id}: must_mention refers to unknown fact {m.fact!r}")
    return problems


def load_suite(root: Path = ROOT) -> Suite:
    packs = {p.id: p for p in (load_pack(f) for f in sorted((root / "fixtures").glob("*.json")))}
    sets = {f.stem: load_set(f) for f in sorted((root / "sets").glob("*.yaml"))}
    suite = Suite(sets=sets, packs=packs)
    problems = cross_check(suite)
    if problems:
        raise ValueError("invalid golden sets:\n  " + "\n  ".join(problems))
    return suite
