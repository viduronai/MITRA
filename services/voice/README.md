# mitra-voice

Real-time voice engine (Step 3a): a per-call Pipecat pipeline with the in-house human layer
(`libs/mitra-human`). It runs end to end with mock STT/LLM/TTS; real providers plug in by env
vars alone. See `docs/05-TRD.md` §5 and `docs/04-WORKFLOWS.md` §1–3. The framework and transport
decision is in `docs/ADR-002-spike-notes.md`.

## Run

```bash
cd services/voice
uv sync
uv run mitra-voice            # http://127.0.0.1:8200
```

Open http://127.0.0.1:8200, pick a scenario, press **Start talking** and allow the microphone.
With mock STT, *what* you say doesn't matter: each time you speak and pause, the next scripted
caller line is used (clinic: fee → timings → booking → location → parking). Wait for the
assistant to finish, or talk over it to barge in.

| Endpoint | |
|---|---|
| `GET /` | browser test page (WebRTC mic, live transcript, per-turn latency table) |
| `POST /api/offer`, `PATCH /api/offer` | WebRTC signalling (SmallWebRTC); the offer body takes `scenario` |
| `GET /sessions`, `GET /sessions/{id}/metrics` | per-turn latencies + p50/p95 summary |
| `POST /v1/text-sessions`, `POST /v1/text-sessions/{id}/turns`, `DELETE /v1/text-sessions/{id}` | text mode for `mitra-evals` (tool calls returned as `actions`) |
| `GET /api/voices` | catalog voices and their Sarvam speakers (test page voice picker) |
| `GET /health` | active providers, max event-loop lag |

## Pipeline

```
mic → SmallWebRTC in → STT → LanguageTracker → UserSpeechTap
    → user aggregator (Silero VAD + Smart Turn v3, per-language silence cap)
    → FillerProcessor → LLM (mock | Claude | Gemini brain) → SpeakableProcessor
      (clause/sentence chunks → speakable(), keeps TTS language = caller language)
    → TTS → [ReplyRecorder] → BackchannelPlayer → SmallWebRTC out → HeardTracker
    → assistant aggregator
```

- **Prompt** (`prompt.py`): global rules → role + behaviour → facts pack → customer memory
  (placeholder), static first so the prefix is cacheable; the conversation is the LLM context.
- **Greeting**: AI + recording disclosure, built from the pack (`greeting_for`), language =
  pack default (placeholder for the caller's last language).
- **Barge-in**: Pipecat stops TTS when the caller starts talking; the interrupted reply in the
  context is rewritten with `truncate_to_heard(reply, words_played)`, counting only words that
  actually left the output transport.
- **Back-channels**: `BackchannelPolicy` polled every 100 ms during a caller turn; the token is
  played as a short -6 dB clip straight to the output (never TTS, never in the context).
- **Fillers**: if predicted latency (measured median LLM TTFT + TTS TTFB, + tool time) > 700 ms,
  `FillerPolicy`'s filler is spoken first and kept out of the context.
- **Latency** (`latency.py`): an observer timestamps each turn from the pipeline clock:
  user-speech-end, STT final, turn end, LLM request/first token, TTS text-in/first byte, first
  audio out. Logged as JSON (`turn.latency`), streamed to the page, served on `/metrics`.
  Logged transcript text goes through `redact_phones`.

## Mocks

| | Behaviour | Tuning |
|---|---|---|
| STT | one scripted line per detected user turn (real VAD decides when), interim words while speaking | `providers/mock_stt.py` `SCRIPTS` |
| LLM | answers from the pack's facts, defers when a fact is missing, booking = simulated tool call | `MOCK_LLM_TTFT_MS`, `MOCK_LLM_TOKEN_MS`, `MOCK_TOOL_LATENCY_MS` |
| TTS | real 24 kHz audio (soft syllable-paced tone), length ∝ text, word timestamps | `MOCK_TTS_TTFB_MS`, `MOCK_TTS_MS_PER_CHAR` |

## Real providers

Set in `services/voice/.env` (see `.env.example`):

| Want | Set |
|---|---|
| Sarvam STT | `MITRA_STT=sarvam`, `SARVAM_API_KEY` (optional `MITRA_STT_MODEL`) |
| Deepgram STT | `MITRA_STT=deepgram`, `DEEPGRAM_API_KEY` |
| Claude for live turns | `MITRA_LLM=anthropic`, `ANTHROPIC_API_KEY`, `MITRA_LLM_MODEL` (a fast Haiku-class model; no default in code) |
| Sarvam Bulbul TTS | `MITRA_TTS=sarvam`, `SARVAM_API_KEY` (optional `MITRA_TTS_VOICE`, `MITRA_TTS_MODEL`) |
| ElevenLabs TTS | `MITRA_TTS=elevenlabs`, `ELEVENLABS_API_KEY`, `MITRA_TTS_VOICE` |

With `MITRA_ENV=local` a provider missing its key falls back to the mock with a message on
startup; any other env refuses to start.

## Brain (Gemini, `MITRA_LLM=gemini`)

`src/mitra_voice/brain/` is the conversational brain, shared by live calls and text mode:

| Module | |
|---|---|
| `engine.py` | one caller turn → checked, streamed reply sentences + tool actions; first-token timeout (`MITRA_LLM_FIRST_TOKEN_TIMEOUT_S`, 1.5 s) → filler + one retry (on `MITRA_LLM_MODEL_SLOW` if set) → apology + `schedule_callback` |
| `guardrails.py` | in code, every turn: emergencies (en/hi/te) → 112 + `transfer_to_human` + `alert_staff` with no LLM call; opt-outs → `opt_out` + `end_call`; medical-advice requests → `alert_staff` + refusal instruction; post-check of every sentence (₹ amounts vs the facts pack, medicine/dose/diagnosis, real-estate guarantees) |
| `tools.py` | in-call tools as Gemini function declarations, simulated against the pack (calendar from the timings facts) |
| `language.py`, `cues.py` | reply language/script (te, hi, en, te-en, hi-en) and one-turn cues (booking accepted, DOB given) |
| `llm.py` | `make_brain_llm(pack=, settings=, call=)`: Pipecat `GoogleLLMService` subclass for the pipeline |

Needs `GEMINI_API_KEY` and `MITRA_LLM_MODEL` (a fast Flash-class model, set only in `.env`). The
static system prompt comes first and is identical across turns, so Gemini's implicit prefix
cache applies; per-turn notes (language, clock, tool log) ride on the caller's message.

### Evals against the brain

```bash
# terminal 1: the brain in text mode (fixed clock = reproducible; cache = free re-runs)
cd services/voice
MITRA_LLM=gemini PORT=8210 MITRA_BRAIN_FIXED_NOW=2026-10-21T08:00:00+05:30 \
  MITRA_LLM_CACHE_DIR=.cache/llm uv run mitra-voice
# terminal 2
cd evals
MITRA_VOICE_TEXT_URL=http://127.0.0.1:8210 MITRA_VOICE_TEXT_TIMEOUT=300 \
  uv run mitra-evals run --agent voice-text --set all --judge off --out reports/brain.json
```

Free-tier keys: add `MITRA_LLM_MAX_RPM=5 MITRA_LLM_RATE_LIMIT_WAIT_S=90` (pace requests and
wait out 429s, text mode only) and run with `--concurrency 1`.

## Real speech: Sarvam (Step 3b)

Run with real speech (keys in `.env`, LLM still mock until Gemini billing is on):

```bash
MITRA_STT=sarvam MITRA_TTS=sarvam uv run mitra-voice     # PowerShell: set $env:MITRA_STT etc.
```

- **STT**: Sarvam streaming websocket (`saaras:v4`, `codemix` mode: Telugu/Hindi in native script,
  English words in Latin). One final transcript per VAD segment, ~300–400 ms after end of
  speech, no partials. `providers/sarvam_stt.py` sends audio from a background task in 100 ms
  chunks. Pipecat's own service awaits a socket send per 20 ms frame on the audio path, which
  stalled whole calls under backpressure.
- **Language**: packs with one Indic language pin the STT to it. Sarvam's auto-detect misread
  short Telugu as Malayalam/Kannada in live probes. Packs with several Indic languages
  auto-detect. `call_context.py` mirrors the caller: native script decides, at least 2 words to
  switch, pack languages only. The call language drives the brain, speech normalisation, TTS
  language, fillers and back-channels; the test page shows it.
- **TTS**: Sarvam Bulbul v3 streaming websocket. Catalog voice → speaker table in `voices.py`
  (priya-te-hyd → priya, arjun-te-vij → aditya, …); `MITRA_TTS_VOICE` overrides.
- **Back-channels**: each policy token is pre-rendered once per voice and language in the call's
  speaker, trimmed, -6 dB, cached in memory and in `.cache/clips` (gitignored).
- **Latency tuning** (before/after in `docs/ADR-002-spike-notes.md`): Smart Turn silence cap
  1.2 s for te/hi (2.0 s en), Bulbul min buffer 30, early first TTS chunk, heavy imports and
  ONNX loads off the event loop (`warmup.py`, `make_turn_analyzers`).
- **Recording** (dev only): `MITRA_RECORD_DIR=...` saves every assistant utterance as WAV.

## Employee pack

`pack.py` loads `fixtures/sunrise-clinic.json` / `fixtures/greenfield-realty.json`, or, when an
offer carries `employee_id` and `MITRA_CORE_URL` + `MITRA_CORE_SERVICE_TOKEN` are set, the real
pack from core's `GET /internal/v1/employees/{id}/pack` (Bearer service token; confirmed facts
only; the greeting already carries the disclosure). In `local`, an unreachable core falls back to
the fixture.

## Test & check

```bash
uv run pytest -q
uv run ruff check . && uv run ruff format --check .
uv run mypy            # strict; Pipecat-facing modules allow untyped calls/decorators (pyproject)
uv run pytest -m live  # opt-in: real Sarvam round trip (~3 API calls, keys from .env)
```

Pipeline tests run the real pipeline with mock providers, a paced in-memory transport and an
energy VAD (Silero rightly ignores synthetic tones).
