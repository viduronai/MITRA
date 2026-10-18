"""Eval-time response cache: an identical request (provider + model + prompt + transcript +
parameters) replays the recorded event stream instead of calling the LLM, so re-running
unchanged eval scenarios costs nothing. Works for every backend (Gemini, Groq).

Text mode only, opt-in with ``MITRA_LLM_CACHE_DIR``. Pair it with ``MITRA_BRAIN_FIXED_NOW`` so
the per-turn clock line (part of the request) is stable across runs. Errors and streams that
were not read to the end are never cached.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from mitra_voice.brain.backend import (
    CallEvent,
    ChatBackend,
    ChatEvent,
    ChatRequest,
    TextEvent,
    ToolCall,
    UsageEvent,
)


def request_key(provider: str, request: ChatRequest) -> str:
    payload = json.dumps(
        {"provider": provider, "request": dataclasses.asdict(request)},
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _encode(event: ChatEvent) -> str:
    if isinstance(event, TextEvent):
        data: dict[str, Any] = {"type": "text", "text": event.text}
    elif isinstance(event, CallEvent):
        data = {"type": "call", **dataclasses.asdict(event.call)}
    else:
        data = {"type": "usage", **dataclasses.asdict(event)}
    return json.dumps(data, ensure_ascii=False)


def _decode(line: str) -> ChatEvent:
    data = json.loads(line)
    kind = data.pop("type")
    if kind == "text":
        return TextEvent(data["text"])
    if kind == "call":
        return CallEvent(ToolCall(**data))
    return UsageEvent(**data)


class CachingBackend:
    """Wraps a backend; stores each completed stream as JSON lines of events."""

    def __init__(self, inner: ChatBackend, directory: Path) -> None:
        self._inner = inner
        self.provider = inner.provider
        self._dir = directory
        self._dir.mkdir(parents=True, exist_ok=True)
        self.hits = 0
        self.misses = 0

    async def stream(self, request: ChatRequest) -> AsyncIterator[ChatEvent]:
        path = self._dir / f"{request_key(self.provider, request)}.jsonl"
        if path.exists():
            self.hits += 1
            events = [_decode(x) for x in path.read_text(encoding="utf-8").splitlines() if x]

            async def replay() -> AsyncIterator[ChatEvent]:
                for event in events:
                    yield event

            return replay()

        self.misses += 1
        stream = await self._inner.stream(request)

        async def record() -> AsyncIterator[ChatEvent]:
            seen: list[str] = []
            async for event in stream:
                seen.append(_encode(event))
                yield event
            path.write_text("\n".join(seen), encoding="utf-8")

        return record()

    def rate_limit_delay(self, exc: Exception) -> float | None:
        return self._inner.rate_limit_delay(exc)

    def is_transient(self, exc: Exception) -> bool:
        return self._inner.is_transient(exc)

    def reasoning_fallback(self, level: str | None, exc: Exception) -> tuple[bool, str | None]:
        return self._inner.reasoning_fallback(level, exc)


__all__ = ["CachingBackend", "request_key"]
