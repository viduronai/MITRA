"""LLM text -> sentence chunks -> ``speakable()`` -> TTS.

Normalisation needs whole phrases ("₹1.1 crore" can arrive split over tokens), so tokens are
buffered to a sentence boundary first. Each spoken sentence is also recorded in the turn's
``ReplyLog``, which is what barge-in truncation and the live transcript use.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable

from pipecat.frames.frames import (
    Frame,
    InterruptionFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
    TTSSpeakFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from mitra_human import speakable
from mitra_voice.intents import detect_lang
from mitra_voice.pack import Lang
from mitra_voice.processors.reply import ReplyLog

# A sentence ends at . ! ? । … followed by whitespace, unless the word is a common abbreviation.
# A clause (, ; :) also ends a chunk once it is long enough, so a long first sentence does not
# hold back first audio while the rest of it streams in. "1,00,000" has no space: never split.
_BOUNDARY = re.compile(r"[.!?।…]+\s|(?P<clause>[,;:])\s")
_ABBREVIATIONS = frozenset({"no.", "dr.", "mr.", "mrs.", "ms.", "st.", "rd.", "nr.", "approx."})
MIN_CLAUSE_WORDS = 6

TextCallback = Callable[[str], Awaitable[None]]


def split_sentences(buffer: str) -> tuple[list[str], str]:
    """Complete chunks (sentences, or long-enough clauses) in ``buffer`` and the remainder."""
    sentences: list[str] = []
    start = 0
    for m in _BOUNDARY.finditer(buffer):
        candidate = buffer[start : m.end()].strip()
        last_word = candidate.rsplit(maxsplit=1)[-1].lower() if candidate else ""
        if last_word in _ABBREVIATIONS:
            continue
        if m.group("clause") and len(candidate.split()) < MIN_CLAUSE_WORDS:
            continue
        sentences.append(candidate)
        start = m.end()
    return sentences, buffer[start:]


class SpeakableProcessor(FrameProcessor):
    def __init__(
        self,
        reply: ReplyLog,
        *,
        default_lang: Lang,
        on_sentence: TextCallback | None = None,
    ) -> None:
        super().__init__()
        self._reply = reply
        self._default_lang = default_lang
        self._on_sentence = on_sentence
        self._buffer = ""

    def _speak(self, text: str) -> str:
        return speakable(text, detect_lang(text, self._default_lang))

    async def _emit(self, sentence: str) -> None:
        spoken = self._speak(sentence)
        self._reply.add(spoken)
        await self.push_frame(LLMTextFrame(spoken + " "))
        if self._on_sentence is not None:
            await self._on_sentence(spoken)

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if direction != FrameDirection.DOWNSTREAM:
            await self.push_frame(frame, direction)
        elif isinstance(frame, LLMFullResponseStartFrame):
            self._buffer = ""
            self._reply.start()
            await self.push_frame(frame, direction)
        elif isinstance(frame, LLMTextFrame):
            self._buffer += frame.text
            sentences, self._buffer = split_sentences(self._buffer)
            for sentence in sentences:
                await self._emit(sentence)
        elif isinstance(frame, LLMFullResponseEndFrame):
            if self._buffer.strip():
                await self._emit(self._buffer.strip())
            self._buffer = ""
            await self.push_frame(frame, direction)
        elif isinstance(frame, TTSSpeakFrame):
            # Greeting and fillers: normalised too, but not part of the LLM reply.
            await self.push_frame(
                TTSSpeakFrame(self._speak(frame.text), append_to_context=frame.append_to_context),
                direction,
            )
        else:
            if isinstance(frame, InterruptionFrame):
                self._buffer = ""
            await self.push_frame(frame, direction)
