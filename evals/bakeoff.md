# Voice bake-off: results template (TRD §16, spike week 1-2)

One row is one full pipeline: **STT × TTS × LLM × framework/transport**. Fill one row per
combination tested. Generate the rows with `mitra_evals.metrics.BakeoffRow(...).markdown()` so
every row uses the same definitions. LLM cells hold the label you test under (LLM-1 … LLM-4).
Keep the real model ids in the run config, not in this file.

**Targets:** first-audio p95 ≤ 800 ms (TRD §12). Blended COGS ≤ ₹2.5/min (TRD §12), against
a ₹3/min Smart tier. Human-likeness: ≥ 70% of listeners cannot reliably tell (PRD G1).

| STT | TTS | LLM | Framework / transport | First audio p50 (ms) | First audio p95 (ms) | Telugu WER | Hindi WER | Naturalness MOS (panel) | Cost ₹/min |
|---|---|---|---|---|---|---|---|---|---|
| Sarvam | Bulbul v3 | LLM-1 | Pipecat / Exotel PSTN | | | | | | |
| Sarvam | ElevenLabs | LLM-1 | Pipecat / Exotel PSTN | | | | | | |
| Sarvam | Cartesia | LLM-1 | Pipecat / Exotel PSTN | | | | | | |
| Deepgram | Bulbul v3 | LLM-1 | Pipecat / Exotel PSTN | | | | | | |
| Sarvam | Bulbul v3 | LLM-2 | Pipecat / Exotel PSTN | | | | | | |
| Sarvam | Bulbul v3 | LLM-1 | LiveKit Agents / Plivo PSTN | | | | | | |
| Sarvam | Bulbul v3 | LLM-1 | LiveKit Agents / WebRTC (web) | | | | | | |
| … | | | | | | | | | |

## How each column is measured

| Column | Definition (see `mitra_evals/metrics.py`) | How |
|---|---|---|
| First audio p50 / p95 | ms from the caller's VAD end-of-turn to the first TTS audio frame reaching the carrier (`first_audio_ms`). Greeting excluded. Linear-interpolated percentiles. | ≥ 200 turns per row: the golden sets driven by the voice-text adapter with TTS on, plus real calls to test numbers over the carrier. Report the network path. |
| Telugu / Hindi WER | `corpus_wer`: word-level edit distance / reference words, after normalisation (Indic digits, case, punctuation). Code-mixed turns count under their base language. | 200 real phone turns per language (TRD §16 item 2), 8 kHz μ-law, with human reference transcripts. Report clean and noisy splits separately. |
| Naturalness MOS | `mos`: mean of 1-5 ratings with a 95% interval, from ≥ 10 native listeners (`evals/panel/`). | Same 30 s scripts rendered by each TTS row. Mixed into the blind A/B panel. |
| Cost ₹/min | STT + TTS + LLM + carrier + infra per connected minute, at list price, for the median call mix (talk ratio, tokens per turn, retries). | Price sheet × measured usage from the latency runs. Write down your FX rate and assumptions under the table. |

Also record per row: barge-in TTS stop (ms, target ≤ 200), interruption-handling score,
early-hang-up proxy, task success and wrong-fact rate from `mitra-evals run --agent voice-text`.
The `report.json` of each run is the evidence. Link it from the row.

## Decision

- Winner per tier (Smart / Natural / Signature):
- ADR-002 (Pipecat vs LiveKit Agents) outcome:
- Open risks:
