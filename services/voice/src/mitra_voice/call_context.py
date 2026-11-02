"""Per-call state shared between the pipeline and the brain: the caller's current language.

Language policy (mirror the caller, TRD §5 code-mix). Only the pack's languages are ever chosen.
- Native script is decisive: Telugu script -> te, Devanagari -> hi. Code-mixed transcripts
  (Sarvam "codemix": Indic words in native script, English words in Latin) count as the Indic
  language.
- STT locked to one language (packs with a single Indic language, see providers.make_stt):
  codemix writes that language in native script, so Latin-only text is English.
- STT on auto-detect: Latin-only text takes the detected language if it is in the pack
  (romanised Hindi/Telugu), else English.
- Detections outside the pack are ignored. Live probes showed Sarvam's auto-detect reading a short
  Telugu segment as Malayalam or Kannada, which is why single-Indic packs lock the STT.
- A switch needs evidence: native script, or at least two words. A lone "ok" or "haan" never
  flips the call language.

Code-mixing (Tenglish/Hinglish) is a separate, sticky trait of the caller: it turns on when an
Indic-language utterance carries English words in Latin script (Sarvam "codemix" output, e.g.
"consultation fee ఎంత?") and off after a clearly native-only utterance (3+ words, no Latin).
``human_lang`` ("te-en" / "hi-en") then drives speech normalisation, fillers and back-channels
(mitra_human); the TTS and STT keep the base language.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from mitra_human import Lang as HumanLang
from mitra_voice.pack import Lang

LanguageHook = Callable[[Lang], Awaitable[None]]
_STT_CODES: dict[str, Lang] = {"en": "en", "hi": "hi", "te": "te"}


def _script_lang(text: str) -> Lang | None:
    if any("ఀ" <= ch <= "౿" for ch in text):
        return "te"
    if any("ऀ" <= ch <= "ॿ" for ch in text):
        return "hi"
    return None


def stt_lang(code: str | None) -> Lang | None:
    """``"te-IN"`` / ``Language.TE_IN`` -> ``"te"``; anything outside en/hi/te -> None."""
    if not code:
        return None
    return _STT_CODES.get(str(code).split("-")[0].lower())


ALL_LANGS: tuple[Lang, ...] = ("en", "hi", "te")
_LATIN_WORD = re.compile(r"[A-Za-z]{2,}")
MIXED: dict[Lang, HumanLang] = {"te": "te-en", "hi": "hi-en"}


def has_latin_words(text: str) -> bool:
    return bool(_LATIN_WORD.search(text))


def human_lang_for(lang: Lang, code_mixed: bool) -> HumanLang:
    """The mitra_human language code: "te-en"/"hi-en" for a code-mixing caller."""
    return MIXED.get(lang, lang) if code_mixed else lang


def stt_lock_language(languages: list[Lang] | tuple[Lang, ...]) -> Lang | None:
    """The language to pin the STT to, or None for auto-detect (several Indic languages)."""
    indic = [lang for lang in languages if lang != "en"]
    if not indic:
        return "en"
    return indic[0] if len(set(indic)) == 1 else None


def detect_caller_language(
    text: str,
    stt_code: str | None,
    current: Lang,
    *,
    allowed: tuple[Lang, ...] = ALL_LANGS,
    stt_locked: bool = False,
) -> Lang:
    """The language to use from this utterance on (``current`` when the evidence is weak)."""
    words = text.split()
    if not words:
        return current
    script = _script_lang(text)
    if script is not None:
        return script if script in allowed else current
    detected = None if stt_locked else stt_lang(stt_code)
    candidate: Lang = detected if detected in allowed else "en"
    if candidate not in allowed or (candidate != current and len(words) < 2):
        return current
    return candidate


@dataclass
class CallContext:
    session_id: str
    language: Lang
    # The pack's languages, and whether the STT is pinned to one language (see module doc).
    allowed: tuple[Lang, ...] = ALL_LANGS
    stt_locked: bool = False
    language_history: list[Lang] = field(default_factory=list)
    code_mixed: bool = False
    # True when a filler was already spoken for the current turn (set by FillerProcessor before
    # the turn's LLMContextFrame reaches the LLM): at most one filler per turn (TRD §5).
    filler_spoken: bool = False
    on_language_change: list[LanguageHook] = field(default_factory=list)
    # Outbound calls: who we are calling and why (campaign script variables, callback topic).
    call_brief: str | None = None

    def __post_init__(self) -> None:
        if not self.language_history:
            self.language_history.append(self.language)

    @property
    def human_lang(self) -> HumanLang:
        return human_lang_for(self.language, self.code_mixed)

    def _observe_mixing(self, text: str) -> None:
        if self.language not in MIXED or _script_lang(text) is None:
            return  # only native-script utterances in an Indic call say anything about mixing
        if has_latin_words(text):
            self.code_mixed = True
        elif len(text.split()) >= 3:
            self.code_mixed = False

    async def observe_utterance(self, text: str, stt_code: str | None) -> bool:
        """Update the call language (and code-mix trait) from a final transcript.

        Returns True if the base language switched.
        """
        new = detect_caller_language(
            text, stt_code, self.language, allowed=self.allowed, stt_locked=self.stt_locked
        )
        if new == self.language:
            self._observe_mixing(text)
            return False
        self.language = new
        self.language_history.append(new)
        self._observe_mixing(text)
        for hook in list(self.on_language_change):
            await hook(new)
        return True
