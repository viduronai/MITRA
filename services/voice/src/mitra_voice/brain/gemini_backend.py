"""Gemini (``google.genai``) backend for the brain."""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from typing import Any, Protocol

from google.genai import types

from mitra_voice.brain.backend import (
    CallEvent,
    ChatEvent,
    ChatRequest,
    ChatTurn,
    TextEvent,
    ToolCall,
    UsageEvent,
)
from mitra_voice.brain.tools import gemini_tools

_RETRY_DELAY = re.compile(r"retry(?:Delay)?['\"]?:\s*['\"]?(\d+(?:\.\d+)?)s", re.IGNORECASE)


class StreamingModels(Protocol):
    """The slice of ``google.genai.Client().aio.models`` used here (faked in tests)."""

    async def generate_content_stream(
        self, *, model: str, contents: Any, config: Any
    ) -> AsyncIterator[Any]: ...


def _contents(turns: tuple[ChatTurn, ...]) -> list[types.Content]:
    out: list[types.Content] = []
    for t in turns:
        if t.role == "user":
            out.append(types.Content(role="user", parts=[types.Part(text=t.text)]))
        elif t.role == "assistant":
            parts = [types.Part(text=t.text)] if t.text else []
            for c in t.calls:
                if c.raw:
                    parts.append(types.Part.model_validate(c.raw))
                else:
                    fc = types.FunctionCall(name=c.name, args=c.args, id=c.id)
                    parts.append(types.Part(function_call=fc))
            if parts:
                out.append(types.Content(role="model", parts=parts))
        else:
            parts = [
                types.Part(
                    function_response=types.FunctionResponse(id=c.id, name=c.name, response=r)
                )
                for c, r in t.results
            ]
            out.append(types.Content(role="user", parts=parts))
    return out


class GeminiBackend:
    provider = "gemini"

    def __init__(self, models: StreamingModels) -> None:
        self._models = models
        self._tools = gemini_tools()

    def config(self, request: ChatRequest) -> types.GenerateContentConfig:
        thinking = (
            types.ThinkingConfig(thinking_level=request.reasoning) if request.reasoning else None
        )
        return types.GenerateContentConfig(
            system_instruction=request.system,
            temperature=request.temperature,
            max_output_tokens=request.max_output_tokens,
            tools=self._tools,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            thinking_config=thinking,
        )

    async def stream(self, request: ChatRequest) -> AsyncIterator[ChatEvent]:
        response = await self._models.generate_content_stream(
            model=request.model, contents=_contents(request.turns), config=self.config(request)
        )

        async def events() -> AsyncIterator[ChatEvent]:
            usage: Any = None
            async for chunk in response:
                usage = getattr(chunk, "usage_metadata", None) or usage
                for cand in getattr(chunk, "candidates", None) or []:
                    content = getattr(cand, "content", None)
                    for part in getattr(content, "parts", None) or []:
                        if getattr(part, "thought", False):
                            continue
                        fc = getattr(part, "function_call", None)
                        if fc is not None:
                            raw = part.model_dump(mode="json", exclude_none=True)
                            call = ToolCall(fc.name or "", dict(fc.args or {}), fc.id, raw)
                            yield CallEvent(call)
                        elif getattr(part, "text", None):
                            yield TextEvent(part.text)
            if usage is not None:
                yield UsageEvent(
                    prompt_tokens=usage.prompt_token_count or 0,
                    cached_tokens=usage.cached_content_token_count or 0,
                    output_tokens=usage.candidates_token_count or 0,
                    thought_tokens=usage.thoughts_token_count or 0,
                )

        return events()

    def rate_limit_delay(self, exc: Exception) -> float | None:
        text = str(exc)
        if "429" not in text and "RESOURCE_EXHAUSTED" not in text:
            return None
        m = _RETRY_DELAY.search(text)
        return (float(m.group(1)) if m else 10.0) + 1.0

    def is_transient(self, exc: Exception) -> bool:
        text = str(exc)
        return any(c in text for c in ("503", "UNAVAILABLE", "500 ", "INTERNAL", "overloaded"))

    def reasoning_fallback(self, level: str | None, exc: Exception) -> tuple[bool, str | None]:
        # Some models only accept a higher minimum thinking level than "minimal".
        if level == "minimal" and "thinking" in str(exc).lower():
            return True, "low"
        return False, level


__all__ = ["GeminiBackend", "StreamingModels"]
