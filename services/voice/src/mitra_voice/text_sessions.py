"""Text-mode sessions for mitra-evals (HTTP contract in evals/src/mitra_evals/agents/base.py).

One eval scenario = one session: greeting, then caller turns, with tool calls surfaced as
``actions``. The brain is the same deterministic pack-grounded responder as the mock LLM.
TODO(llm): route through the real live-turn LLM (same prompt sections) once MITRA_LLM=anthropic
is wired with tools, so evals grade the production brain rather than the mock.
"""

from __future__ import annotations

import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from mitra_human import truncate_to_heard
from mitra_voice.pack import EmployeePack, Lang, pack_from_dict
from mitra_voice.prompt import greeting_for
from mitra_voice.providers.mock_llm import mock_answer

MAX_TEXT_SESSIONS = 200
EvalLanguage = Literal["en", "hi", "te", "te-en", "hi-en"]


class TextContext(BaseModel):
    model_config = ConfigDict(extra="ignore")
    scenario_id: str = Field(default="adhoc", max_length=200)
    language: EvalLanguage = "en"
    direction: Literal["inbound", "outbound"] = "inbound"
    caller_name: str | None = Field(default=None, max_length=100)


class TextSessionIn(BaseModel):
    pack: dict[str, Any]
    context: TextContext = Field(default_factory=TextContext)


class TurnIn(BaseModel):
    text: str = Field(min_length=1, max_length=2_000)
    interrupt: bool = False


def pack_from_eval(data: dict[str, Any]) -> EmployeePack:
    """Map the evals pack schema onto ours (validated by ``pack_from_dict``)."""
    languages = list(data.get("languages") or [])
    default = data.get("default_language")
    if default in languages:
        languages.remove(default)
        languages.insert(0, default)
    behaviour = data.get("behaviour") or {}
    escalate_to = behaviour.get("escalate_to")
    return pack_from_dict(
        {
            "business_id": str(data.get("id", "eval")),
            "business_name": data.get("business_name"),
            "industry": data.get("industry"),
            "employee_id": f"{data.get('id', 'eval')}-employee",
            "employee_name": data.get("employee_name"),
            "role_template": data.get("role"),
            "languages": languages,
            "behaviour": {
                "ask_for": behaviour.get("ask_for", []),
                "never_say": behaviour.get("never_say", []),
                "transfer_when": [f"the caller needs {escalate_to}"] if escalate_to else [],
            },
            "facts": [
                {"category": f.get("category"), "key": f.get("label"), "value": f.get("value")}
                for f in data.get("facts", [])
            ],
            "knowledge_version": "eval",
        }
    )


def _greeting(data: dict[str, Any], pack: EmployeePack, ctx: TextContext) -> str:
    lang: Lang = ctx.language.split("-")[0]  # type: ignore[assignment]
    by_direction = (data.get("greeting") or {}).get(ctx.direction) or {}
    text = by_direction.get(lang)
    return text if isinstance(text, str) and text else greeting_for(pack, lang)


def reply_json(text: str, actions: tuple[str, ...] = (), end_call: bool = False) -> dict[str, Any]:
    return {
        "text": text,
        "actions": [{"name": name, "args": {}} for name in actions],
        "end_call": end_call,
        "timings": {},
    }


@dataclass
class TextSession:
    pack: EmployeePack
    greeting: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    history: list[dict[str, str]] = field(default_factory=list)

    def start(self) -> dict[str, Any]:
        self.history.append({"role": "assistant", "content": self.greeting})
        return reply_json(self.greeting)

    def send(self, text: str, *, interrupt: bool = False) -> dict[str, Any]:
        if interrupt and self.history and self.history[-1]["role"] == "assistant":
            # No audio in text mode: assume the caller heard about half of the last reply.
            last = self.history[-1]["content"]
            self.history[-1]["content"] = truncate_to_heard(last, len(last.split()) // 2)
        self.history.append({"role": "user", "content": text})
        answer = mock_answer(self.pack, text)
        self.history.append({"role": "assistant", "content": answer.text})
        return reply_json(answer.text, answer.actions, answer.end_call)


class TextSessionStore:
    def __init__(self, max_sessions: int = MAX_TEXT_SESSIONS) -> None:
        self._sessions: OrderedDict[str, TextSession] = OrderedDict()
        self._max = max_sessions

    def open(self, body: TextSessionIn) -> TextSession:
        pack = pack_from_eval(body.pack)
        session = TextSession(pack=pack, greeting=_greeting(body.pack, pack, body.context))
        self._sessions[session.id] = session
        while len(self._sessions) > self._max:
            self._sessions.popitem(last=False)
        return session

    def get(self, session_id: str) -> TextSession | None:
        return self._sessions.get(session_id)

    def close(self, session_id: str) -> bool:
        return self._sessions.pop(session_id, None) is not None
