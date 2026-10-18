"""OpenAI-compatible chat-completions backend for the brain (Groq; any compatible endpoint).

Streaming text deltas pass straight through; tool-call deltas are accumulated by index and
emitted whole when the stream ends. Reasoning models' thoughts never reach the caller: separate
``reasoning`` deltas are ignored and inline ``<think>...</think>`` blocks are stripped.
"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator
from typing import Any, Protocol

from openai import AsyncOpenAI

from mitra_voice.brain.backend import (
    CallEvent,
    ChatEvent,
    ChatRequest,
    ChatTurn,
    TextEvent,
    ToolCall,
    UsageEvent,
)
from mitra_voice.brain.tools import openai_tools

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
_TRY_AGAIN = re.compile(r"try again in (?:(\d+)m)?(\d+(?:\.\d+)?)(ms|s)", re.IGNORECASE)


class ChatCompletions(Protocol):
    async def create(self, **params: Any) -> Any: ...


class _Chat(Protocol):
    @property
    def completions(self) -> ChatCompletions: ...


class OpenAICompatClient(Protocol):
    """The slice of ``openai.AsyncOpenAI`` used here (faked in tests)."""

    @property
    def chat(self) -> _Chat: ...


def messages_for(system: str, turns: tuple[ChatTurn, ...]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = [{"role": "system", "content": system}]
    for t in turns:
        if t.role == "user":
            out.append({"role": "user", "content": t.text})
        elif t.role == "assistant":
            msg: dict[str, Any] = {"role": "assistant", "content": t.text or None}
            if t.calls:
                msg["tool_calls"] = [
                    {
                        "id": c.id or f"call_{i}",
                        "type": "function",
                        "function": {"name": c.name, "arguments": json.dumps(c.args)},
                    }
                    for i, c in enumerate(t.calls)
                ]
            out.append(msg)
        else:
            for i, (c, result) in enumerate(t.results):
                out.append(
                    {
                        "role": "tool",
                        "tool_call_id": c.id or f"call_{i}",
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                )
    return out


class _ThinkFilter:
    """Drops ``<think>...</think>`` spans from a stream of text deltas."""

    def __init__(self) -> None:
        self._buf = ""
        self._inside = False

    def feed(self, text: str) -> str:
        self._buf += text
        out: list[str] = []
        while self._buf:
            if self._inside:
                end = self._buf.find("</think>")
                if end < 0:
                    self._buf = self._buf[-8:]  # keep a possible partial closing tag
                    return "".join(out)
                self._buf = self._buf[end + len("</think>") :]
                self._inside = False
            else:
                start = self._buf.find("<think>")
                if start < 0:
                    # Hold back a possible partial "<think" at the end.
                    cut = self._buf.rfind("<")
                    if cut >= 0 and "<think>".startswith(self._buf[cut:]):
                        out.append(self._buf[:cut])
                        self._buf = self._buf[cut:]
                    else:
                        out.append(self._buf)
                        self._buf = ""
                    return "".join(out)
                out.append(self._buf[:start])
                self._buf = self._buf[start + len("<think>") :]
                self._inside = True
        return "".join(out)

    def flush(self) -> str:
        rest, self._buf = ("" if self._inside else self._buf), ""
        return rest


class OpenAICompatBackend:
    def __init__(self, client: OpenAICompatClient, *, provider: str = "groq") -> None:
        self._client = client
        self.provider = provider
        self._tools = openai_tools()

    def params(self, request: ChatRequest) -> dict[str, Any]:
        params: dict[str, Any] = {
            "model": request.model,
            "messages": messages_for(request.system, request.turns),
            "tools": self._tools,
            "tool_choice": "auto",
            "temperature": request.temperature,
            "max_tokens": request.max_output_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if request.reasoning:
            params["reasoning_effort"] = request.reasoning
        return params

    async def stream(self, request: ChatRequest) -> AsyncIterator[ChatEvent]:
        response = await self._client.chat.completions.create(**self.params(request))

        async def events() -> AsyncIterator[ChatEvent]:
            pending: dict[int, dict[str, str]] = {}
            think = _ThinkFilter()
            async for chunk in response:
                usage = getattr(chunk, "usage", None)
                if usage is not None:
                    details = getattr(usage, "prompt_tokens_details", None)
                    yield UsageEvent(
                        prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
                        cached_tokens=getattr(details, "cached_tokens", 0) or 0,
                        output_tokens=getattr(usage, "completion_tokens", 0) or 0,
                    )
                for choice in getattr(chunk, "choices", None) or []:
                    delta = getattr(choice, "delta", None)
                    text = getattr(delta, "content", None)
                    if text:
                        visible = think.feed(text)
                        if visible:
                            yield TextEvent(visible)
                    for tc in getattr(delta, "tool_calls", None) or []:
                        slot = pending.setdefault(
                            getattr(tc, "index", 0) or 0, {"id": "", "name": "", "args": ""}
                        )
                        if getattr(tc, "id", None):
                            slot["id"] = tc.id
                        fn = getattr(tc, "function", None)
                        if fn is not None:
                            slot["name"] += getattr(fn, "name", None) or ""
                            slot["args"] += getattr(fn, "arguments", None) or ""
            rest = think.flush()
            if rest:
                yield TextEvent(rest)
            for _, slot in sorted(pending.items()):
                try:
                    args = json.loads(slot["args"]) if slot["args"].strip() else {}
                except json.JSONDecodeError:
                    args = {"_unparsed": slot["args"][:500]}
                yield CallEvent(
                    ToolCall(
                        name=slot["name"],
                        args=args if isinstance(args, dict) else {"value": args},
                        id=slot["id"] or None,
                    )
                )

        return events()

    def rate_limit_delay(self, exc: Exception) -> float | None:
        status = getattr(exc, "status_code", None)
        text = str(exc)
        if status != 429 and "429" not in text and "rate_limit" not in text.lower():
            return None
        headers = getattr(getattr(exc, "response", None), "headers", None) or {}
        retry_after = headers.get("retry-after") if hasattr(headers, "get") else None
        if retry_after:
            try:
                return float(retry_after) + 0.5
            except ValueError:
                pass
        m = _TRY_AGAIN.search(text)
        if m:
            seconds = float(m.group(2)) / (1000 if m.group(3).lower() == "ms" else 1)
            return int(m.group(1) or 0) * 60 + seconds + 0.5
        return 10.0

    def is_transient(self, exc: Exception) -> bool:
        status = getattr(exc, "status_code", None)
        if isinstance(status, int) and status >= 500:
            return True
        text = str(exc).lower()
        return any(c in text for c in ("503", "502", "over capacity", "overloaded", "internal"))

    def reasoning_fallback(self, level: str | None, exc: Exception) -> tuple[bool, str | None]:
        # Non-reasoning models reject reasoning_effort: drop it and retry once.
        if level and "reasoning" in str(exc).lower():
            return True, None
        return False, level


def groq_client(api_key: str) -> Any:
    return AsyncOpenAI(api_key=api_key, base_url=GROQ_BASE_URL)


__all__ = ["GROQ_BASE_URL", "OpenAICompatBackend", "OpenAICompatClient", "groq_client"]
