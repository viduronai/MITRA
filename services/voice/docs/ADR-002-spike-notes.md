# ADR-002 update: Pipecat as the voice framework (spike notes, for team-lead review)

Status: **proposed: confirm Pipecat for P1**; the LiveKit Agents bake-off (TRD §16.1) still
needs real Telugu/Hindi phone audio and real providers.
Date: 2026-10-18 · Scope: Step 3a voice-engine skeleton.

## Decision

1. **Framework: Pipecat `pipecat-ai==1.12.0`** (latest, released 2026-09-26), pinned exactly. It
   installs and runs on **Windows 11 + Python 3.13** (uv, CPython 3.13.14). No need to fall back
   to 3.12.
2. **Browser transport: `SmallWebRTCTransport` (aiortc 1.15, PyAV 17)**, not the FastAPI
   WebSocket transport. It works on Windows. A plain-JS `RTCPeerConnection` client (no Pipecat
   client SDK) is enough.
3. **Turn detection: Silero VAD (stop 0.2 s) + Smart Turn v3.2** (`LocalSmartTurnAnalyzerV3`).
   Both are ONNX and bundled in the wheel, so the torch-heavy `local-smart-turn` extra is **not**
   needed. A VAD silence-timeout strategy is available through `MITRA_TURN=vad`.
4. **Carrier path (later):** Exotel/Plivo will use Pipecat's FastAPI WebSocket transport with
   their serializers. Only the transport changes; the pipeline is transport-agnostic
   (`build_call_pipeline` takes any input/output processors).

## What was verified

| Check | Result |
|---|---|
| `uv add pipecat-ai[silero,webrtc,websocket,sarvam,deepgram,anthropic,elevenlabs]==1.12.0` on py3.13/win | OK |
| aiortc loopback (two peers, Opus audio, 50 frames) | OK. **11.9 s** to connect with the default STUN server (STUN gathering times out on this network), **0.7 s** with `iceServers=[]` |
| Pipecat SmallWebRTC + headless Chrome (fake mic), echo pipeline | connected in 337 ms; 16 kHz 20 ms frames in; data channel and return audio OK |
| Full mock pipeline + headless Chrome, real speech WAV as mic | greeting + 3 Q&A turns, filler on the tool turn, metrics endpoint OK |
| Smart Turn v3 on English SAPI speech | correct end-of-turn on every turn; turn decision about 460 ms after end of speech (incl. 200 ms VAD stop) |

## Things the team should know about Pipecat 1.12

- `PipelineTask`/`PipelineRunner` are deprecated (since 1.3) in favour of `PipelineWorker` and
  `WorkerRunner(...).add_workers(...)`. We use the new API.
- VAD and turn strategies live on the **user context aggregator** (`LLMUserAggregatorParams`),
  not on the transport. VAD frames are broadcast both ways, so an upstream STT still sees them.
- Service config moved to `Service.Settings(...)`. Every settings field must be initialised,
  or Pipecat logs ERRORs (our mocks pass explicit `None`s).
- Observers are dispatched through a queue: use `FramePushed.timestamp` (pipeline clock) for
  latency, never wall-clock time at observation. With `observe_every_push=False` only a frame's
  first hop is seen.
- The aggregator triggers inference **before** it broadcasts `UserStoppedSpeakingFrame`.
- SmallWebRTC needs the client to send `ping` on the data channel at least every 3 s, or it
  considers the client gone. Transceiver 0 = audio, 1 = video.
- Pipecat's strict typing is partial: mypy strict needs `disallow_untyped_calls/decorators=false`
  and `disallow_subclassing_any=false` for Pipecat-facing modules only (documented in pyproject).

## Consequences / risks

- **ICE:** no STUN/TURN on localhost (STUN made connection setup 12 s here). A browser test page
  off-LAN needs a TURN server (TODO deploy). Phone calls won't use WebRTC.
- **Latency (mock providers):** first audio p50 is about 955 ms vs the 800 ms p95 target. Turn
  detection (about 460 ms) is the biggest share, then mock LLM TTFT (250 ms, configured) and the
  first clause streaming in. Levers: tune VAD stop / Smart Turn threshold per language,
  speculative generation on stable partials (Pipecat `speculation_gate`, TRD §5), and
  clause-level TTS flushing (already done; it saved about 380 ms on long first sentences).
- **LiveKit Agents** was not evaluated in this step; TRD §16.1 still applies.

---

## Step 3b update: real Sarvam speech (2026-10-18)

### Providers chosen in Pipecat 1.12

| Need | Choice | Why |
|---|---|---|
| STT | `SarvamSTTService` streaming websocket, `saaras:v4`, `mode="codemix"`, wrapped by `BufferedSarvamSTTService` | 300–400 ms from end of speech to final; code-mix in native + Latin script |
| STT (rejected) | `SarvamRealtimeSTTService` (partials, `language_code=auto`) | Live probe: translated Telugu into English and hallucinated text. Not usable yet. |
| TTS | `SarvamTTSService` (Bulbul v3, websocket, streaming) | First byte 200 ms (short chunks) to 500 ms (sentences) |
| Speculative LLM start | not possible | Pipecat's `EagerUserTurnStopStrategy` needs eager end-of-turn transcripts; Sarvam streaming gives one final per VAD segment and no partials |

### Language detection (live probes, Bulbul-synthesized callers)

| Clip | STT auto-detect | STT pinned te-IN |
|---|---|---|
| "నమస్కారం, కన్సల్టేషన్ ఫీజు ఎంత?" (te) | `ml-IN` "നമസ്കാരം." once; another run returned Kannada script "ಎಷ್ಟು" | correct Telugu |
| "What are your clinic timings?" (en) | en-IN, correct | correct, Latin |
| "क्या मैं कल शाम … appointment book कर सकता हूँ?" (hi) | hi-IN, correct code-mix | returned as Telugu or English text |
| "Clinic address ఎక్కడ ఉంది? Parking ఉందా?" (te-en) | te-IN, correct code-mix | correct |

Decision: pin the STT when the pack has a single Indic language (most SMBs: te+en or hi+en);
auto-detect only for multi-Indic packs, ignoring detections outside the pack.
`call_context.py` has the switching policy, unit-tested with the real transcripts above.

### Two production bugs found and fixed

1. **Blocked audio path.** Pipecat's Sarvam STT awaits a websocket send for every 20 ms frame,
   inline. Under backpressure the whole pipeline fell 17 s behind real time: VAD late,
   transcripts before their turn, greeting stuck. Fix: batch to 100 ms and send from a
   background task, draining before the VAD-stop flush.
2. **Event-loop stalls at call start.** Lazy imports (Pipecat's default LLM adapter pulls in
   `openai`, Sarvam SDK) and ONNX model loads ran on the shared loop: 3.5 s and 10.5 s stalls
   measured. Fix: import warm-up in a thread at startup and per-call model loads via
   `asyncio.to_thread`. Max loop lag is now ~150–500 ms at connect and is reported on `/health`.
   Also fixed: the greeting was dropped when the client connected before the pipeline started.

### Latency on localhost (real Sarvam STT/TTS, mock LLM TTFT 250 ms; ms, n=5 caller turns)

Same 86 s caller recording each run (te, en, en, te, hi-under-te-pin). In filler turns, "first
audio" is the filler.

| Config | STT p50 | Turn end p50 / p95 | TTS first byte p50 / p95 | First audio p50 / p95 |
|---|---|---|---|---|
| Before: Step 3a defaults (VAD 200 ms, Smart Turn cap 3 s, Bulbul buffer 50, whole first clause) | 347 | 444 / 2656 | 287 / 463 | 1218 / 3917 |
| After: VAD 200, Smart Turn cap te/hi 1.2 s, en 2.0 s, buffer 30, early first chunk | 446 | 453 / 1894 | 257 / 472 | 1255 / 2238 |
| After + VAD 160 ms | 325 | 445 / 1203 | 469 / 557 | 1230 / 2432 |
| VAD 120 ms (rejected) | - | - | - | split one Hindi utterance into 3 turns and degraded transcripts |

Breakdown of a typical non-filler turn: end of speech → Sarvam final ~350 → turn end ~450 →
LLM 250 (mock) → Bulbul first byte ~450 → first audio ~1.2 s. **800 ms p95 is not reachable
with this cascade on localhost.** Sarvam STT finalisation (~350) plus Bulbul first byte (~450)
alone exceed it. The tuning removed the long tail (Smart Turn misjudging Telugu: 3.2 s → 1.4 s).
Fillers already mask slow turns (perceived 640–680 ms). With Gemini, add its real TTFT.

Next levers: Bulbul's first-byte time (try a lower `max_chunk_length` and a pre-warmed socket
per call), an STT with eager end-of-turn or partials for Indic (enables speculative LLM start),
and filler-first on every turn predicted > 900 ms.
