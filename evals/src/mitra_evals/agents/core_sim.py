"""``core-sim``: the simulated test call in services/core (``mitra_core.simulation``).

That simulation is not interactive: it writes a whole scripted transcript (greeting, three
caller questions with answers from confirmed facts, a booking offer, a goodbye). This adapter
builds that transcript once per call and answers each eval caller turn with the scripted
employee reply whose question best matches it (keyword overlap), falling back to the next
unused one in script order. It never emits actions; the simulation has none.

Modes:
* in-process (preferred): ``mitra_core`` importable (the ``core`` dependency group). Uses the
  eval's pack facts.
* HTTP: ``MITRA_CORE_URL`` + ``MITRA_CORE_TOKEN`` (owner/manager JWT with ``business_id``) +
  ``MITRA_CORE_EMPLOYEE_ID``. Creates ``POST /v1/test-calls`` and polls until completed. Uses
  the facts stored for that business in core's database, NOT the eval pack.
"""

from __future__ import annotations

import asyncio
import importlib
import os
from typing import Any

import httpx

from mitra_evals.agents.base import (
    AgentReply,
    AgentUnavailableError,
    CallContext,
    ConversationSession,
)
from mitra_evals.schema import EmployeePack, base_language
from mitra_evals.text import words

_STOP = {"the", "is", "are", "what", "you", "your", "and", "for", "can", "how", "hi", "do"}


def _words(text: str) -> set[str]:
    return {w for w in words(text) if len(w) > 2 and w not in _STOP}


class _ScriptSession:
    def __init__(self, transcript: list[dict[str, Any]]) -> None:
        self._greeting = ""
        self._pairs: list[tuple[str, str]] = []  # (scripted caller line, employee reply)
        self._closing = "Thank you for calling!"
        lines = [(str(t["speaker"]), str(t["text"])) for t in transcript]
        if lines and lines[0][0] == "employee":
            self._greeting = lines[0][1]
            lines = lines[1:]
        caller: str | None = None
        for speaker, text in lines:
            if speaker == "caller":
                caller = text
            elif caller is not None:
                self._pairs.append((caller, text))
                caller = None
            else:
                self._closing = text
        self._used: set[int] = set()

    async def start(self) -> AgentReply:
        return AgentReply(text=self._greeting)

    async def send(self, caller_text: str, *, interrupt: bool = False) -> AgentReply:
        free = [i for i in range(len(self._pairs)) if i not in self._used]
        if not free:
            return AgentReply(text=self._closing)
        said = _words(caller_text)
        best = max(free, key=lambda i: len(said & _words(self._pairs[i][0])))
        if not said & _words(self._pairs[best][0]):
            best = free[0]
        self._used.add(best)
        return AgentReply(text=self._pairs[best][1])

    async def close(self) -> None:
        return None


def _load_simulation() -> tuple[Any, Any, Any] | None:
    try:
        simulation = importlib.import_module("mitra_core.simulation")
        enums = importlib.import_module("mitra_core.models.enums")
    except ImportError:
        return None
    return simulation, enums.FactCategory, enums.Industry


def _build_in_process(
    sim: tuple[Any, Any, Any], pack: EmployeePack, context: CallContext
) -> list[dict[str, Any]]:
    simulation, fact_category, industry = sim
    greeting = getattr(pack.greeting, context.direction)[base_language(context.language)]
    script = simulation.build_transcript(
        business_name=pack.business_name,
        industry=industry(pack.industry),
        employee_name=pack.employee_name,
        greeting=greeting,
        ask_for=list(pack.behaviour.ask_for),
        facts=[(fact_category(f.category), f.label, f.value) for f in pack.facts],
    )
    return list(script.transcript)


class CoreSimAgent:
    name = "core-sim"

    def __init__(self) -> None:
        self._sim = _load_simulation()
        self._url = os.environ.get("MITRA_CORE_URL")
        if self._sim is None and not self._url:
            raise AgentUnavailableError(
                "core-sim needs mitra_core importable (uv sync --group core) or MITRA_CORE_URL "
                "with MITRA_CORE_TOKEN and MITRA_CORE_EMPLOYEE_ID"
            )

    @property
    def mode(self) -> str:
        return "in-process" if self._sim is not None else "http"

    async def open(self, pack: EmployeePack, context: CallContext) -> ConversationSession:
        if self._sim is not None:
            return _ScriptSession(_build_in_process(self._sim, pack, context))
        return _ScriptSession(await self._fetch_over_http())

    async def _fetch_over_http(self) -> list[dict[str, Any]]:
        token = os.environ.get("MITRA_CORE_TOKEN")
        employee_id = os.environ.get("MITRA_CORE_EMPLOYEE_ID")
        if not (token and employee_id):
            raise AgentUnavailableError(
                "HTTP mode needs MITRA_CORE_TOKEN and MITRA_CORE_EMPLOYEE_ID"
            )
        headers = {"Authorization": f"Bearer {token}"}
        async with httpx.AsyncClient(base_url=str(self._url), headers=headers, timeout=15) as http:
            created = await http.post("/v1/test-calls", json={"employee_id": employee_id})
            created.raise_for_status()
            call_id = created.json()["id"]
            for _ in range(30):
                got = await http.get(f"/v1/test-calls/{call_id}")
                got.raise_for_status()
                body = got.json()
                if body["status"] == "completed":
                    return list(body["transcript"])
                await asyncio.sleep(0.5)
        raise RuntimeError(f"test call {call_id} did not complete in time")
