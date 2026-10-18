"""Per-language end-of-turn tuning (TRD §5 adaptive patience; latency budget WORKFLOWS §1).

Smart Turn v3 is trained mostly on English. On Telugu questions ("...చేయవచ్చా?") it often says
"incomplete", and the turn then ends only at its silence cap (default 3 s, measured: 3.2 s turn
end in the live smoke). For Indic languages we cap that silence lower, so a misjudged turn costs
at most about 1.2 s. English keeps a longer cap because the model is reliable there and callers
pause mid-thought. The Silero VAD stop window is global (``MITRA_VAD_STOP_MS``): it also triggers
Sarvam's transcript flush, so it sits on every turn's path.

TODO(spike): re-tune both values per language on real 8 kHz call audio (TRD §16.2).
"""

from __future__ import annotations

from pipecat.audio.turn.smart_turn.local_smart_turn_v3 import LocalSmartTurnAnalyzerV3

from mitra_voice.pack import Lang

SMART_TURN_MAX_SILENCE_S: dict[Lang, float] = {"en": 2.0, "hi": 1.2, "te": 1.2}


class TunableSmartTurn(LocalSmartTurnAnalyzerV3):
    """Smart Turn whose silence cap can change mid-call (Pipecat computes it once at init)."""

    def __init__(self, *, override_s: float | None = None) -> None:
        super().__init__()
        self._override_s = override_s

    def set_max_silence(self, seconds: float) -> None:
        self._params = self._params.model_copy(update={"stop_secs": seconds})
        self._stop_ms = seconds * 1000

    def tune_for(self, lang: Lang) -> None:
        self.set_max_silence(self._override_s or SMART_TURN_MAX_SILENCE_S[lang])

    @property
    def max_silence_s(self) -> float:
        return float(self._params.stop_secs)
