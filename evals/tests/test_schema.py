from __future__ import annotations

import pytest
from pydantic import ValidationError

from mitra_evals.loader import Suite, cross_check
from mitra_evals.schema import Assertions, MentionCheck, PatternCheck, ScenarioSet, base_language
from tests.helpers import scenario


def test_minimal_scenario_gets_defaults() -> None:
    s = scenario()
    assert s.assertions.disclosure_in_first_turn
    assert s.assertions.max_sentences_per_turn == 2
    assert s.rubric == ["politeness", "natural_phrasing", "grounded", "brevity"]


def test_unknown_key_is_rejected() -> None:
    with pytest.raises(ValidationError):
        scenario(assertion={})


def test_mention_needs_exactly_one_source() -> None:
    with pytest.raises(ValidationError):
        MentionCheck(label="x")
    with pytest.raises(ValidationError):
        MentionCheck(label="x", fact="consultation_fee", any_of=["500"])
    assert MentionCheck(label="x", any_of=["500"]).any_of == ["500"]


def test_bad_regex_is_rejected() -> None:
    with pytest.raises(ValidationError):
        PatternCheck(label="x", pattern="(unclosed")


def test_action_cannot_be_required_and_forbidden() -> None:
    with pytest.raises(ValidationError):
        Assertions(required_actions=["book_slot"], forbidden_actions=["book_slot"])


def test_assertion_turn_must_exist() -> None:
    with pytest.raises(ValidationError):
        scenario(assertions={"must_mention": [{"label": "x", "any_of": ["a"], "turn": 3}]})


def test_persona_markers_are_required() -> None:
    with pytest.raises(ValidationError):
        scenario(persona="interrupter")
    with pytest.raises(ValidationError):
        scenario(persona="noisy_street")
    assert scenario(persona="noisy_street", audio={"noise": "street", "snr_db": 5}).audio


def test_unknown_language_and_action_are_rejected() -> None:
    with pytest.raises(ValidationError):
        scenario(language="ta")
    with pytest.raises(ValidationError):
        scenario(assertions={"required_actions": ["teleport"]})


def test_duplicate_ids_in_a_set() -> None:
    s = scenario().model_dump()
    with pytest.raises(ValidationError):
        ScenarioSet.model_validate({"name": "x", "description": "x", "scenarios": [s, s]})


def test_cross_check_finds_dangling_refs(suite: Suite) -> None:
    bad = scenario(
        id="t.bad",
        pack="skyline_homes",
        assertions={"must_mention": [{"label": "x", "fact": "no_such_fact"}]},
    )
    ghost = scenario(id="t.ghost", pack="no_such_pack")
    broken = Suite(
        sets={"x": ScenarioSet(name="x", description="x", scenarios=[bad, ghost])},
        packs=suite.packs,
    )
    problems = cross_check(broken)
    assert any("industry clinic but pack is real_estate" in p for p in problems)
    assert any("unknown fact 'no_such_fact'" in p for p in problems)
    assert any("unknown pack 'no_such_pack'" in p for p in problems)


def test_base_language() -> None:
    assert base_language("te-en") == "te"
    assert base_language("hi-en") == "hi"
    assert base_language("en") == "en"


def test_select(suite: Suite) -> None:
    assert len(suite.select("all")) == len(suite.scenarios())
    assert {s.industry for _, s in suite.select("real_estate")} == {"real_estate"}
    assert [s.id for _, s in suite.select("clinic.fee.en")] == ["clinic.fee.en"]
    with pytest.raises(ValueError, match="unknown set"):
        suite.select("nope")
