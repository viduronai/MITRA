"""Eval-time response cache: an identical request (model + config + contents) replays the
recorded stream instead of calling Gemini, so re-running unchanged eval scenarios costs nothing.

Text mode only, opt-in with ``MITRA_LLM_CACHE_DIR``. Pair it with ``MITRA_BRAIN_FIXED_NOW`` so
the per-turn clock line (part of the request) is stable across runs. Errors are never cached.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import structlog
from google.genai import types

from mitra_voice.brain.engine import StreamingModels

log = structlog.get_logger(__name__)


def _dump(value: Any) -> Any:
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        return dump(mode="json", exclude_none=True)
    if isinstance(value, list | tuple):
        return [_dump(v) for v in value]
    return value


def request_key(model: str, contents: Any, config: Any) -> str:
    payload = json.dumps(
        {"model": model, "contents": _dump(contents), "config": _dump(config)},
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class CachingModels:
    """Wraps ``client.aio.models``; stores each completed stream as JSON lines of chunks."""

    def __init__(self, inner: StreamingModels, directory: Path) -> None:
        self._inner = inner
        self._dir = directory
        self._dir.mkdir(parents=True, exist_ok=True)
        self.hits = 0
        self.misses = 0

    async def generate_content_stream(
        self, *, model: str, contents: Any, config: Any
    ) -> AsyncIterator[Any]:

        path = self._dir / f"{request_key(model, contents, config)}.jsonl"
        if path.exists():
            self.hits += 1
            lines = path.read_text(encoding="utf-8").splitlines()
            chunks = [types.GenerateContentResponse.model_validate_json(x) for x in lines if x]

            async def replay() -> AsyncIterator[Any]:
                for chunk in chunks:
                    yield chunk

            return replay()

        self.misses += 1
        stream = await self._inner.generate_content_stream(
            model=model, contents=contents, config=config
        )

        async def record() -> AsyncIterator[Any]:
            seen: list[str] = []
            async for chunk in stream:
                seen.append(chunk.model_dump_json(exclude_none=True))
                yield chunk
            # Only a fully consumed stream is cached (timeouts / errors never are).
            path.write_text("\n".join(seen), encoding="utf-8")

        return record()


__all__ = ["CachingModels", "request_key"]
