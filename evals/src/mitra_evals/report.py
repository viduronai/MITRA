"""Writes ``report.json`` and a self-contained HTML report (no external assets)."""

from __future__ import annotations

from html import escape
from pathlib import Path

from mitra_evals.results import Rate, RunReport, ScenarioResult

_CSS = """
:root{--bg:#f7f8fa;--panel:#fff;--ink:#14161a;--muted:#5d6470;--line:#e3e6eb;--accent:#2459f5;
--ok:#1f8a4c;--bad:#c2372b;--warn:#a86a00;--bar:#dfe6fb;--caller:#eef1f5;--agent:#e8efff;
font-family:"Segoe UI",system-ui,-apple-system,sans-serif}
@media (prefers-color-scheme:dark){:root{--bg:#0e1013;--panel:#171a1f;--ink:#e9ecf1;--muted:#9aa3af;
--line:#2a2f37;--accent:#6f92ff;--ok:#4cc184;--bad:#ff7a6e;--warn:#e0a83a;--bar:#22305a;
--caller:#20242b;--agent:#1b2742}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);line-height:1.45}
main{max-width:1080px;margin:0 auto;padding:28px 16px 64px}
h1{font-size:24px;margin:0 0 4px}h2{font-size:17px;margin:32px 0 12px}
.meta{color:var(--muted);font-size:13px}.meta code{font-size:12px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-top:18px}
.tile{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:12px 14px}
.tile b{display:block;font-size:24px;font-variant-numeric:tabular-nums}
.tile span{color:var(--muted);font-size:12px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:14px}
table{width:100%;border-collapse:collapse;background:var(--panel);border:1px solid var(--line);
border-radius:10px;overflow:hidden;font-size:13px}
th,td{padding:7px 10px;text-align:left;border-bottom:1px solid var(--line)}
th{color:var(--muted);font-weight:600;font-size:12px}td.n{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.bar{position:relative;height:8px;background:var(--bar);border-radius:4px;min-width:80px}
.bar i{position:absolute;inset:0 auto 0 0;background:var(--accent);border-radius:4px}
details{background:var(--panel);border:1px solid var(--line);border-radius:10px;margin:8px 0}
summary{cursor:pointer;padding:10px 14px;display:flex;gap:10px;align-items:baseline;flex-wrap:wrap}
summary .id{font-family:ui-monospace,Consolas,monospace;font-size:12px;color:var(--muted)}
.tag{font-size:11px;padding:1px 7px;border-radius:9px;border:1px solid var(--line);
color:var(--muted)}
.body{padding:0 14px 14px}.fail{color:var(--bad)}.pass{color:var(--ok)}
ul.checks{margin:6px 0 12px;padding-left:18px;font-size:13px}ul.checks li{margin:3px 0}
.chat{display:flex;flex-direction:column;gap:6px}
.msg{max-width:85%;padding:8px 11px;border-radius:10px;font-size:14px}
.msg.caller{background:var(--caller);align-self:flex-start}.msg.agent{background:var(--agent);align-self:flex-end}
.msg small{display:block;color:var(--muted);font-size:11px;margin-bottom:2px}
.chip{display:inline-block;font-size:11px;margin:4px 4px 0 0;padding:1px 7px;border-radius:9px;
background:var(--panel);border:1px solid var(--line)}
.err{color:var(--warn);font-size:13px}.judge{font-size:13px;color:var(--muted);margin:6px 0 10px}
"""


def _pct(v: float | None) -> str:
    return "-" if v is None else f"{v:.0%}"


def _rate_table(title: str, rates: dict[str, Rate]) -> str:
    rows = "".join(
        f"<tr><td>{escape(k)}</td><td class=n>{r.passed}/{r.total}</td>"
        f"<td class=n>{_pct(r.rate)}</td>"
        f"<td><div class=bar><i style='width:{r.rate * 100:.0f}%'></i></div></td></tr>"
        for k, r in rates.items()
    )
    return (
        f"<div><table><thead><tr><th>{escape(title)}</th><th class=n>Passed</th>"
        "<th class=n>Rate</th>"
        f"<th></th></tr></thead><tbody>{rows}</tbody></table></div>"
    )


def _metric(name: str, value: float | None) -> str:
    if value is None:
        shown = "-"
    elif "latency" in name:
        shown = f"{value:.0f} ms"
    else:
        shown = _pct(value)
    return f"<div class=tile><b>{shown}</b><span>{escape(name.replace('_', ' '))}</span></div>"


def _transcript(r: ScenarioResult) -> str:
    out = []
    for t in r.transcript:
        who = "Caller" if t.speaker == "caller" else "Agent"
        label = who + (" (interrupts)" if t.interrupt else "")
        if t.speaker == "agent" and t.response_ms is not None:
            label += f" · {t.response_ms:.0f} ms"
        chips = "".join(f"<span class=chip>{escape(a.name)}</span>" for a in t.actions)
        out.append(
            f"<div class='msg {t.speaker}'><small>{escape(label)}</small>"
            f"{escape(t.text)}{chips}</div>"
        )
    return f"<div class=chat>{''.join(out)}</div>"


def _scenario(r: ScenarioResult, *, open_: bool) -> str:
    failed = [c for c in r.checks if not c.passed]
    checks = "".join(
        f"<li><b>{escape(c.name)}</b>: {escape(c.label)}"
        + (f" (turn {c.turn})" if c.turn is not None else "")
        + (f" - <span class=fail>{escape(c.detail)}</span>" if c.detail else "")
        + "</li>"
        for c in failed
    )
    judge = ""
    if r.judge and r.judge.scores:
        judge = (
            "<div class=judge>Judge: "
            + ", ".join(f"{escape(s.item)} {s.score}/5" for s in r.judge.scores)
            + f". {escape(r.judge.summary)}</div>"
        )
    elif r.judge and r.judge.error:
        judge = f"<div class=err>Judge error: {escape(r.judge.error)}</div>"
    error = f"<div class=err>Agent error: {escape(r.error)}</div>" if r.error else ""
    status = "<span class=pass>pass</span>" if r.passed else "<span class=fail>fail</span>"
    tags = "".join(
        f"<span class=tag>{escape(x)}</span>" for x in (r.industry, r.language, r.persona, r.set)
    )
    return (
        f"<details{' open' if open_ else ''}><summary>{status}<b>{escape(r.title)}</b>"
        f"<span class=id>{escape(r.id)}</span>{tags}</summary><div class=body>{error}"
        + (f"<ul class=checks>{checks}</ul>" if checks else "")
        + f"{judge}{_transcript(r)}</div></details>"
    )


def render_html(report: RunReport) -> str:
    s = report.summary
    failing = [r for r in report.scenarios if not r.passed]
    passing = [r for r in report.scenarios if r.passed]
    tiles = (
        f"<div class=tile><b>{_pct(s.overall.rate)}</b><span>scenarios passed "
        f"({s.overall.passed}/{s.overall.total})</span></div>"
        + "".join(_metric(k, v) for k, v in s.metrics.items())
    )
    judge = (
        _rate_free_table("Judge item", s.judge_means)
        if s.judge_means
        else "<p class=meta>LLM judge not run (needs ANTHROPIC_API_KEY and MITRA_JUDGE_MODEL).</p>"
    )
    notes = "".join(f"<div class=meta>{escape(n)}</div>" for n in report.notes)
    return (
        "<!doctype html><html lang=en><head><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width,initial-scale=1'>"
        f"<title>Mitra eval report</title><style>{_CSS}</style></head><body><main>"
        f"<h1>Mitra eval report</h1><div class=meta>Agent <code>{escape(report.agent)}</code> · "
        f"run <code>{escape(report.run_id)}</code> · {escape(report.created_at)} · sets: "
        f"{escape(', '.join(report.sets))}</div>{notes}<div class=tiles>{tiles}</div>"
        "<h2>Pass rate</h2><div class=grid>"
        + _rate_table("Industry", s.by_industry)
        + _rate_table("Language", s.by_language)
        + _rate_table("Persona", s.by_persona)
        + _rate_table("Check", s.by_check)
        + f"</div><h2>LLM judge</h2>{judge}"
        f"<h2>Failing scenarios ({len(failing)})</h2>"
        + "".join(_scenario(r, open_=i < 3) for i, r in enumerate(failing))
        + f"<h2>Passing scenarios ({len(passing)})</h2>"
        + "".join(_scenario(r, open_=False) for r in passing)
        + "</main></body></html>"
    )


def _rate_free_table(title: str, means: dict[str, float]) -> str:
    rows = "".join(
        f"<tr><td>{escape(k)}</td><td class=n>{v:.2f} / 5</td>"
        f"<td><div class=bar><i style='width:{v / 5 * 100:.0f}%'></i></div></td></tr>"
        for k, v in means.items()
    )
    return (
        f"<table><thead><tr><th>{escape(title)}</th><th class=n>Mean</th><th></th></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
    )


def write_reports(report: RunReport, json_path: Path, html_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    html_path.write_text(render_html(report), encoding="utf-8")
