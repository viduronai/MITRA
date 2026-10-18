"""A scripted stand-in for ``google.genai`` ``client.aio.models`` (no network)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from google.genai import types


def text_chunk(text: str) -> types.GenerateContentResponse:
    return types.GenerateContentResponse(
        candidates=[
            types.Candidate(content=types.Content(role="model", parts=[types.Part(text=text)]))
        ],
        usage_metadata=types.GenerateContentResponseUsageMetadata(
            prompt_token_count=1000, cached_content_token_count=800, candidates_token_count=20
        ),
    )


def call_chunk(fn: str, args: dict[str, Any]) -> types.GenerateContentResponse:
    part = types.Part(function_call=types.FunctionCall(name=fn, args=args))
    return types.GenerateContentResponse(
        candidates=[types.Candidate(content=types.Content(role="model", parts=[part]))]
    )


@dataclass
class Scripted:
    """One model response: its chunks, and an optional delay before the first one."""

    chunks: list[types.GenerateContentResponse]
    delay_s: float = 0.0
    error: Exception | None = None


@dataclass
class FakeModels:
    script: list[Scripted]
    requests: list[dict[str, Any]] = field(default_factory=list)

    async def generate_content_stream(
        self, *, model: str, contents: Any, config: Any
    ) -> AsyncIterator[Any]:
        self.requests.append({"model": model, "contents": list(contents), "config": config})
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


def say(*sentences: str, delay_s: float = 0.0) -> Scripted:
    return Scripted([text_chunk(s) for s in sentences], delay_s=delay_s)


def calls(*items: tuple[str, dict[str, Any]]) -> Scripted:
    return Scripted([call_chunk(name, args) for name, args in items])
