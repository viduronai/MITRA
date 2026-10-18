"""Language codes and script helpers shared across the package."""

from __future__ import annotations

from typing import Literal, cast, get_args

Lang = Literal["en", "hi", "te"]
SUPPORTED_LANGS: tuple[str, ...] = get_args(Lang)

DEVANAGARI = "ऀ-ॿ"
TELUGU = "ఀ-౿"


def check_lang(lang: str) -> Lang:
    """Validate a language code at the public boundary."""
    if lang not in SUPPORTED_LANGS:
        raise ValueError(f"unsupported language {lang!r}; expected one of {SUPPORTED_LANGS}")
    return cast(Lang, lang)


def has_devanagari(text: str) -> bool:
    return any("ऀ" <= ch <= "ॿ" for ch in text)


def has_telugu(text: str) -> bool:
    return any("ఀ" <= ch <= "౿" for ch in text)
