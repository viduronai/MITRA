"""A scripted stand-in for ``openai.AsyncOpenAI`` chat completions (Groq), no network."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any


def text(content: str) -> SimpleNamespace:
    delta = SimpleNamespace(content=content, tool_calls=None)
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta)], usage=None)


def tool_delta(
    index: int, *, id: str | None = None, name: str | None = None, args: str = ""
) -> SimpleNamespace:
    call = SimpleNamespace(index=index, id=id, function=SimpleNamespace(name=name, arguments=args))
    delta = SimpleNamespace(content=None, tool_calls=[call])
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta)], usage=None)


def usage(prompt: int = 1200, cached: int = 0, completion: int = 30) -> SimpleNamespace:
    details = SimpleNamespace(cached_tokens=cached)
    return SimpleNamespace(
        choices=[],
        usage=SimpleNamespace(
            prompt_tokens=prompt, completion_tokens=completion, prompt_tokens_details=details
        ),
    )


@dataclass
class Step:
    chunks: list[SimpleNamespace]
    delay_s: float = 0.0
    error: Exception | None = None


class RateLimitedError(Exception):
    """Shaped like ``openai.RateLimitError`` (status_code + response.headers)."""

    status_code = 429

    def __init__(self, retry_after: str | None = None, message: str = "rate_limit_exceeded"):
        super().__init__(message)
        headers = {"retry-after": retry_after} if retry_after else {}
        self.response = SimpleNamespace(headers=headers)


@dataclass
class FakeCompletions:
    script: list[Step]
    requests: list[dict[str, Any]] = field(default_factory=list)

    async def create(self, **params: Any) -> AsyncIterator[Any]:
        self.requests.append(params)
        if not self.script:
            raise AssertionError("unexpected model request")
        step = self.script.pop(0)
        if step.error is not None:
            raise step.error

        async def gen() -> AsyncIterator[Any]:
            if step.delay_s:
                await asyncio.sleep(step.delay_s)
            for chunk in step.chunks:
                yield chunk

        return gen()


class FakeOpenAI:
    def __init__(self, script: list[Step]) -> None:
        self.completions = FakeCompletions(script)
        self.chat = SimpleNamespace(completions=self.completions)

    @property
    def requests(self) -> list[dict[str, Any]]:
        return self.completions.requests
