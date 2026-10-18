"""The conversational brain: one caller turn in, a spoken reply (streamed) plus tool actions out.

Shared by the live pipeline (``brain.llm``) and text mode (``text_sessions``), so the evals grade
the production brain. Per turn:

1. deterministic pre-check (``guardrails.pre_check``): emergencies and opt-outs never reach the
   LLM; medical-advice requests get a turn-level instruction;
2. Gemini, streamed, with the in-call tools executed locally (``tools.ToolExecutor``) in a loop;
   the static system prompt is identical across turns and calls of one employee so Gemini's
   implicit prefix cache applies, and everything per-turn (language, clock, tool log) rides on
   the caller's message instead;
3. sentence-level post-check (``guardrails.PostCheck``) before any text leaves the brain;
4. first-token timeout -> one retry (optionally on the slow model) -> apology + callback.
"""

from __future__ import annotations

import asyncio
import re
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

import structlog
from google.genai import types

from mitra_voice.brain.cues import BOOK_NOW, SEND_REPORT, booking_accepted, dob_given
from mitra_voice.brain.guardrails import PostCheck, pre_check, split_sentences
from mitra_voice.brain.language import CallerLanguage, base_language, reply_instruction
from mitra_voice.brain.tools import Clock, ToolExecutor, gemini_tools
from mitra_voice.pack import EmployeePack
from mitra_voice.prompt import Localized, build_prompt

log = structlog.get_logger(__name__)

Role = Literal["user", "assistant"]
MAX_SENTENCES = 2


class StreamingModels(Protocol):
    """The slice of ``google.genai.Client().aio.models`` the brain uses (faked in tests)."""

    async def generate_content_stream(
        self, *, model: str, contents: Any, config: Any
    ) -> AsyncIterator[Any]: ...


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
    thinking_level: str | None = "minimal"
    # Free-tier keys are rate limited: pace requests per model (0 = off) and, in text mode,
    # wait out 429s up to this long per request (live calls: 0, fail fast to the apology).
    max_rpm: int = 0
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


@dataclass
class Usage:
    prompt_tokens: int = 0
    cached_tokens: int = 0
    output_tokens: int = 0
    thought_tokens: int = 0
    requests: int = 0

    def add(self, meta: Any) -> None:
        self.requests += 1
        self.prompt_tokens += getattr(meta, "prompt_token_count", None) or 0
        self.cached_tokens += getattr(meta, "cached_content_token_count", None) or 0
        self.output_tokens += getattr(meta, "candidates_token_count", None) or 0
        self.output_tokens += getattr(meta, "response_token_count", None) or 0
        self.thought_tokens += getattr(meta, "thoughts_token_count", None) or 0


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
        models: StreamingModels,
        config: BrainConfig,
        pack: EmployeePack,
        *,
        localized: Localized | None = None,
        customer_memory: str | None = None,
        clock: Clock | None = None,
    ) -> None:
        self._models = models
        self.config = config
        self.pack = pack
        self.executor = ToolExecutor(pack, clock=clock) if clock else ToolExecutor(pack)
        self.post = PostCheck(pack)
        self.usage = Usage()
        self.system_prompt = build_prompt(
            pack, customer_memory, localized=localized
        ).system_prompt()
        self._thinking_level = config.thinking_level
        self._tools = gemini_tools()
        self._t0 = time.perf_counter()

    # --- prompt pieces --------------------------------------------------------------------------

    def _turn_note(self, lang: CallerLanguage, instruction: str | None) -> str:
        lines = [f"[reply language: {lang}] {reply_instruction(lang)}", self.executor.today_line()]
        tool_log = self.executor.log_lines()
        if tool_log:
            lines.append("Earlier tool results this call:\n" + "\n".join(tool_log))
        if instruction:
            lines.append(instruction)
        return "\n".join(lines)

    def _contents(self, history: Sequence[Message], caller_text: str, note: str) -> list[Any]:

        contents: list[Any] = []
        for m in history:
            role = "model" if m.role == "assistant" else "user"
            if m.text.strip():
                contents.append(types.Content(role=role, parts=[types.Part(text=m.text)]))
        user_text = f"{caller_text}\n\n({note})"
        contents.append(types.Content(role="user", parts=[types.Part(text=user_text)]))
        return contents

    def _config(self) -> Any:

        thinking = (
            types.ThinkingConfig(thinking_level=self._thinking_level)
            if self._thinking_level
            else None
        )
        return types.GenerateContentConfig(
            system_instruction=self.system_prompt,
            temperature=self.config.temperature,
            max_output_tokens=self.config.max_output_tokens,
            tools=self._tools,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            thinking_config=thinking,
        )

    # --- model calls ----------------------------------------------------------------------------

    async def _open(self, model: str, contents: list[Any], budget_s: float) -> tuple[Any, Any]:
        """Start a stream and wait, at most ``budget_s`` in total, for its first chunk."""

        async def first_chunk() -> tuple[Any, Any]:
            stream = await self._models.generate_content_stream(
                model=model, contents=contents, config=self._config()
            )
            iterator = stream.__aiter__()
            try:
                return iterator, await iterator.__anext__()
            except StopAsyncIteration:
                return iterator, None

        return await asyncio.wait_for(first_chunk(), timeout=budget_s)

    async def _request(self, model: str, contents: list[Any], budget_s: float) -> tuple[Any, Any]:
        """``_open`` with pacing, 429 back-off (bounded) and the thinking-level fallback."""
        waited = 0.0
        while True:
            await _pace(model, self.config.max_rpm)
            self._t0 = time.perf_counter()
            try:
                return await self._open(model, contents, budget_s)
            except TimeoutError:
                raise
            except Exception as exc:
                if self._thinking_level == "minimal" and "thinking" in str(exc).lower():
                    # Some models only accept a higher minimum thinking level.
                    self._thinking_level = "low"
                    continue
                delay = _rate_limit_delay(exc)
                if delay is None or waited + delay > self.config.max_rate_limit_wait_s:
                    raise
                log.info("brain.rate_limited", wait_s=round(delay, 1))
                await asyncio.sleep(delay)
                waited += delay

    async def _open_with_retry(
        self,
        contents: list[Any],
        result: TurnResult,
        first_round: bool,
        on_retry: Callable[[], Awaitable[None]] | None = None,
    ) -> tuple[Any, Any]:
        """First round: the 1.5 s first-token budget, then one retry (slow model if set) while
        the filler plays. Rounds after a tool call already had their filler: the long budget."""
        if not first_round:
            try:
                return await self._request(self.config.model, contents, self.config.retry_timeout_s)
            except TimeoutError:
                raise FirstTokenTimeoutError from None
        try:
            return await self._request(
                self.config.model, contents, self.config.first_token_timeout_s
            )
        except TimeoutError:
            log.warning("brain.first_token_timeout", model_slot="fast")
        except Exception as exc:
            if not _is_transient(exc):
                raise
            log.warning("brain.model_unavailable", detail=str(exc)[:120])
        result.retried = True
        if on_retry is not None:
            await on_retry()
        model = self.config.slow_model or self.config.model
        try:
            return await self._request(model, contents, self.config.retry_timeout_s)
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
        note = self._turn_note(lang, "\n".join(instructions) or None)
        contents = self._contents(history, caller_text, note)
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
                    contents, result, round_no == 0, on_retry
                )
                calls: list[Any] = []
                model_parts: list[Any] = []
                chunk = first
                usage = None
                while chunk is not None:
                    if result.first_token_ms is None:
                        result.first_token_ms = (time.perf_counter() - self._t0) * 1000
                    usage = getattr(chunk, "usage_metadata", None) or usage
                    for cand in getattr(chunk, "candidates", None) or []:
                        content = getattr(cand, "content", None)
                        for part in getattr(content, "parts", None) or []:
                            if getattr(part, "thought", False):
                                continue
                            model_parts.append(part)
                            if getattr(part, "function_call", None) is not None:
                                calls.append(part.function_call)
                            elif getattr(part, "text", None):
                                for sentence in take(part.text, final=False):
                                    yield sentence
                    try:
                        chunk = await asyncio.wait_for(
                            iterator.__anext__(), timeout=self.config.stream_idle_timeout_s
                        )
                    except StopAsyncIteration:
                        chunk = None
                if usage is not None:
                    self.usage.add(usage)
                if not calls:
                    break
                contents.append(_content("model", model_parts))
                responses = []
                for call in calls:
                    args = dict(call.args or {})
                    output = self.executor.execute(call.name, args)
                    result.actions.append(Action(call.name, args))
                    responses.append(_function_response(call, output))
                if self.executor.end_call:
                    result.end_call = True
                contents.append(_content("user", responses))
            for sentence in take("", final=True):
                yield sentence
        except (FirstTokenTimeoutError, TimeoutError):
            result.failed = True
            log.warning("brain.turn_failed", reason="timeout", round=round_no)
        except Exception as exc:
            result.failed = True
            log.warning("brain.turn_failed", reason=type(exc).__name__, detail=str(exc)[:200])

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

    async def turn(
        self, history: Sequence[Message], caller_text: str, lang: CallerLanguage
    ) -> TurnResult:
        result = TurnResult()
        async for _ in self.stream_turn(history, caller_text, lang, result):
            pass
        return result


_DONE: dict[str, str] = {
    "en": "Done, I've taken care of that.",
    "te": "సరే అండి, అది చేసేశాను.",
    "hi": "ठीक है, वो कर दिया है।",
}


_RETRY_DELAY = re.compile(r"retry(?:Delay)?['\"]?:\s*['\"]?(\d+(?:\.\d+)?)s", re.IGNORECASE)
_last_request: dict[str, float] = {}
_pace_lock = asyncio.Lock()


def _is_transient(exc: Exception) -> bool:
    """Server-side overload / internal errors: worth one retry (possibly on the slow model)."""
    text = str(exc)
    return any(code in text for code in ("503", "UNAVAILABLE", "500 ", "INTERNAL", "overloaded"))


def _rate_limit_delay(exc: Exception) -> float | None:
    """Seconds to wait for a 429 / RESOURCE_EXHAUSTED error, else None."""
    text = str(exc)
    if "429" not in text and "RESOURCE_EXHAUSTED" not in text:
        return None
    m = _RETRY_DELAY.search(text)
    return (float(m.group(1)) if m else 10.0) + 1.0


async def _pace(model: str, max_rpm: int) -> None:
    """Space requests to one model at least 60/max_rpm seconds apart (process-wide)."""
    if max_rpm <= 0:
        return
    async with _pace_lock:
        gap = 60.0 / max_rpm
        wait = _last_request.get(model, 0.0) + gap - time.monotonic()
        if wait > 0:
            await asyncio.sleep(wait)
        _last_request[model] = time.monotonic()


def _content(role: str, parts: list[Any]) -> Any:

    return types.Content(role=role, parts=parts)


def _function_response(call: Any, output: dict[str, Any]) -> Any:

    return types.Part(
        function_response=types.FunctionResponse(
            id=getattr(call, "id", None), name=call.name, response=output
        )
    )


__all__ = [
    "Action",
    "Brain",
    "BrainConfig",
    "FirstTokenTimeoutError",
    "Message",
    "StreamingModels",
    "TurnResult",
    "Usage",
    "filler_for",
]
