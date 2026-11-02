"""Back-channels: the "mm-hmm / हाँ जी / అవును" a listener says while the caller talks.

Timing rules (all per caller turn; a turn restarts when ``elapsed_ms`` goes backwards
or ``new_turn()`` is called):

- the caller has been speaking for at least 3500 ms;
- the current pause is a clause-boundary pause of 250-700 ms;
- at least 4000 ms since the previous back-channel;
- at most one back-channel in each 6-second block of the turn (0-6 s, 6-12 s, ...);
- the partial transcript looks mid-explanation: at least five words and the latest
  clause is not a question.
"""

from __future__ import annotations

import random
import re
from typing import Final

from mitra_human._lang import BaseLang, Lang, base_lang, check_lang, is_code_mixed

TOKENS: Final[dict[Lang, tuple[str, ...]]] = {
    "en": ("mm-hmm", "okay", "right"),
    "hi": ("हाँ जी", "अच्छा", "हम्म"),
    "te": ("అవును", "సరే", "హ్మ్"),
    "te-en": ("అవును", "సరే", "okay"),
    "hi-en": ("हाँ जी", "अच्छा", "okay"),
}

_CLAUSE_SPLIT = re.compile(r"[.!?।॥,;:]+")
_EN_QUESTION_STARTS = frozenset(
    """
    what why how when where who whom whose which can could will would should do does did is
    are am was were have has may shall
    """.split()
)
_EN_WH_WORDS = frozenset(("what", "why", "how", "when", "where", "who", "which"))
_EN_QUESTION_TAILS = ("right", "isn't it", "aren't you", "don't you", "no")
# "... but can you move it": an auxiliary followed by a subject, anywhere in the clause.
_EN_INVERSION = re.compile(
    r"\b(?:can|could|will|would|do|does|did|is|are|should|may|shall|have|has)\s+"
    r"(?:you|i|we|it|there|he|she|they)\b"
)
_HI_QUESTION_WORDS = frozenset(
    """
    क्या क्यों कब कहाँ कहां कैसे कैसा कैसी कौन कौनसा कितना कितने कितनी kya kyun kyon kab
    kahan kaise kaisa kaun kitna kitne kitni
    """.split()
)
_HI_QUESTION_TAILS = frozenset(("ना", "न", "na", "naa"))
_TE_QUESTION_WORDS = frozenset(
    """
    ఏమిటి ఏంటి ఏం ఎప్పుడు ఎక్కడ ఎలా ఎందుకు ఎవరు ఎంత ఎన్ని ఏది enti emiti eppudu ekkada ela
    enduku evaru entha enni edi
    """.split()
)
# Telugu yes/no questions end in -ా (ఉందా, వస్తారా); these common words do too.
_TE_NOT_QUESTIONS = frozenset(("చాలా", "కూడా", "ఇలా", "అలా", "మళ్ళా", "బాగా", "లేదా"))
_MIN_WORDS = 5


def is_question(clause: str, lang: Lang) -> bool:
    """Code-mixed clauses count as questions if either language's cues say so."""
    if is_code_mixed(lang):
        # The English part often starts mid-clause: "मैंने book किया था what is the status".
        return (
            _is_question(clause, base_lang(lang))
            or _is_question(clause, "en")
            or bool(_EN_WH_WORDS.intersection(clause.lower().split()))
        )
    return _is_question(clause, base_lang(lang))


def _is_question(clause: str, lang: BaseLang) -> bool:
    words = clause.lower().split()
    if not words:
        return False
    if lang == "en":
        joined = " ".join(words)
        return (
            words[0] in _EN_QUESTION_STARTS
            or joined.endswith(_EN_QUESTION_TAILS)
            or _EN_INVERSION.search(joined) is not None
        )
    if lang == "hi":
        return bool(_HI_QUESTION_WORDS.intersection(words)) or words[-1] in _HI_QUESTION_TAILS
    if _TE_QUESTION_WORDS.intersection(words):
        return True
    return words[-1].endswith("ా") and words[-1] not in _TE_NOT_QUESTIONS


def looks_mid_explanation(partial_text: str, lang: Lang) -> bool:
    text = partial_text.strip()
    if text.endswith("?") or len(text.split()) < _MIN_WORDS:
        return False
    clauses = [c for c in _CLAUSE_SPLIT.split(text) if c.strip()]
    return not clauses or not is_question(clauses[-1], lang)


class BackchannelPolicy:
    MIN_SPEECH_MS: Final = 3500
    MIN_PAUSE_MS: Final = 250
    MAX_PAUSE_MS: Final = 700
    MIN_GAP_MS: Final = 4000
    WINDOW_MS: Final = 6000

    def __init__(self, lang: Lang, *, seed: int | None = None) -> None:
        self._lang = check_lang(lang)
        self._rng = random.Random(seed)  # noqa: S311 - variety, not security
        self._last_token: str | None = None
        self._prev_elapsed = -1
        self._last_at: int | None = None
        self._windows_used: set[int] = set()

    def new_turn(self) -> None:
        """Forget the per-turn timing (call when the caller starts a new turn)."""
        self._prev_elapsed = -1
        self._last_at = None
        self._windows_used.clear()

    def on_user_speech(self, elapsed_ms: int, partial_text: str, pause_ms: int) -> str | None:
        """Return a back-channel token to play now, or None.

        ``elapsed_ms`` is how long the caller has been talking in this turn,
        ``pause_ms`` the length of the silence they are currently in.
        """
        if elapsed_ms < 0 or pause_ms < 0:
            raise ValueError("elapsed_ms and pause_ms must be non-negative")
        if elapsed_ms < self._prev_elapsed:
            self.new_turn()
        self._prev_elapsed = elapsed_ms

        if elapsed_ms < self.MIN_SPEECH_MS:
            return None
        if not self.MIN_PAUSE_MS <= pause_ms <= self.MAX_PAUSE_MS:
            return None
        if self._last_at is not None and elapsed_ms - self._last_at < self.MIN_GAP_MS:
            return None
        window = elapsed_ms // self.WINDOW_MS
        if window in self._windows_used:
            return None
        if not looks_mid_explanation(partial_text, self._lang):
            return None

        self._last_at = elapsed_ms
        self._windows_used.add(window)
        return self._pick()

    def _pick(self) -> str:
        choices = [t for t in TOKENS[self._lang] if t != self._last_token]
        token = self._rng.choice(choices)
        self._last_token = token
        return token
