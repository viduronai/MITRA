from __future__ import annotations

import json
from pathlib import Path

import pytest

from mitra_evals.cli import main
from mitra_evals.panel import binomial_tail, summarise


def _listener(lid: str, correct: int, total: int, missing: int = 0) -> dict[str, object]:
    answers = [
        {
            "language": "te" if i % 2 else "hi",
            "correct": i < correct,
            "naturalness_by_source": {"mitra": 4, "human": 5},
        }
        for i in range(total)
    ]
    answers += [{"language": "te", "correct": True, "clip_missing": True}] * missing
    return {"listener": {"id": lid}, "answers": answers}


def test_binomial_tail() -> None:
    assert binomial_tail(0, 10) == pytest.approx(1.0)
    assert binomial_tail(10, 10) == pytest.approx(1 / 1024)
    assert binomial_tail(15, 20) == pytest.approx(0.0207, abs=1e-3)


def test_g1_summary() -> None:
    files = [_listener(f"L{i}", correct=11, total=20) for i in range(7)]
    files += [
        _listener("L8", correct=18, total=20),
        _listener("L9", correct=16, total=20, missing=3),
    ]
    summary = summarise(files)
    assert summary.g1_rate == pytest.approx(7 / 9)
    assert summary.g1_pass
    assert summary.skipped_missing == 3
    assert summary.naturalness["mitra"] is not None
    assert summary.naturalness["mitra"].mean == 4


def test_g1_fails_when_most_listeners_can_tell() -> None:
    summary = summarise([_listener("a", 19, 20), _listener("b", 20, 20), _listener("c", 10, 20)])
    assert not summary.g1_pass


def test_panel_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "L1.json"
    path.write_text(json.dumps(_listener("L1", 10, 20)), encoding="utf-8")
    assert main(["panel", str(path)]) == 0
    assert "cannot reliably tell" in capsys.readouterr().out
