"""LLM text -> sentence chunks -> ``speakable()`` -> TTS.

Normalisation needs whole phrases ("₹1.1 crore" can arrive split over tokens), so tokens are
buffered to a sentence boundary first. Each spoken sentence is also recorded in the turn's
``ReplyLog``, which is what barge-in truncation and the live transcript use.

This is the last processor before TTS, so it also keeps the TTS language in step with the
caller's language (``CallContext.language``): before each utterance whose language differs from
what the TTS was last set to, it pushes a ``TTSUpdateSettingsFrame``.
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
    TTSUpdateSettingsFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.services.settings import TTSSettings
from pipecat.transcriptions.language import Language

from mitra_human import speakable
from mitra_voice.call_context import CallContext
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
PIPECAT_LANGUAGE: dict[Lang, Language] = {
    "en": Language.EN_IN,
    "hi": Language.HI_IN,
    "te": Language.TE_IN,
}


_HAS_NUMBER = re.compile(r"[\d₹]")


def spoken_form(text: str, call_language: Lang) -> str:
    """What TTS is actually given for ``text``; pre-rendered phrases must use the same form."""
    return speakable(text, detect_lang(text, call_language))


def split_first_words(buffer: str, min_words: int) -> tuple[str, str] | None:
    """An early first chunk: the complete words of ``buffer`` once there are ``min_words``.

    Never cuts right after a word with a digit or ₹ ("₹65 | lakh", "10 | AM" would be read
    wrongly), and only at whitespace so no word is split.
    """
    if min_words <= 0 or not buffer or not buffer[-1].isspace():
        return None
    words = buffer.split()
    if len(words) < min_words or _HAS_NUMBER.search(words[-1]):
        return None
    return buffer.strip(), ""


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
        call: CallContext,
        tts_language: Lang,
        first_chunk_words: int = 0,
        on_sentence: TextCallback | None = None,
    ) -> None:
        super().__init__()
        self._first_chunk_words = first_chunk_words
        self._first_pending = False
        self._reply = reply
        self._call = call
        self._tts_language = tts_language
        self._on_sentence = on_sentence
        self._buffer = ""

    def _speak(self, text: str) -> str:
        # The reply's own script decides number words; Latin text falls back to English.
        return spoken_form(text, self._call.language)

    async def _sync_tts_language(self) -> None:
        if self._call.language != self._tts_language:
            self._tts_language = self._call.language
            delta = TTSSettings(language=PIPECAT_LANGUAGE[self._tts_language])
            await self.push_frame(TTSUpdateSettingsFrame(delta=delta))

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
            await self._sync_tts_language()
            self._buffer = ""
            self._first_pending = True
            self._reply.start()
            await self.push_frame(frame, direction)
        elif isinstance(frame, LLMTextFrame):
            self._buffer += frame.text
            sentences, self._buffer = split_sentences(self._buffer)
            if not sentences and self._first_pending:
                early = split_first_words(self._buffer, self._first_chunk_words)
                if early is not None:
                    sentences, self._buffer = [early[0]], early[1]
            for sentence in sentences:
                self._first_pending = False
                await self._emit(sentence)
        elif isinstance(frame, LLMFullResponseEndFrame):
            if self._buffer.strip():
                await self._emit(self._buffer.strip())
            self._buffer = ""
            await self.push_frame(frame, direction)
        elif isinstance(frame, TTSSpeakFrame):
            # Greeting and fillers: normalised too, but not part of the LLM reply.
            await self._sync_tts_language()
            await self.push_frame(
                TTSSpeakFrame(self._speak(frame.text), append_to_context=frame.append_to_context),
                direction,
            )
        else:
            if isinstance(frame, InterruptionFrame):
                self._buffer = ""
            await self.push_frame(frame, direction)
