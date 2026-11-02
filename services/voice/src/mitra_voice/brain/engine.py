"""The conversational brain: one caller turn in, a spoken reply (streamed) plus tool actions out.

Shared by the live pipeline (``brain.llm``) and text mode (``text_sessions``), so the evals grade
the production brain. Per turn:

1. deterministic pre-check (``guardrails.pre_check``): emergencies and opt-outs never reach the
   LLM; medical-advice requests get a turn-level instruction;
2. the LLM (any ``backend.ChatBackend``: Gemini, Groq), streamed, with the in-call tools
   executed locally (``tools.ToolExecutor``) in a loop; the static system prompt is identical
   across turns and calls of one employee so provider prefix caches apply, and everything
   per-turn (language, clock, tool log) rides on the caller's message instead;
3. sentence-level post-check (``guardrails.PostCheck``) before any text leaves the brain;
4. first-token timeout -> one retry (optionally on the slow model) -> apology + callback.
"""

from __future__ import annotations

import asyncio
import re
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

import structlog

from mitra_voice.brain.backend import (
    CallEvent,
    ChatBackend,
    ChatEvent,
    ChatRequest,
    ChatTurn,
    TextEvent,
    ToolCall,
    UsageEvent,
    pace,
)
from mitra_voice.brain.cues import (
    BOOK_NOW,
    HURRIED,
    SEND_REPORT,
    booking_accepted,
    dob_given,
    hurried,
)
from mitra_voice.brain.guardrails import PostCheck, pre_check, split_sentences
from mitra_voice.brain.language import CallerLanguage, base_language, reply_instruction
from mitra_voice.brain.tools import Clock, ToolExecutor
from mitra_voice.pack import EmployeePack
from mitra_voice.prompt import Localized, build_prompt

log = structlog.get_logger(__name__)

Role = Literal["user", "assistant"]
MAX_SENTENCES = 2
Opened = tuple[AsyncIterator[ChatEvent], ChatEvent | None]


@dataclass(frozen=True, slots=True)
class BrainConfig:
    model: str
    slow_model: str | None = None
    temperature: float = 0.3
    max_output_tokens: int = 256
    first_token_timeout_s: float = 1.5
    # The retry gets a longer window: the filler is already playing.
    retry_timeout_s: float = 4.0
    stream_idle_timeout_s: float = 8.0
    max_tool_rounds: int = 4
    # Gemini thinking_level / Groq reasoning_effort (None = the provider's default).
    reasoning: str | None = None
    # Free tiers are rate limited: pace requests per (provider, model) on requests and
    # estimated tokens per minute (0 = off) and, in text mode, wait out 429s up to this long
    # per request (live calls: 0, fail fast to the apology).
    max_rpm: int = 0
    max_tpm: int = 0
    max_rate_limit_wait_s: float = 0.0


@dataclass(frozen=True, slots=True)
class Message:
    role: Role
    text: str


@dataclass(frozen=True, slots=True)
class Action:
    name: str
    args: dict[str, Any] = field(default_factory=dict)


@dataclass
class TurnResult:
    text: str = ""
    actions: list[Action] = field(default_factory=list)
    end_call: bool = False
    first_token_ms: float | None = None
    guard: str | None = None
    violations: list[str] = field(default_factory=list)
    retried: bool = False
    failed: bool = False
    # "rate_limited" when the provider quota (e.g. a daily token cap) stopped the turn.
    error: str | None = None


@dataclass
class Usage:
    prompt_tokens: int = 0
    cached_tokens: int = 0
    output_tokens: int = 0
    thought_tokens: int = 0
    requests: int = 0

    def add(self, event: UsageEvent) -> None:
        self.requests += 1
        self.prompt_tokens += event.prompt_tokens
        self.cached_tokens += event.cached_tokens
        self.output_tokens += event.output_tokens
        self.thought_tokens += event.thought_tokens


class FirstTokenTimeoutError(TimeoutError):
    pass


_FILLER: dict[str, str] = {
    "en": "One moment please.",
    "te": "ఒక్క నిమిషం అండి.",
    "hi": "एक मिनट दीजिए।",
}
_APOLOGY: dict[str, str] = {
    "en": "Sorry, I'm having a little trouble on my side. Can our team call you back shortly?",
    "te": "క్షమించండి అండి, నా వైపు చిన్న సమస్య ఉంది. మా టీమ్ మీకు కొద్దిసేపట్లో కాల్ చేస్తారు, సరేనా?",
    "hi": "माफ़ कीजिए, मेरी तरफ़ थोड़ी दिक्कत है। क्या हमारी टीम आपको थोड़ी देर में कॉल कर ले?",
}


def filler_for(lang: CallerLanguage) -> str:
    return _FILLER[base_language(lang)]


class Brain:
    """One call's brain. Stateless about the conversation text (the caller passes the history,
    already truncated to what the caller heard); stateful about tools and usage."""

    def __init__(
        self,
        backend: ChatBackend,
        config: BrainConfig,
        pack: EmployeePack,
        *,
        localized: Localized | None = None,
        customer_memory: str | None = None,
        clock: Clock | None = None,
    ) -> None:
        self.backend = backend
        self.config = config
        self.pack = pack
        self.executor = ToolExecutor(pack, clock=clock) if clock else ToolExecutor(pack)
        self.post = PostCheck(pack)
        self.usage = Usage()
        self._localized = localized
        self._memory = customer_memory
        self._prompts: dict[str, str] = {}
        self._lang: CallerLanguage = pack.default_language
        self.system_prompt = self._system_for(self._lang)
        self._reasoning = config.reasoning
        self._t0 = time.perf_counter()

    def _system_for(self, lang: CallerLanguage) -> str:
        """The system prompt with localised fact wording for this caller's language only.

        One prompt per base language, so the prefix stays identical (cacheable) within a call.
        """
        base = base_language(lang)
        if base not in self._prompts:
            sections = build_prompt(
                self.pack,
                self._memory,
                localized=self._localized,
                localized_languages=() if base == "en" else (base,),
            )
            self._prompts[base] = sections.system_prompt()
        return self._prompts[base]

    # --- prompt pieces --------------------------------------------------------------------------

    def _turn_note(self, lang: CallerLanguage, instruction: str | None) -> str:
        lines = [f"[reply language: {lang}] {reply_instruction(lang)}", self.executor.today_line()]
        tool_log = self.executor.log_lines()
        if tool_log:
            lines.append("Earlier tool results this call:\n" + "\n".join(tool_log))
        if instruction:
            lines.append(instruction)
        return "\n".join(lines)

    def _turns(self, history: Sequence[Message], caller_text: str, note: str) -> list[ChatTurn]:
        turns = [ChatTurn(role=m.role, text=m.text) for m in history if m.text.strip()]
        turns.append(ChatTurn(role="user", text=f"{caller_text}\n\n({note})"))
        return turns

    def _request_for(self, model: str, turns: list[ChatTurn]) -> ChatRequest:
        return ChatRequest(
            model=model,
            system=self._system_for(self._lang),
            turns=tuple(turns),
            temperature=self.config.temperature,
            max_output_tokens=self.config.max_output_tokens,
            reasoning=self._reasoning,
        )

    # --- model calls ----------------------------------------------------------------------------

    async def _open(self, model: str, turns: list[ChatTurn], budget_s: float) -> Opened:
        """Start a stream and wait, at most ``budget_s`` in total, for its first event."""
        request = self._request_for(model, turns)

        async def first_event() -> Opened:
            iterator = (await self.backend.stream(request)).__aiter__()
            try:
                return iterator, await iterator.__anext__()
            except StopAsyncIteration:
                return iterator, None

        return await asyncio.wait_for(first_event(), timeout=budget_s)

    async def _request(self, model: str, turns: list[ChatTurn], budget_s: float) -> Opened:
        """``_open`` with pacing, 429 back-off (bounded) and the reasoning-level fallback."""
        waited = 0.0
        while True:
            await pace(
                self.backend.provider,
                model,
                self._request_for(model, turns).estimated_tokens(),
                max_rpm=self.config.max_rpm,
                max_tpm=self.config.max_tpm,
            )
            self._t0 = time.perf_counter()
            try:
                return await self._open(model, turns, budget_s)
            except TimeoutError:
                raise
            except Exception as exc:
                retry, level = self.backend.reasoning_fallback(self._reasoning, exc)
                if retry:
                    self._reasoning = level
                    continue
                delay = self.backend.rate_limit_delay(exc)
                if delay is None or waited + delay > self.config.max_rate_limit_wait_s:
                    raise
                log.info("brain.rate_limited", provider=self.backend.provider, wait_s=delay)
                await asyncio.sleep(delay)
                waited += delay

    async def _open_with_retry(
        self,
        turns: list[ChatTurn],
        result: TurnResult,
        first_round: bool,
        on_retry: Callable[[], Awaitable[None]] | None = None,
    ) -> Opened:
        """First round: the 1.5 s first-token budget, then one retry (slow model if set) while
        the filler plays. Rounds after a tool call already had their filler: the long budget."""
        if not first_round:
            try:
                return await self._request(self.config.model, turns, self.config.retry_timeout_s)
            except TimeoutError:
                raise FirstTokenTimeoutError from None
        try:
            return await self._request(self.config.model, turns, self.config.first_token_timeout_s)
        except TimeoutError:
            log.warning("brain.first_token_timeout", model_slot="fast")
        except Exception as exc:
            if not self.backend.is_transient(exc):
                raise
            log.warning("brain.model_unavailable", detail=str(exc)[:120])
        result.retried = True
        if on_retry is not None:
            await on_retry()
        model = self.config.slow_model or self.config.model
        try:
            return await self._request(model, turns, self.config.retry_timeout_s)
        except TimeoutError:
            raise FirstTokenTimeoutError from None

    async def stream_turn(
        self,
        history: Sequence[Message],
        caller_text: str,
        lang: CallerLanguage,
        result: TurnResult,
        *,
        on_retry: Callable[[], Awaitable[None]] | None = None,
    ) -> AsyncIterator[str]:
        """Yield checked reply sentences for one caller turn; ``result`` collects the rest."""
        self._lang = lang
        self.system_prompt = self._system_for(lang)
        started = time.perf_counter()
        self.post.caller_texts = [m.text for m in history if m.role == "user"] + [caller_text]

        hit = pre_check(caller_text, lang, self.pack)
        if hit is not None and hit.reply is not None:
            result.guard = hit.kind
            for name, args in hit.actions:
                self.executor.execute(name, args)
                result.actions.append(Action(name, args))
            result.end_call = hit.end_call
            result.first_token_ms = (time.perf_counter() - started) * 1000
            result.text = hit.reply
            yield hit.reply
            return
        medical = hit is not None and hit.kind == "medical"
        if medical:
            result.guard = "medical"
            for name, args in hit.actions if hit else ():
                self.executor.execute(name, args)
                result.actions.append(Action(name, args))

        instructions = [hit.turn_instruction] if hit and hit.turn_instruction else []
        last_reply = next((m.text for m in reversed(history) if m.role == "assistant"), None)
        if booking_accepted(last_reply, caller_text):
            instructions.append(BOOK_NOW)
        if dob_given(last_reply, caller_text):
            instructions.append(SEND_REPORT)
        if hurried(caller_text, [m.text for m in history if m.role == "user"]):
            instructions.append(HURRIED)
        note = self._turn_note(lang, "\n".join(instructions) or None)
        turns = self._turns(history, caller_text, note)
        emitted: list[str] = []
        pending = ""

        def take(text: str, *, final: bool) -> list[str]:
            nonlocal pending
            pending += text
            parts = split_sentences(pending)
            if not parts:
                return []
            done = parts if final else parts[:-1]
            if final:
                pending = ""
            else:
                for part in done:  # drop finished sentences, keep the raw tail (its spaces)
                    pending = pending.lstrip()
                    pending = pending[len(part) :] if pending.startswith(part) else parts[-1]
            out = []
            for sentence in done:
                if len(emitted) >= MAX_SENTENCES or "medical" in result.violations:
                    continue
                checked, found = self.post.apply(sentence, lang, medical_turn=medical)
                for v in found:
                    if v not in result.violations:
                        result.violations.append(v)
                if "medical" in found and emitted:
                    checked = split_sentences(checked)[0]
                emitted.append(checked)
                out.append(checked)
            return out

        round_no = 0
        try:
            for round_no in range(self.config.max_tool_rounds + 1):
                iterator, first = await self._open_with_retry(
                    turns, result, round_no == 0, on_retry
                )
                calls: list[ToolCall] = []
                spoken = ""
                event = first
                while event is not None:
                    if result.first_token_ms is None:
                        result.first_token_ms = (time.perf_counter() - self._t0) * 1000
                    if isinstance(event, TextEvent):
                        spoken += event.text
                        for sentence in take(event.text, final=False):
                            yield sentence
                    elif isinstance(event, CallEvent):
                        calls.append(event.call)
                    else:
                        self.usage.add(event)
                    try:
                        event = await asyncio.wait_for(
                            iterator.__anext__(), timeout=self.config.stream_idle_timeout_s
                        )
                    except StopAsyncIteration:
                        event = None
                if not calls:
                    break
                turns.append(ChatTurn(role="assistant", text=spoken, calls=tuple(calls)))
                results = []
                for call in calls:
                    output = self.executor.execute(call.name, call.args)
                    result.actions.append(Action(call.name, call.args))
                    results.append((call, output))
                if self.executor.end_call:
                    result.end_call = True
                turns.append(ChatTurn(role="tool", results=tuple(results)))
            for sentence in take("", final=True):
                yield sentence
        except (FirstTokenTimeoutError, TimeoutError):
            result.failed = True
            log.warning("brain.turn_failed", reason="timeout", round=round_no)
        except Exception as exc:
            result.failed = True
            if self.backend.rate_limit_delay(exc) is not None:
                result.error = "rate_limited"
            log.warning("brain.turn_failed", reason=type(exc).__name__, detail=str(exc)[:400])

        if result.failed or not emitted:
            if result.failed or not result.actions:
                apology = _APOLOGY[base_language(lang)]
                self.executor.execute("schedule_callback", {"topic": "call back after an error"})
                result.actions.append(Action("schedule_callback", {"topic": "error"}))
                emitted.append(apology)
                yield apology
            else:
                # Tools ran but the model said nothing: confirm briefly rather than go silent.
                done = _DONE[base_language(lang)]
                emitted.append(done)
                yield done
        result.text = " ".join(emitted)
        names = {a.name for a in result.actions}
        if not result.failed and _PROMISE.search(result.text) and not names & _FOLLOW_UP_TOOLS:
            # A spoken "the team will confirm / get back to you" must create the follow-up.
            args = {"topic": caller_text[:200]}
            self.executor.execute("schedule_callback", args)
            result.actions.append(Action("schedule_callback", args))

    async def turn(
        self, history: Sequence[Message], caller_text: str, lang: CallerLanguage
    ) -> TurnResult:
        result = TurnResult()
        async for _ in self.stream_turn(history, caller_text, lang, result):
            pass
        return result


_PROMISE = re.compile(
    r"confirm|get back to you|call you back|will (?:share|send|update)|"
    r"కన్ఫర్మ్|confirm చేసి|తెలియజేస్తా|చెప్తాను|చెబుతాను|కాల్ చేస్తా|"
    r"कन्फ़र्म|कन्फर्म|बता दूँगी|बता दूंगी|बता देंगे|कॉल कर|call कर",
    re.IGNORECASE,
)
_FOLLOW_UP_TOOLS = frozenset(
    {"schedule_callback", "transfer_to_human", "send_whatsapp_template", "book_slot", "reschedule"}
)

_DONE: dict[str, str] = {
    "en": "Done, I've taken care of that.",
    "te": "సరే అండి, అది చేసేశాను.",
    "hi": "ठीक है, वो कर दिया है।",
}


__all__ = [
    "Action",
    "Brain",
    "BrainConfig",
    "FirstTokenTimeoutError",
    "Message",
    "TurnResult",
    "Usage",
    "filler_for",
]
