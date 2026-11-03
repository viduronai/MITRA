"""Intent planners and voice-note transcription, both behind small interfaces.

* ``RulesPlanner`` (default, tests): ``intents.parse``.
* ``LlmPlanner``: a free OpenAI-compatible chat endpoint (Groq, or Gemini's OpenAI endpoint)
  maps the owner's words to ONE intent as JSON. It never sees business data and never writes
  the answer, so it cannot invent numbers. Any failure falls back to the rules.
* ``WhisperTranscriber``: OpenAI-compatible ``/audio/transcriptions`` (Groq's free Whisper).
"""

from __future__ import annotations

import json
from typing import Any, Literal, Protocol, get_args

import httpx

from mitra_core.config import Settings
from mitra_core.logging import get_logger
from mitra_core.manager.intents import Intent, IntentName, detect_language, parse

log = get_logger(__name__)

INTENT_NAMES: tuple[str, ...] = get_args(IntentName)


class Planner(Protocol):
    async def plan(self, text: str) -> Intent: ...


class Transcriber(Protocol):
    async def transcribe(self, audio: bytes, mime: str) -> str | None: ...


class RulesPlanner:
    async def plan(self, text: str) -> Intent:
        return parse(text)


_PROMPT = f"""You route a business owner's message to ONE intent for their AI calling team.
The message may be Telugu, Hindi, English or a mix. Reply with ONLY a JSON object:
{{"intent": one of {list(INTENT_NAMES)},
 "period": "today" | "yesterday" | "week",
 "query": "search words, customer name or employee name, in the original script",
 "when": "callback time as said, e.g. 5 pm",
 "results": subset of ["interested","call_back","booked","missed","not_interested"],
 "day_offset": 0 or 1,
 "text": "for coach: the instruction itself"}}
summary = how did calls go; attention = what needs the owner; bookings = appointments/visits;
search = who called about a topic; customer = details of one customer; pause/resume an
employee; callback = call one customer back; call_list = call many people; coach = change how
an employee behaves ("next time offer Saturday first"); payments = who paid / what is pending /
how much was collected (text = "paid" | "pending" | "collected"); unknown = none of these.
Never answer the question yourself."""


class LlmPlanner:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout_s: float = 10.0,
    ) -> None:
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._key = api_key
        self._model = model
        self._transport = transport
        self._timeout = timeout_s

    async def plan(self, text: str) -> Intent:
        fallback = parse(text)
        try:
            data = await self._complete(text)
            return _to_intent(data, fallback)
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            log.warning("manager.planner_failed", error=type(exc).__name__)
            return fallback

    async def _complete(self, text: str) -> dict[str, Any]:
        body = {
            "model": self._model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": _PROMPT},
                {"role": "user", "content": text[:1000]},
            ],
        }
        async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
            res = await client.post(
                self._url, json=body, headers={"Authorization": f"Bearer {self._key}"}
            )
        res.raise_for_status()
        parsed = json.loads(res.json()["choices"][0]["message"]["content"])
        if not isinstance(parsed, dict):
            raise ValueError("not an object")
        return parsed


def _to_intent(data: dict[str, Any], fallback: Intent) -> Intent:
    name = data.get("intent")
    if name not in INTENT_NAMES:
        return fallback
    raw_period = data.get("period")
    period: Literal["today", "yesterday", "week"] = (
        "week" if raw_period == "week" else "yesterday" if raw_period == "yesterday" else "today"
    )
    results = [str(r) for r in data.get("results") or [] if isinstance(r, str)][:5]
    offset = data.get("day_offset")
    return Intent(
        name=name,
        lang=fallback.lang or detect_language(str(data.get("query") or "")),
        period=period,
        query=str(data.get("query") or "")[:80],
        when=str(data.get("when") or "")[:20],
        results=results or (["interested", "call_back"] if name == "call_list" else []),
        day_offset=1 if offset == 1 else 0,
        text=str(data.get("text") or fallback.text)[:200],
    )


class WhisperTranscriber:
    def __init__(self, base_url: str, api_key: str, model: str, *, timeout_s: float = 30.0) -> None:
        self._url = base_url.rstrip("/") + "/audio/transcriptions"
        self._key = api_key
        self._model = model
        self._timeout = timeout_s

    async def transcribe(self, audio: bytes, mime: str) -> str | None:
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                res = await client.post(
                    self._url,
                    headers={"Authorization": f"Bearer {self._key}"},
                    data={"model": self._model},
                    files={"file": ("voice.ogg", audio, mime)},
                )
            res.raise_for_status()
            return str(res.json().get("text") or "").strip() or None
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("manager.transcribe_failed", error=type(exc).__name__)
            return None


def get_planner(settings: Settings) -> Planner:
    if (
        settings.manager_llm == "llm"
        and settings.manager_llm_url
        and settings.manager_llm_api_key
        and settings.manager_llm_model
    ):
        return LlmPlanner(
            settings.manager_llm_url,
            settings.manager_llm_api_key.get_secret_value(),
            settings.manager_llm_model,
        )
    return RulesPlanner()


def get_transcriber(settings: Settings) -> Transcriber | None:
    if settings.transcribe_url and settings.transcribe_api_key and settings.transcribe_model:
        return WhisperTranscriber(
            settings.transcribe_url,
            settings.transcribe_api_key.get_secret_value(),
            settings.transcribe_model,
        )
    return None
