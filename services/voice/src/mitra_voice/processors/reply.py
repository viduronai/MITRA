"""What the assistant meant to say this turn vs. what the caller actually heard (barge-in)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import cast

from pipecat.frames.frames import Frame, TTSTextFrame
from pipecat.processors.aggregators.llm_context import LLMContext, LLMContextMessage
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from mitra_human import truncate_to_heard

_NORMALISE = re.compile(r"[^\w]+")


def _norm(word: str) -> str:
    return _NORMALISE.sub("", word.lower())


@dataclass
class ReplyLog:
    """The spoken (normalised) reply of the current assistant turn and how much was played."""

    parts: list[str] = field(default_factory=list)
    words_played: int = 0
    active: bool = False

    def start(self) -> None:
        self.parts.clear()
        self.words_played = 0
        self.active = True

    def add(self, spoken: str) -> None:
        self.parts.append(spoken)

    @property
    def text(self) -> str:
        return " ".join(self.parts)

    @property
    def words(self) -> list[str]:
        return self.text.split()

    def on_word_played(self, word: str) -> None:
        """Advance only on the reply's next expected word, so filler/greeting words don't count."""
        words = self.words
        n = self.words_played
        if self.active and n < len(words) and _norm(words[n]) == _norm(word):
            self.words_played += 1

    def heard(self) -> str:
        return truncate_to_heard(self.text, self.words_played)

    def finish(self) -> None:
        self.active = False


class HeardTracker(FrameProcessor):
    """Placed right after ``transport.output()``: TTS word frames leave the output transport in
    step with playback, so each one passing here is a word the caller actually heard."""

    def __init__(self, reply: ReplyLog) -> None:
        super().__init__()
        self._reply = reply

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, TTSTextFrame) and direction == FrameDirection.DOWNSTREAM:
            for word in frame.text.split():
                self._reply.on_word_played(word)
        await self.push_frame(frame, direction)


def apply_heard_to_context(context: LLMContext, heard: str) -> bool:
    """Rewrite the last assistant message to what was heard (drop it if nothing was).

    Returns True if the context changed. Called when an assistant turn stops interrupted, so
    the next LLM turn knows exactly what the caller heard (TRD §5 barge-in).
    """
    messages = list(context.get_messages())
    for i in range(len(messages) - 1, -1, -1):
        message = messages[i]
        if not isinstance(message, dict) or message.get("role") != "assistant":
            continue
        if message.get("content") == heard:
            return False
        if heard:
            messages[i] = cast(LLMContextMessage, {**message, "content": heard})
        else:
            del messages[i]
        context.set_messages(messages)
        return True
    return False


def last_user_text(context: LLMContext) -> str:
    for message in reversed(context.get_messages()):
        if not isinstance(message, dict) or message.get("role") != "user":
            continue
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return " ".join(str(part.get("text", "")) for part in content if isinstance(part, dict))
    return ""
