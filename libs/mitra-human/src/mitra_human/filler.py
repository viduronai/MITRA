"""Instant acknowledgements ("Sure, one second.") that mask a slow answer.

A filler is returned only when the expected latency is above 700 ms, at most once
every two turns, and never the same filler twice in a row.
"""

from __future__ import annotations

import random
from typing import Final, Literal

from mitra_human._lang import Lang, check_lang

Gender = Literal["female", "male"]

_FILLERS: Final[dict[tuple[Lang, Gender], tuple[str, ...]]] = {
    ("en", "female"): ("Sure, one second.", "Let me check.", "Okay, just a moment."),
    ("hi", "female"): ("जी, एक सेकंड…", "देखती हूँ…", "एक मिनट, मैं चेक करती हूँ…"),
    ("hi", "male"): ("जी, एक सेकंड…", "देखता हूँ…", "एक मिनट, मैं चेक करता हूँ…"),
    ("te", "female"): ("సరే, ఒక్క నిమిషం…", "చూస్తాను…", "ఒక్క క్షణం అండి…"),
}
# Code-mixed callers get English-leaning fillers with the native politeness word.
_FILLERS[("te-en", "female")] = ("one minute అండి…", "check చేస్తాను…", "just a second అండి…")
_FILLERS[("hi-en", "female")] = ("just one minute जी…", "check करती हूँ…", "one second जी…")
_FILLERS[("hi-en", "male")] = ("just one minute जी…", "check करता हूँ…", "one second जी…")
# English and Telugu first-person verbs do not change with gender.
_FILLERS[("en", "male")] = _FILLERS[("en", "female")]
_FILLERS[("te", "male")] = _FILLERS[("te", "female")]
_FILLERS[("te-en", "male")] = _FILLERS[("te-en", "female")]


def fillers(lang: Lang, gender: Gender = "female") -> tuple[str, ...]:
    return _FILLERS[(lang, gender)]


class FillerPolicy:
    LATENCY_THRESHOLD_MS: Final = 700
    MIN_TURN_GAP: Final = 2

    def __init__(self, lang: Lang, *, seed: int | None = None, gender: Gender = "female") -> None:
        self._lang = check_lang(lang)
        if gender not in ("female", "male"):
            raise ValueError(f"gender must be 'female' or 'male', got {gender!r}")
        self._options = _FILLERS[(self._lang, gender)]
        self._rng = random.Random(seed)  # noqa: S311 - variety, not security
        self._last_filler: str | None = None
        self._last_turn: int | None = None

    def filler_for(self, expected_latency_ms: int, turn_index: int) -> str | None:
        """Return a filler to say before a slow answer on ``turn_index``, or None."""
        if expected_latency_ms <= self.LATENCY_THRESHOLD_MS:
            return None
        if self._last_turn is not None and turn_index < self._last_turn:
            self._last_turn = None  # turn counter restarted: a new call
        if self._last_turn is not None and turn_index - self._last_turn < self.MIN_TURN_GAP:
            return None
        choices = [f for f in self._options if f != self._last_filler]
        filler = self._rng.choice(choices)
        self._last_filler = filler
        self._last_turn = turn_index
        return filler
