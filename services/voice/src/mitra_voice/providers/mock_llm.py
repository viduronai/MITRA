"""Mock LLM: answers deterministically from the employee pack's confirmed facts.

It never invents a fact: a question whose fact is missing gets a polite defer, mirroring the
global prompt rule. Tokens stream after a configurable time-to-first-token, and turns that would
need a tool (booking) wait an extra simulated tool latency, which is what the filler hook masks.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import Any

from pipecat.frames.frames import (
    Frame,
    LLMContextFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
)
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.frame_processor import FrameDirection
from pipecat.services.llm_service import LLMService
from pipecat.services.settings import LLMSettings

from mitra_voice.intents import Intent, classify
from mitra_voice.pack import EmployeePack, Fact, FactCategory
from mitra_voice.processors.reply import last_user_text

_STOPWORDS = frozenset(
    {"a", "an", "the", "is", "are", "what", "which", "your", "you", "for", "of", "to", "me"}
    | {"my", "i", "hi", "do", "does"}
)
_WORD = re.compile(r"[a-z0-9]+")
_TOKEN = re.compile(r"\S+\s*")

_DEFER: dict[Intent, str] = {
    "price": "Let me confirm the exact price with the team and message you on WhatsApp.",
    "timings": "Let me double-check the timings with the team and message you on WhatsApp.",
    "location": "I'll send you the exact location on WhatsApp right after this call.",
    "services": "Let me have the team share the full list with you on WhatsApp.",
    "unknown": "That's a good question. Let me confirm with the team and message you on WhatsApp.",
}
_CATEGORY: dict[Intent, FactCategory] = {
    "price": "prices",
    "timings": "timings",
    "location": "location",
    "services": "services",
}


@dataclass(frozen=True, slots=True)
class MockAnswer:
    text: str
    intent: Intent
    uses_tool: bool
    # Tool calls a real LLM would make this turn (names from TRD section 5's in-call tools).
    actions: tuple[str, ...] = ()
    end_call: bool = False


def _words(text: str) -> set[str]:
    return {w for w in _WORD.findall(text.lower()) if w not in _STOPWORDS}


def _best_fact(pack: EmployeePack, category: FactCategory, question: str) -> Fact | None:
    candidates = [f for f in pack.facts if f.category == category]
    if not candidates:
        return None
    asked = _words(question)
    # Highest key overlap wins; ties keep pack order (max() returns the first maximum).
    return max(candidates, key=lambda f: len(asked & _words(f.key)))


def _lc_first(key: str) -> str:
    """'Consultation fee' -> 'consultation fee', but '2 BHK price range' and 'OPD' stay."""
    if len(key) > 1 and key[0].isupper() and not key[1].isupper():
        return key[0].lower() + key[1:]
    return key


def _slot_for(question: str) -> str:
    q = question.lower()
    if "weekend" in q or "saturday" in q:
        return "Saturday at 11 AM"
    if "evening" in q:
        return "tomorrow at 6 PM"
    if "morning" in q:
        return "tomorrow at 10:30 AM"
    return "tomorrow at 11 AM"


def mock_answer(pack: EmployeePack, question: str) -> MockAnswer:
    intent = classify(question)
    if intent == "emergency":
        text = (
            "I'm connecting you to our staff right now. "
            "If it is life-threatening, please call 108 immediately."
        )
        return MockAnswer(text, intent, False, ("transfer_to_human", "alert_staff"))
    if intent == "opt_out":
        text = "Sorry for the trouble. I've noted that, and we won't call you again."
        return MockAnswer(text, intent, False, ("opt_out",), end_call=True)
    if intent == "booking":
        text = f"I checked the schedule and {_slot_for(question)} is free. Shall I book it?"
        if pack.behaviour.ask_for:
            text += f" Could you share {pack.behaviour.ask_for[0]}?"
        return MockAnswer(text, intent, True, ("check_availability",))
    if intent == "thanks":
        return MockAnswer(f"Thank you for calling {pack.business_name}!", intent, False)

    fact = _best_fact(pack, _CATEGORY[intent], question) if intent in _CATEGORY else None
    if fact is None:
        return MockAnswer(_DEFER[intent], intent, uses_tool=False)
    value = fact.value.rstrip(".")
    key = _lc_first(fact.key)
    if intent == "price":
        text = f"The {key} is {value}."
    elif intent == "timings":
        text = f"Our {key} are {value}."
    elif intent == "location":
        text = f"We're at {value}."
    elif "project" in key.lower():
        text = f"Right now we have {value}."
    else:
        text = f"We offer {value}."
    return MockAnswer(text[0].upper() + text[1:], intent, uses_tool=False)


class MockLLMService(LLMService):
    def __init__(
        self,
        pack: EmployeePack,
        *,
        ttft_ms: int = 250,
        token_ms: int = 20,
        tool_latency_ms: int = 600,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault(
            "settings",
            LLMSettings(
                model=None,
                system_instruction=None,
                temperature=None,
                max_tokens=None,
                top_p=None,
                top_k=None,
                frequency_penalty=None,
                presence_penalty=None,
                seed=None,
                filter_incomplete_user_turns=False,
                user_turn_completion_config=None,
            ),
        )
        super().__init__(**kwargs)
        self._pack = pack
        self._ttft_s = ttft_ms / 1000
        self._token_s = token_ms / 1000
        self._tool_s = tool_latency_ms / 1000

    def can_generate_metrics(self) -> bool:
        return True

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, LLMContextFrame):
            await self._respond(frame.context)
        else:
            await self.push_frame(frame, direction)

    async def _respond(self, context: LLMContext) -> None:
        answer = mock_answer(self._pack, last_user_text(context))
        await self.push_frame(LLMFullResponseStartFrame())
        await self.start_ttfb_metrics()
        # Interruptions cancel this task mid-sleep, like a real streaming request.
        await asyncio.sleep(self._ttft_s + (self._tool_s if answer.uses_tool else 0))
        await self.stop_ttfb_metrics()
        for token in _TOKEN.findall(answer.text):
            await self._push_llm_text(token)
            await asyncio.sleep(self._token_s)
        await self.push_frame(LLMFullResponseEndFrame())
