"""``mitra-evals``: validate the golden sets, show coverage, run an agent, write reports."""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

from mitra_evals.agents import AGENT_NAMES, AgentUnavailableError, build_agent
from mitra_evals.judge import Judge, judge_model
from mitra_evals.loader import ROOT, Suite, load_suite
from mitra_evals.report import write_reports
from mitra_evals.runner import run_suite


def _stats(suite: Suite) -> str:
    scenarios = [s for _, s in suite.scenarios()]
    lines = [f"{len(scenarios)} scenarios in {len(suite.sets)} sets, {len(suite.packs)} packs"]
    for field in ("industry", "language", "persona"):
        counts = Counter(getattr(s, field) for s in scenarios)
        lines.append(f"  {field:<9} " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
    return "\n".join(lines)


def _run(args: argparse.Namespace, suite: Suite) -> int:
    selected = suite.select(args.set)
    if args.language:
        selected = [(n, s) for n, s in selected if s.language in args.language]
    if args.persona:
        selected = [(n, s) for n, s in selected if s.persona in args.persona]
    if not selected:
        print("no scenarios match the selection", file=sys.stderr)
        return 2
    try:
        agent = build_agent(args.agent, {s.id: s for _, s in suite.scenarios()})
    except AgentUnavailableError as exc:
        print(f"agent {args.agent!r} is unavailable: {exc}", file=sys.stderr)
        return 3

    notes: list[str] = []
    mode = getattr(agent, "mode", None)
    if mode:
        notes.append(f"{agent.name} mode: {mode}")
    model = judge_model()
    judge: Judge | None = None
    if args.judge == "off":
        notes.append("LLM judge disabled (--judge off)")
    elif model is None:
        if args.judge == "on":
            print("--judge on needs ANTHROPIC_API_KEY and MITRA_JUDGE_MODEL", file=sys.stderr)
            return 2
        notes.append("LLM judge skipped: ANTHROPIC_API_KEY and MITRA_JUDGE_MODEL not both set")
    else:
        try:
            judge = Judge(model)
        except ImportError:
            print("the LLM judge needs the `judge` extra (anthropic)", file=sys.stderr)
            return 2
    if any(s.audio for _, s in selected):
        notes.append("Audio-sim markers (noise, SNR) are ignored in text mode")

    report = asyncio.run(
        run_suite(agent, suite, selected, judge=judge, concurrency=args.concurrency, notes=notes)
    )
    out = Path(args.out)
    html = Path(args.html) if args.html else out.with_suffix(".html")
    write_reports(report, out, html)
    s = report.summary
    print(f"{agent.name}: {s.overall.passed}/{s.overall.total} passed ({s.overall.rate:.0%})")
    for dim, rates in (
        ("industry", s.by_industry),
        ("language", s.by_language),
        ("persona", s.by_persona),
    ):
        print(f"  {dim:<9} " + ", ".join(f"{k} {r.rate:.0%}" for k, r in rates.items()))
    for note in notes:
        print(f"  note: {note}")
    print(f"wrote {out} and {html}")
    if args.fail_under is not None and s.overall.rate < args.fail_under:
        print(f"pass rate below --fail-under {args.fail_under:.0%}", file=sys.stderr)
        return 1
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mitra-evals", description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT, help="evals folder (sets/, fixtures/)")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate", help="validate every set and pack, print coverage")
    run = sub.add_parser("run", help="run scenarios against an agent")
    run.add_argument("--agent", choices=AGENT_NAMES, required=True)
    run.add_argument("--set", default="all", help="all | clinic | real_estate | set names | ids")
    run.add_argument("--language", action="append", help="filter: en, hi, te, te-en, hi-en")
    run.add_argument("--persona", action="append", help="filter by persona")
    run.add_argument("--out", default="reports/report.json", help="JSON report path")
    run.add_argument("--html", help="HTML report path (default: next to --out)")
    run.add_argument("--judge", choices=("auto", "on", "off"), default="auto")
    run.add_argument("--concurrency", type=int, default=4)
    run.add_argument("--fail-under", type=float, help="exit 1 if the pass rate is below this (0-1)")
    panel = sub.add_parser("panel", help="score listener-panel answer files (PRD G1)")
    panel.add_argument("files", nargs="+", type=Path)
    args = parser.parse_args(argv)

    if args.command == "panel":
        from mitra_evals.panel import load_files, render, summarise

        print(render(summarise(load_files(args.files))))
        return 0

    try:
        suite = load_suite(args.root)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2
    if args.command == "validate":
        print(_stats(suite))
        return 0
    try:
        return _run(args, suite)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
