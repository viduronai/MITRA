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
| `GET /health` | which providers are active |

## Pipeline

```
mic → SmallWebRTC in → STT → UserSpeechTap → user aggregator (Silero VAD + Smart Turn v3)
    → FillerProcessor → LLM → SpeakableProcessor (clause/sentence chunks → speakable())
    → TTS → BackchannelPlayer → SmallWebRTC out → HeardTracker → assistant aggregator
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

## Employee pack

`pack.py` loads `fixtures/sunrise-clinic.json` / `fixtures/greenfield-realty.json`. If
`MITRA_CORE_URL` and `MITRA_CORE_SERVICE_TOKEN` are set, it calls the core loader, which is a stub:
core needs `GET /internal/v1/employees/{id}/pack` behind service auth (details in `pack.py`).

## Test & check

```bash
uv run pytest -q
uv run ruff check . && uv run ruff format --check .
uv run mypy            # strict; Pipecat-facing modules allow untyped calls/decorators (pyproject)
```

Pipeline tests run the real pipeline with mock providers, a paced in-memory transport and an
energy VAD (Silero rightly ignores synthetic tones).
