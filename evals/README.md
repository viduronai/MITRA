# mitra-evals

Offline evaluation suite for Mitra conversations and the voice-provider bake-off (TRD §6, §13,
§16). Everything runs without provider keys against a pluggable agent under test.

```bash
uv sync                                              # dev + core groups (core = services/core, for core-sim)
uv run mitra-evals validate                          # schema + cross-checks, coverage counts
uv run mitra-evals run --agent scripted --set all --out reports/report.json
uv run mitra-evals run --agent core-sim --set clinic --language te --out reports/core.json
uv run mitra-evals run --agent reference --fail-under 1.0 --out reports/ref.json   # gold replies
uv run mitra-evals panel answers/*.json              # score listener-panel downloads (PRD G1)
```

`run` writes the JSON report and an HTML report next to it (or at `--html`). Pass rates are
broken down per industry, language and persona, and every failing assertion is listed with its
transcript. `--fail-under 0.9` turns a run into a CI gate.

## Layout

| Path | What |
|---|---|
| `sets/*.yaml` | Golden scenarios: caller turns, gold `reference` replies, `assertions`, `rubric`. Schema: `mitra_evals/schema.py`. Telugu and Hindi lines still need native review (see each file's header). |
| `fixtures/*.json` | Employee packs: Sunrise Clinic (Hyderabad) and Skyline Homes (Vijayawada). `missing_facts` lists the gaps that exist on purpose. |
| `mitra_evals/checks.py` | Deterministic checks: disclosure, recording notice, facts mentioned, forbidden phrases, industry guardrails, required/forbidden actions, grounded ₹ amounts, brevity, reply language. |
| `mitra_evals/judge.py` | Optional LLM judge for the rubric. Runs only when `ANTHROPIC_API_KEY` and `MITRA_JUDGE_MODEL` are set (`uv sync --extra judge` outside dev). |
| `mitra_evals/metrics.py` | Metric definitions for runs and the bake-off: first-audio p50/p95, early-hang-up rate and proxy, task success, wrong-fact rate, interruption score, WER, MOS. |
| `bakeoff.md` | Bake-off results table (STT × TTS × LLM × transport). |
| `panel/index.html` | Blind A/B listener panel (human vs Mitra). Open the file directly. Answers download as JSON. Clips are placeholders (`panel/clips/manifest.js`). |

## Agents under test

| `--agent` | What |
|---|---|
| `scripted` | Trivial keyword baseline: a floor to beat. |
| `reference` | Replays the gold replies. It must pass 100%, because that proves every assertion is satisfiable. |
| `core-sim` | `mitra_core.simulation` in-process (or `MITRA_CORE_URL` + `MITRA_CORE_TOKEN` + `MITRA_CORE_EMPLOYEE_ID` over HTTP). The simulation is non-interactive, so caller turns are mapped to the nearest scripted answer. |
| `voice-text` | Text-mode hook for services/voice: `MITRA_VOICE_TEXT_ENTRYPOINT=pkg.module:factory` (in-process) or `MITRA_VOICE_TEXT_URL` (HTTP). |

### Text-mode contract for services/voice

The full contract is in `mitra_evals/agents/base.py`. One scenario is one call:

```python
class AgentUnderTest(Protocol):
    name: str

    async def open(self, pack: EmployeePack, context: CallContext) -> ConversationSession: ...


class ConversationSession(Protocol):
    async def start(self) -> AgentReply: ...  # greeting, with AI + recording disclosure
    async def send(self, caller_text: str, *, interrupt: bool = False) -> AgentReply: ...
    async def close(self) -> None: ...
```

`AgentReply` = `text`, `actions` (in-call tool calls such as `book_slot`, `transfer_to_human`,
`opt_out`, `alert_staff`), `end_call`, and optional `timings` (`first_token_ms`,
`first_audio_ms`, `tts_stop_ms`). Over HTTP: `POST /v1/text-sessions`,
`POST /v1/text-sessions/{id}/turns`, `DELETE /v1/text-sessions/{id}`.

## Gates

```bash
uv run ruff check && uv run ruff format --check && uv run mypy && uv run pytest
```
