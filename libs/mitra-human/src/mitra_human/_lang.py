"""Language codes and script helpers shared across the package."""

from __future__ import annotations

from typing import Literal, cast, get_args

# Public language codes. "te-en" (Tenglish) and "hi-en" (Hinglish) are code-mixed speech:
# amounts and plain numbers stay in Telugu/Hindi, while times, dates and phone numbers
# are spoken in English, the way code-mixing callers say them.
Lang = Literal["en", "hi", "te", "te-en", "hi-en"]
# The languages words are actually rendered in.
BaseLang = Literal["en", "hi", "te"]
SUPPORTED_LANGS: tuple[str, ...] = get_args(Lang)

DEVANAGARI = "ऀ-ॿ"
TELUGU = "ఀ-౿"


def check_lang(lang: str) -> Lang:
    """Validate a language code at the public boundary."""
    if lang not in SUPPORTED_LANGS:
        raise ValueError(f"unsupported language {lang!r}; expected one of {SUPPORTED_LANGS}")
    return cast(Lang, lang)


def base_lang(lang: Lang) -> BaseLang:
    """The native language of a code: "te-en" -> "te", "hi-en" -> "hi"."""
    if lang == "te-en":
        return "te"
    if lang == "hi-en":
        return "hi"
    return lang


def is_code_mixed(lang: Lang) -> bool:
    return lang in ("te-en", "hi-en")


def digits_lang(lang: Lang) -> BaseLang:
    """Language for digit-by-digit reading (phones, codes): English when code-mixed."""
    return "en" if is_code_mixed(lang) else base_lang(lang)


def has_devanagari(text: str) -> bool:
    return any("ऀ" <= ch <= "ॿ" for ch in text)


def has_telugu(text: str) -> bool:
    return any("ఀ" <= ch <= "౿" for ch in text)
