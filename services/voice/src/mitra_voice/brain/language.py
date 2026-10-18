"""Caller-language policy: which language and script the next reply is in.

Codes: ``en``, ``hi``, ``te`` and the code-mixed ``te-en`` (Tenglish) / ``hi-en`` (Hinglish),
written the way Indic STT emits them (native script for Telugu/Hindi words, Latin for English).
In a live call the pipeline passes the STT's language tag through :class:`LanguageRef`; in text
mode (and when STT gives no tag) the language is detected from the caller's words.
"""

from __future__ import annotations

import re
from typing import Literal, get_args

from mitra_voice.pack import Lang

CallerLanguage = Literal["en", "hi", "te", "te-en", "hi-en"]
CALLER_LANGUAGES: frozenset[str] = frozenset(get_args(CallerLanguage))

# Latin share of letters above which native-script text counts as code-mixed. A single English
# word in a Telugu sentence ("RERA", "OK") stays plain Telugu.
_CODE_MIX_LATIN_SHARE = 0.3

# Romanised Telugu / Hindi markers (callers typing or STT emitting Latin script). Common enough
# words that two hits make the call; English words that collide ("to", "hai" in names) are left out.
_ROMAN_TE = frozenset(
    [
        "andi",
        "ela",
        "enti",
        "emi",
        "undi",
        "unnaya",
        "unnara",
        "cheyandi",
        "cheyakandi",
        "cheppandi",
        "kavali",
        "ledu",
        "ledhu",
        "avunu",
        "kaadu",
        "baagundi",
        "chala",
        "meeru",
        "nenu",
        "naaku",
        "maaku",
        "ekkada",
        "eppudu",
        "entha",
        "ivvandi",
        "raavali",
        "vastanu",
        "vastam",
        "garu",
        "cheyyandi",
        "sari",
        "ayyindi",
    ]
)
_ROMAN_HI = frozenset(
    [
        "kya",
        "hai",
        "hain",
        "nahi",
        "nahin",
        "mujhe",
        "mera",
        "meri",
        "aap",
        "aapka",
        "kitna",
        "kitni",
        "kab",
        "kahan",
        "karo",
        "karna",
        "chahiye",
        "bataiye",
        "bolo",
        "theek",
        "thik",
        "accha",
        "acha",
        "haan",
        "ji",
        "bhai",
        "matlab",
        "wala",
        "wali",
        "kijiye",
        "dijiye",
        "raha",
        "rahi",
    ]
)
_LATIN_WORD = re.compile(r"[a-z]+")
_LATIN_TOKEN = re.compile(r"[A-Za-z]{2,}")
_UNITS = frozenset({"ml", "mg", "kg", "km", "am", "pm", "sq", "ft", "yd"})


def base_language(code: str) -> Lang:
    """``te-en`` -> ``te``; unknown codes fall back to English."""
    head = code.split("-", 1)[0]
    if head == "te":
        return "te"
    if head == "hi":
        return "hi"
    return "en"


def normalise_code(code: str | None) -> CallerLanguage | None:
    """Accept STT/BCP-47 style tags (``te-IN``, ``hi_IN``, ``en-IN``) and our own codes."""
    if not code:
        return None
    c = code.strip().lower().replace("_", "-")
    if c in CALLER_LANGUAGES:
        return c  # type: ignore[return-value]
    head = c.split("-", 1)[0]
    if head in {"te", "hi", "en"}:
        return head  # type: ignore[return-value]
    return None


def detect_language(text: str, fallback: CallerLanguage | None = None) -> CallerLanguage | None:
    """Guess the caller's language from one utterance; ``fallback`` when there are no letters
    (e.g. "11", "ok?" is still English)."""
    te = sum(1 for c in text if "ఀ" <= c <= "౿")
    hi = sum(1 for c in text if "ऀ" <= c <= "ॿ")
    la = sum(1 for c in text if c.isascii() and c.isalpha())
    total = te + hi + la
    if total == 0:
        return fallback
    if te or hi:
        native: Lang = "te" if te >= hi else "hi"
        latin = _LATIN_TOKEN.findall(text)
        # Acronyms (RERA, BHK, TSH) are said the same way in any language; a real English word
        # ("fees", "ok", "evening") makes the utterance code-mixed.
        if la / total > _CODE_MIX_LATIN_SHARE or any(
            not w.isupper() and w.lower() not in _UNITS for w in latin
        ):
            return "te-en" if native == "te" else "hi-en"
        return native
    words = _LATIN_WORD.findall(text.lower())
    te_hits = sum(1 for w in words if w in _ROMAN_TE)
    hi_hits = sum(1 for w in words if w in _ROMAN_HI)
    if max(te_hits, hi_hits) >= 2 or (words and max(te_hits, hi_hits) / len(words) >= 0.3):
        return "te-en" if te_hits >= hi_hits else "hi-en"
    return "en"


class LanguageRef:
    """Per-call holder for the caller's current language, set by the pipeline from STT tags.

    ``resolve`` prefers a fresh STT tag, then text detection, then the last known language.
    """

    def __init__(self, initial: str | None = None) -> None:
        self._stt: CallerLanguage | None = None
        self._last: CallerLanguage | None = normalise_code(initial)

    def set(self, code: str | None) -> None:
        """Record the language the STT detected for the latest caller utterance."""
        self._stt = normalise_code(code)

    def get(self) -> CallerLanguage | None:
        return self._stt or self._last

    def resolve(self, caller_text: str) -> CallerLanguage:
        detected = detect_language(caller_text, fallback=None)
        stt = self._stt
        if stt and detected and base_language(stt) == base_language(detected):
            # STT knows the language; the text tells us whether it was code-mixed.
            lang: CallerLanguage = detected
        else:
            lang = stt or detected or self._last or "en"
        last = self._last
        if last and "-" in last and "-" not in lang and base_language(last) == lang:
            # A Hinglish caller's all-Hindi sentence is still a Hinglish call: keep the mix.
            lang = last
        self._last = lang
        self._stt = None
        return lang


def reply_instruction(lang: CallerLanguage) -> str:
    """The per-turn language line appended to the caller's message."""
    if lang == "te":
        return (
            "Reply in spoken Telugu written in Telugu script. Write common English loanwords in "
            "Telugu script too (అపాయింట్‌మెంట్, ఫీజు, వాట్సాప్); keep digits as digits."
        )
    if lang == "hi":
        return (
            "Reply in spoken Hindi written in Devanagari. Write common English loanwords in "
            "Devanagari too (अपॉइंटमेंट, फीस, व्हाट्सऐप); keep digits as digits."
        )
    if lang == "te-en":
        return (
            "Reply in Tenglish like the caller: Telugu words in Telugu script, English words "
            "(appointment, booking, WhatsApp) in Latin script. Never use Devanagari."
        )
    if lang == "hi-en":
        return (
            "Reply in Hinglish like the caller: Hindi words in Devanagari, English words "
            "(appointment, booking, WhatsApp) in Latin script. Never use Telugu script."
        )
    return "Reply in simple Indian English, in Latin script only."


__all__ = [
    "CALLER_LANGUAGES",
    "CallerLanguage",
    "LanguageRef",
    "base_language",
    "detect_language",
    "normalise_code",
    "reply_instruction",
]
