"""Provider-neutral chat streaming for the brain: the engine speaks only these types, and one
backend per provider (``gemini_backend``, ``openai_backend`` for Groq) translates.

A request is the system prompt + a neutral transcript (user text, assistant text + tool calls,
tool results). A response is a stream of events: text deltas, complete tool calls, usage.
Rate limits are paced per (provider, model) with a rolling one-minute window on requests and
estimated tokens; 429s are classified by each backend (retry-after / retryDelay).
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

# The 11 in-call tool declarations, as counted by providers (approx.).
TOOL_TOKENS = 800


@dataclass(frozen=True, slots=True)
class ToolCall:
    name: str
    args: dict[str, Any] = field(default_factory=dict)
    id: str | None = None
    # Provider extras needed to send the call back (e.g. a Gemini part's thought signature),
    # JSON-serialisable so the eval cache can store it.
    raw: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class ChatTurn:
    role: Literal["user", "assistant", "tool"]
    text: str = ""
    calls: tuple[ToolCall, ...] = ()
    results: tuple[tuple[ToolCall, dict[str, Any]], ...] = ()


@dataclass(frozen=True, slots=True)
class ChatRequest:
    model: str
    system: str
    turns: tuple[ChatTurn, ...]
    temperature: float
    max_output_tokens: int
    # Gemini thinking_level / Groq reasoning_effort; None = the provider's default.
    reasoning: str | None = None

    def estimated_tokens(self) -> int:
        """Rough prompt + completion size for TPM pacing (Indic text: ~3 chars per token),
        plus the tool declarations every request carries."""
        chars = len(self.system) + sum(
            len(t.text) + sum(len(str(r)) for _, r in t.results) for t in self.turns
        )
        return chars // 3 + TOOL_TOKENS + self.max_output_tokens


@dataclass(frozen=True, slots=True)
class TextEvent:
    text: str


@dataclass(frozen=True, slots=True)
class CallEvent:
    call: ToolCall


@dataclass(frozen=True, slots=True)
class UsageEvent:
    prompt_tokens: int = 0
    cached_tokens: int = 0
    output_tokens: int = 0
    thought_tokens: int = 0


ChatEvent = TextEvent | CallEvent | UsageEvent


class ChatBackend(Protocol):
    """One LLM provider. ``stream`` sends the request; iterating yields its events."""

    provider: str

    async def stream(self, request: ChatRequest) -> AsyncIterator[ChatEvent]: ...

    def rate_limit_delay(self, exc: Exception) -> float | None:
        """Seconds to wait before retrying a rate-limited request, else None."""
        ...

    def is_transient(self, exc: Exception) -> bool:
        """A server-side overload / internal error, worth one retry."""
        ...

    def reasoning_fallback(self, level: str | None, exc: Exception) -> tuple[bool, str | None]:
        """(retry?, new level) when the provider rejected the reasoning setting."""
        ...


# --- pacing ---------------------------------------------------------------------------------------


@dataclass
class _Window:
    requests: deque[float] = field(default_factory=deque)
    tokens: deque[tuple[float, int]] = field(default_factory=deque)


_windows: dict[tuple[str, str], _Window] = {}
_lock = asyncio.Lock()


async def pace(provider: str, model: str, tokens: int, *, max_rpm: int, max_tpm: int) -> None:
    """Wait until one more request (of ~``tokens``) fits the per-minute limits (0 = no limit).

    Process-wide per (provider, model), so concurrent eval sessions share the budget.
    """
    if max_rpm <= 0 and max_tpm <= 0:
        return
    async with _lock:
        window = _windows.setdefault((provider, model), _Window())
        while True:
            now = time.monotonic()
            while window.requests and now - window.requests[0] >= 60:
                window.requests.popleft()
            while window.tokens and now - window.tokens[0][0] >= 60:
                window.tokens.popleft()
            waits = [0.0]
            if max_rpm > 0 and len(window.requests) >= max_rpm:
                waits.append(60 - (now - window.requests[0]))
            used = sum(n for _, n in window.tokens)
            if max_tpm > 0 and window.tokens and used + tokens > max_tpm:
                waits.append(60 - (now - window.tokens[0][0]))
            wait = max(waits)
            if wait <= 0:
                break
            await asyncio.sleep(wait + 0.05)
        window.requests.append(time.monotonic())
        window.tokens.append((time.monotonic(), tokens))


def reset_pacing() -> None:
    _windows.clear()


__all__ = [
    "CallEvent",
    "ChatBackend",
    "ChatEvent",
    "ChatRequest",
    "ChatTurn",
    "TextEvent",
    "ToolCall",
    "UsageEvent",
    "pace",
    "reset_pacing",
]
