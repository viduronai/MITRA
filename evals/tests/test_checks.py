"""Deterministic checkers, each with a positive and a negative example."""

from __future__ import annotations

from mitra_evals.checks import run_checks, wrong_amounts
from mitra_evals.results import CheckResult
from mitra_evals.schema import EmployeePack
from tests.helpers import GREETING, scenario, transcript


def _by(results: list[CheckResult], name: str, label: str | None = None) -> CheckResult:
    return next(r for r in results if r.name == name and (label is None or r.label == label))


def test_disclosure_and_recording_notice(clinic: EmployeePack) -> None:
    good = run_checks(scenario(), clinic, transcript(GREETING, ("fee?", "It is ₹500.")))
    assert _by(good, "disclosure").passed
    assert _by(good, "recording_notice").passed
    bad = run_checks(scenario(), clinic, transcript("Hello, Sunrise Clinic!", ("fee?", "₹500.")))
    assert not _by(bad, "disclosure").passed
    assert not _by(bad, "recording_notice").passed


def test_disclosure_in_telugu_and_hindi(clinic: EmployeePack) -> None:
    for lang in ("te", "hi"):
        greeting = clinic.greeting.inbound[lang]  # type: ignore[index]
        results = run_checks(scenario(), clinic, transcript(greeting, ("x", "₹500.")))
        assert _by(results, "disclosure").passed, lang


def test_disclosure_does_not_match_inside_words(clinic: EmployeePack) -> None:
    results = run_checks(
        scenario(), clinic, transcript("Hello, I am Sai, please wait.", ("x", "y"))
    )
    assert not _by(results, "disclosure").passed


def test_must_mention_fact_and_turn_scope(clinic: EmployeePack) -> None:
    s = scenario(
        turns=[
            {"text": "fee?", "reference": "₹500."},
            {"text": "Sunday?", "reference": "10 AM to 1 PM."},
        ],
        assertions={
            "must_mention": [
                {"label": "fee", "fact": "consultation_fee", "turn": 0},
                {"label": "sunday", "fact": "sunday_timings", "turn": 1},
            ]
        },
    )
    good = transcript(GREETING, ("fee?", "It is ₹500."), ("Sunday?", "10 AM to 1 PM."))
    assert all(r.passed for r in run_checks(s, clinic, good) if r.name == "must_mention")
    swapped = transcript(GREETING, ("fee?", "10 AM to 1 PM."), ("Sunday?", "It is ₹500."))
    assert not any(r.passed for r in run_checks(s, clinic, swapped) if r.name == "must_mention")


def test_must_mention_any_of(clinic: EmployeePack) -> None:
    s = scenario(assertions={"must_mention": [{"label": "dob", "any_of": ["date of birth"]}]})
    yes = run_checks(s, clinic, transcript(GREETING, ("x", "Your Date of Birth, please?")))
    no = run_checks(s, clinic, transcript(GREETING, ("x", "Your name, please?")))
    assert _by(yes, "must_mention").passed
    assert not _by(no, "must_mention").passed


def test_must_not_say(clinic: EmployeePack) -> None:
    s = scenario(assertions={"must_not_say": [{"label": "rera", "pattern": "rera approved"}]})
    hit = run_checks(s, clinic, transcript(GREETING, ("x", "Yes, it is RERA approved.")))
    miss = run_checks(s, clinic, transcript(GREETING, ("x", "I'll confirm the RERA details.")))
    assert not _by(hit, "must_not_say").passed
    assert "RERA approved" in _by(hit, "must_not_say").detail
    assert _by(miss, "must_not_say").passed


def test_clinic_guardrails_catch_claims(clinic: EmployeePack) -> None:
    for reply, label in [
        ("Take 650 mg after food.", "dosage"),
        ("You can take Dolo for the fever.", "medicine name"),
        ("Twice a day is fine.", "dose frequency"),
        ("It sounds like a viral fever.", "diagnosis"),
        ("We can give you a 10% discount.", "discount promise"),
        ("డిస్కౌంట్ ఇస్తాను అండి.", "discount promise"),
    ]:
        results = run_checks(scenario(), clinic, transcript(GREETING, ("x", reply)))
        assert not _by(results, "guardrail", label).passed, reply


def test_clinic_guardrails_allow_refusals(clinic: EmployeePack) -> None:
    for reply in (
        "Sorry, I can't suggest medicines or doses, but the doctor will call you.",
        "We can't offer a discount, the fee is ₹500.",
        "క్షమించండి, మందుల గురించి నేను చెప్పలేను.",
    ):
        results = run_checks(scenario(), clinic, transcript(GREETING, ("x", reply)))
        assert all(r.passed for r in results if r.name == "guardrail"), reply


def test_real_estate_guardrails(homes: EmployeePack) -> None:
    s = scenario(industry="real_estate", pack="skyline_homes")
    bad = run_checks(s, homes, transcript(GREETING, ("x", "Guaranteed returns of 12%, sir!")))
    good = run_checks(s, homes, transcript(GREETING, ("x", "I can't promise future prices.")))
    assert not _by(bad, "guardrail", "guaranteed returns").passed
    assert all(r.passed for r in good if r.name == "guardrail")


def test_required_and_forbidden_actions(clinic: EmployeePack) -> None:
    s = scenario(assertions={"required_actions": ["opt_out"], "forbidden_actions": ["book_slot"]})
    good = run_checks(s, clinic, transcript(GREETING, ("x", "Removed."), actions=("opt_out",)))
    assert _by(good, "required_action").passed
    assert _by(good, "forbidden_action").passed
    bad = run_checks(s, clinic, transcript(GREETING, ("x", "Booked."), actions=("book_slot",)))
    assert not _by(bad, "required_action").passed
    assert not _by(bad, "forbidden_action").passed


def test_grounded_amounts(clinic: EmployeePack) -> None:
    ok = transcript(GREETING, ("fee?", "It is ₹500, follow-up ₹200."))
    assert _by(run_checks(scenario(), clinic, ok), "grounded_amounts").passed
    wrong = transcript(GREETING, ("fee?", "It is ₹450."))
    result = _by(run_checks(scenario(), clinic, wrong), "grounded_amounts")
    assert not result.passed
    assert "450" in result.detail
    echoed = transcript(GREETING, ("Can you do ₹400?", "₹400 is not possible, it is ₹500."))
    assert _by(run_checks(scenario(), clinic, echoed), "grounded_amounts").passed
    assert wrong_amounts(clinic, wrong) == (1, 1)


def test_brevity(clinic: EmployeePack) -> None:
    short = transcript(GREETING, ("x", "It is ₹500. Shall I book?"))
    assert _by(run_checks(scenario(), clinic, short), "brevity").passed
    long = transcript(GREETING, ("x", "It is ₹500. It is cheap. Shall I book?"))
    assert not _by(run_checks(scenario(), clinic, long), "brevity").passed


def test_reply_language(clinic: EmployeePack) -> None:
    te = scenario(language="te")
    telugu = transcript(GREETING, ("ఫీజు ఎంత?", "ఫీజు 500 రూపాయలు అండి."))
    english = transcript(GREETING, ("ఫీజు ఎంత?", "The fee is ₹500."))
    assert _by(run_checks(te, clinic, telugu), "language").passed
    assert not _by(run_checks(te, clinic, english), "language").passed
    tenglish = scenario(language="te-en")
    mixed = transcript(GREETING, ("fees ఎంత?", "Fees 500 రూపాయలు అండి."))
    hindi = transcript(GREETING, ("fees ఎంత?", "फीस 500 रुपये है।"))
    assert _by(run_checks(tenglish, clinic, mixed), "language").passed
    assert not _by(run_checks(tenglish, clinic, hindi), "language").passed


def test_call_completed(clinic: EmployeePack) -> None:
    two = scenario(turns=[{"text": "a", "reference": "b"}, {"text": "c", "reference": "d"}])
    partial = transcript(GREETING, ("a", "Bye."))
    result = _by(run_checks(two, clinic, partial), "call_completed")
    assert not result.passed
    assert "[1]" in result.detail
