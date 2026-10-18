"""Runner and CLI smoke tests on the offline agents, plus the optional judge with a fake client."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from mitra_evals.agents.scripted import ScriptedAgent
from mitra_evals.cli import main
from mitra_evals.judge import Judge, judge_model
from mitra_evals.loader import Suite
from mitra_evals.report import render_html
from mitra_evals.results import JudgeScore, RunReport
from mitra_evals.runner import run_suite


def test_run_suite_on_scripted(suite: Suite) -> None:
    selected = suite.select("all")
    report = asyncio.run(run_suite(ScriptedAgent(), suite, selected))
    s = report.summary
    assert s.overall.total == len(selected)
    assert 0 < s.overall.passed < s.overall.total  # a floor, not a ceiling
    assert set(s.by_industry) == {"clinic", "real_estate"}
    assert set(s.by_language) == {"en", "hi", "te", "te-en", "hi-en"}
    assert s.by_check["disclosure"].rate == 1.0
    assert all(r.transcript[0].speaker == "agent" for r in report.scenarios)
    html = render_html(report)
    assert "Failing scenarios" in html
    assert "clinic.fee.en" in html


def test_cli_run_writes_reports(tmp_path: Path) -> None:
    out = tmp_path / "out" / "report.json"
    assert main(["run", "--agent", "scripted", "--set", "clinic_info", "--out", str(out)]) == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    report = RunReport.model_validate(data)
    assert report.agent == "scripted"
    assert report.sets == ["clinic_info"]
    assert "rate" in data["summary"]["overall"]
    assert out.with_suffix(".html").read_text(encoding="utf-8").startswith("<!doctype html>")


def test_cli_fail_under_and_filters(tmp_path: Path) -> None:
    out = str(tmp_path / "r.json")
    args = ["run", "--agent", "scripted", "--language", "te", "--out", out]
    assert main([*args, "--fail-under", "1.0"]) == 1
    assert main(["run", "--agent", "reference", "--set", "real_estate", "--out", out]) == 0
    assert main(["run", "--agent", "scripted", "--persona", "nobody", "--out", out]) == 2


def test_cli_reports_unavailable_agent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MITRA_VOICE_TEXT_URL", raising=False)
    monkeypatch.delenv("MITRA_VOICE_TEXT_ENTRYPOINT", raising=False)
    assert main(["run", "--agent", "voice-text", "--out", str(tmp_path / "r.json")]) == 3


def test_cli_validate(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["validate"]) == 0
    assert "scenarios in" in capsys.readouterr().out


def test_judge_off_without_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("MITRA_JUDGE_MODEL", "some-model")
    assert judge_model() is None
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.delenv("MITRA_JUDGE_MODEL")
    assert judge_model() is None
    monkeypatch.setenv("MITRA_JUDGE_MODEL", "some-model")
    assert judge_model() == "some-model"


class _FakeMessages:
    def __init__(self, response: Any) -> None:
        self.response, self.calls = response, []

    async def parse(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return self.response


def test_judge_with_fake_client(suite: Suite) -> None:
    verdict = SimpleNamespace(
        scores=[
            JudgeScore(item="politeness", score=5, reason="warm"),
            JudgeScore(item="persona_handling", score=2, reason="not requested"),
        ],
        summary="Good call.",
    )
    messages = _FakeMessages(SimpleNamespace(stop_reason="end_turn", parsed_output=verdict))
    judge = Judge("some-model", client=SimpleNamespace(messages=messages))
    _, scenario = suite.select("clinic.fee.en")[0]
    report = asyncio.run(
        run_suite(ScriptedAgent(), suite, [("clinic_info", scenario)], judge=judge)
    )
    result = report.scenarios[0].judge
    assert result is not None
    assert [s.item for s in result.scores] == ["politeness"]
    assert report.judge_enabled
    assert report.summary.judge_means == {"politeness": 5.0}
    sent = messages.calls[0]
    assert sent["model"] == "some-model"
    assert "Facts pack" in sent["messages"][0]["content"]


def test_judge_refusal_is_recorded(suite: Suite) -> None:
    messages = _FakeMessages(SimpleNamespace(stop_reason="refusal", parsed_output=None))
    judge = Judge("some-model", client=SimpleNamespace(messages=messages))
    _, scenario = suite.select("clinic.fee.en")[0]
    report = asyncio.run(
        run_suite(ScriptedAgent(), suite, [("clinic_info", scenario)], judge=judge)
    )
    result = report.scenarios[0].judge
    assert result is not None
    assert result.error
    assert "refusal" in result.error
