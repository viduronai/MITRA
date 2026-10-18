"""Barge-in support: cut the assistant's text down to what the caller actually heard."""

from __future__ import annotations

import re

_WORD = re.compile(r"\S+")
_SENTENCE_END = (".", "!", "?", "।", "॥", "…")
_DANGLING = ",;:-–—"
ELLIPSIS = "…"


def truncate_to_heard(text: str, words_played: int) -> str:
    """Return the first ``words_played`` whitespace-separated words of ``text``.

    Works for any script (words are split on whitespace only). If the cut falls
    mid-sentence an ellipsis is appended; a dangling comma or dash is dropped first.
    0 words gives ""; ``words_played`` at or past the end returns ``text`` unchanged.
    """
    if words_played < 0:
        raise ValueError("words_played must be non-negative")
    words = list(_WORD.finditer(text))
    if words_played >= len(words):
        return text
    if words_played == 0:
        return ""
    last = words[words_played - 1].group()
    heard = text[words[0].start() : words[words_played - 1].end()]
    if last.endswith(_SENTENCE_END):
        return heard
    if last.rstrip(_DANGLING):  # never drop a word that is only punctuation
        heard = heard.rstrip(_DANGLING)
    return heard + ELLIPSIS
