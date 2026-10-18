"""Every golden set and pack validates, coverage meets the brief, and the gold reference replies
pass every deterministic check (so each assertion is satisfiable and no pattern is over-broad)."""

from __future__ import annotations

import asyncio
from collections import Counter
from pathlib import Path

import pytest

from mitra_evals.agents.reference import ReferenceAgent
from mitra_evals.loader import ROOT, Suite, cross_check, load_pack, load_set
from mitra_evals.runner import run_scenario
from mitra_evals.schema import Scenario

SET_FILES = sorted((ROOT / "sets").glob("*.yaml"))
PACK_FILES = sorted((ROOT / "fixtures").glob("*.json"))


@pytest.mark.parametrize("path", SET_FILES, ids=lambda p: p.stem)
def test_set_file_validates(path: Path) -> None:
    scenario_set = load_set(path)
    assert scenario_set.name == path.stem
    assert scenario_set.scenarios


@pytest.mark.parametrize("path", SET_FILES, ids=lambda p: p.stem)
def test_set_file_flags_native_review(path: Path) -> None:
    head = path.read_text(encoding="utf-8").splitlines()[0]
    assert head.startswith("# NATIVE REVIEW NEEDED")


@pytest.mark.parametrize("path", PACK_FILES, ids=lambda p: p.stem)
def test_pack_validates(path: Path) -> None:
    pack = load_pack(path)
    assert pack.id == path.stem
    assert pack.missing_facts


def test_cross_references(suite: Suite) -> None:
    assert cross_check(suite) == []


def test_coverage(suite: Suite) -> None:
    scenarios = [s for _, s in suite.scenarios()]
    assert len(scenarios) >= 60
    for industry in ("clinic", "real_estate"):
        mine = [s for s in scenarios if s.industry == industry]
        assert {s.language for s in mine} == {"en", "hi", "te", "te-en", "hi-en"}
        assert {s.persona for s in mine} >= {
            "elderly",
            "impatient",
            "noisy_street",
            "interrupter",
            "wants_human",
            "do_not_call",
        }
    tags = Counter(t for s in scenarios for t in s.tags)
    assert tags["emergency"] >= 4
    assert tags["medical_advice"] >= 4
    assert tags["missing_fact"] >= 6


def test_reference_replies_are_short(suite: Suite) -> None:
    from mitra_evals.text import sentence_count

    long = [
        (s.id, i)
        for _, s in suite.scenarios()
        for i, t in enumerate(s.turns)
        if sentence_count(t.reference) > 2
    ]
    assert long == []


ALL_IDS = [s.id for st in (load_set(p) for p in SET_FILES) for s in st.scenarios]


@pytest.mark.parametrize("scenario_id", ALL_IDS)
def test_reference_passes_all_checks(suite: Suite, scenario_id: str) -> None:
    set_name, scenario = next((n, s) for n, s in suite.scenarios() if s.id == scenario_id)
    agent = ReferenceAgent({scenario.id: scenario})
    result, (wrong, _) = asyncio.run(
        run_scenario(agent, set_name, scenario, suite.packs[scenario.pack])
    )
    failed = [(c.name, c.label, c.detail) for c in result.checks if not c.passed]
    assert failed == []
    assert result.passed
    assert wrong == 0


def test_every_scenario_exercises_its_assertions(suite: Suite) -> None:
    """A scenario with nothing scenario-specific to check is not a test."""

    def specific(s: Scenario) -> bool:
        a = s.assertions
        return bool(a.must_mention or a.must_not_say or a.required_actions)

    assert [s.id for _, s in suite.scenarios() if not specific(s)] == []
