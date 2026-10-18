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
