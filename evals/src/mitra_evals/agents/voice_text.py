"""``voice-text``: text-mode hook for services/voice (contract in :mod:`mitra_evals.agents.base`).

* ``MITRA_VOICE_TEXT_ENTRYPOINT="pkg.module:factory"``: in-process; ``factory()`` returns an
  :class:`~mitra_evals.agents.base.AgentUnderTest`.
* ``MITRA_VOICE_TEXT_URL``: the HTTP contract (``/v1/text-sessions``).
"""

from __future__ import annotations

import importlib
import os
from typing import Any, cast

import httpx

from mitra_evals.agents.base import (
    AgentReply,
    AgentUnavailableError,
    AgentUnderTest,
    CallContext,
    ConversationSession,
)
from mitra_evals.schema import EmployeePack


class _HttpSession:
    def __init__(self, http: httpx.AsyncClient, pack: EmployeePack, context: CallContext) -> None:
        self._http, self._pack, self._context = http, pack, context
        self._id: str | None = None

    async def start(self) -> AgentReply:
        resp = await self._http.post(
            "/v1/text-sessions",
            json={"pack": self._pack.model_dump(mode="json"), "context": self._context.to_json()},
        )
        resp.raise_for_status()
        body: dict[str, Any] = resp.json()
        self._id = str(body["session_id"])
        return AgentReply.from_json(body["reply"])

    async def send(self, caller_text: str, *, interrupt: bool = False) -> AgentReply:
        if self._id is None:
            raise RuntimeError("send() before start()")
        resp = await self._http.post(
            f"/v1/text-sessions/{self._id}/turns",
            json={"text": caller_text, "interrupt": interrupt},
        )
        resp.raise_for_status()
        return AgentReply.from_json(resp.json())

    async def close(self) -> None:
        try:
            if self._id is not None:
                await self._http.delete(f"/v1/text-sessions/{self._id}")
        finally:
            await self._http.aclose()


class _HttpVoiceAgent:
    name = "voice-text"

    def __init__(self, url: str, timeout: float) -> None:
        self._url, self._timeout = url, timeout

    async def open(self, pack: EmployeePack, context: CallContext) -> ConversationSession:
        http = httpx.AsyncClient(base_url=self._url, timeout=self._timeout)
        return _HttpSession(http, pack, context)


def voice_text_agent() -> AgentUnderTest:
    entrypoint = os.environ.get("MITRA_VOICE_TEXT_ENTRYPOINT")
    if entrypoint:
        module_name, _, attr = entrypoint.partition(":")
        try:
            factory = getattr(importlib.import_module(module_name), attr or "text_mode_agent")
        except (ImportError, AttributeError) as exc:
            raise AgentUnavailableError(f"cannot load {entrypoint!r}: {exc}") from exc
        return cast(AgentUnderTest, factory())
    url = os.environ.get("MITRA_VOICE_TEXT_URL")
    if url:
        return _HttpVoiceAgent(url, float(os.environ.get("MITRA_VOICE_TEXT_TIMEOUT", "30")))
    raise AgentUnavailableError(
        "voice-text needs MITRA_VOICE_TEXT_ENTRYPOINT (module:factory) or MITRA_VOICE_TEXT_URL; "
        "the voice service's text mode is not wired up yet"
    )
