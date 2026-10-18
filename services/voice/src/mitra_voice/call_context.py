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
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

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
    # True when a filler was already spoken for the current turn (set by FillerProcessor before
    # the turn's LLMContextFrame reaches the LLM): at most one filler per turn (TRD §5).
    filler_spoken: bool = False
    on_language_change: list[LanguageHook] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.language_history:
            self.language_history.append(self.language)

    async def observe_utterance(self, text: str, stt_code: str | None) -> bool:
        """Update the call language from a final transcript; True if it switched."""
        new = detect_caller_language(
            text, stt_code, self.language, allowed=self.allowed, stt_locked=self.stt_locked
        )
        if new == self.language:
            return False
        self.language = new
        self.language_history.append(new)
        for hook in list(self.on_language_change):
            await hook(new)
        return True
