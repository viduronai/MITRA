"""Text-mode sessions for mitra-evals (HTTP contract in evals/src/mitra_evals/agents/base.py).

One eval scenario = one session: greeting, then caller turns, with tool calls surfaced as
``actions``. With ``MITRA_LLM=gemini`` or ``groq`` (plus its key and ``MITRA_LLM_MODEL``) each turn
goes through the production brain (``mitra_voice.brain``: guardrails, the LLM, tools, post-check);
otherwise through the deterministic pack-grounded mock responder.
"""

from __future__ import annotations

import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from mitra_human import truncate_to_heard
from mitra_voice.brain.backend import ChatBackend
from mitra_voice.brain.cache import CachingBackend
from mitra_voice.brain.client import brain_available, brain_clock, brain_config, make_backend
from mitra_voice.brain.engine import Brain, Message
from mitra_voice.brain.language import LanguageRef
from mitra_voice.config import Settings, get_settings
from mitra_voice.pack import EmployeePack, Lang, pack_from_dict
from mitra_voice.prompt import Localized, greeting_for
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


def localized_from_eval(data: dict[str, Any]) -> Localized:
    """Localised fact wording from the evals pack, keyed like our facts (by label)."""
    out: dict[str, dict[str, str]] = {}
    for f in data.get("facts", []):
        forms = f.get("localized") or {}
        if isinstance(forms, dict) and f.get("label"):
            out[str(f["label"])] = {str(k): str(v) for k, v in forms.items() if v}
    return out


def _greeting(data: dict[str, Any], pack: EmployeePack, ctx: TextContext) -> str:
    lang: Lang = ctx.language.split("-")[0]  # type: ignore[assignment]
    by_direction = (data.get("greeting") or {}).get(ctx.direction) or {}
    text = by_direction.get(lang)
    return text if isinstance(text, str) and text else greeting_for(pack, lang)


def reply_json(
    text: str,
    actions: tuple[str, ...] | list[tuple[str, dict[str, Any]]] = (),
    end_call: bool = False,
    timings: dict[str, float] | None = None,
) -> dict[str, Any]:
    return {
        "text": text,
        "actions": [
            {"name": a, "args": {}} if isinstance(a, str) else {"name": a[0], "args": a[1]}
            for a in actions
        ],
        "end_call": end_call,
        "timings": timings or {},
    }


@dataclass
class TextSession:
    pack: EmployeePack
    greeting: str
    brain: Brain | None = None
    language: LanguageRef = field(default_factory=LanguageRef)
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    history: list[dict[str, str]] = field(default_factory=list)

    def start(self) -> dict[str, Any]:
        self.history.append({"role": "assistant", "content": self.greeting})
        return reply_json(self.greeting)

    async def send(self, text: str, *, interrupt: bool = False) -> dict[str, Any]:
        if interrupt and self.history and self.history[-1]["role"] == "assistant":
            # No audio in text mode: assume the caller heard about half of the last reply.
            last = self.history[-1]["content"]
            self.history[-1]["content"] = truncate_to_heard(last, len(last.split()) // 2)
        if self.brain is None:
            self.history.append({"role": "user", "content": text})
            answer = mock_answer(self.pack, text)
            self.history.append({"role": "assistant", "content": answer.text})
            return reply_json(answer.text, answer.actions, answer.end_call)

        past = [
            Message("user" if m["role"] == "user" else "assistant", m["content"])
            for m in self.history
        ]
        result = await self.brain.turn(past, text, self.language.resolve(text))
        self.history.append({"role": "user", "content": text})
        self.history.append({"role": "assistant", "content": result.text})
        timings = (
            {"first_token_ms": round(result.first_token_ms, 1)} if result.first_token_ms else {}
        )
        return reply_json(
            result.text, [(a.name, a.args) for a in result.actions], result.end_call, timings
        )


class TextSessionStore:
    def __init__(self, max_sessions: int = MAX_TEXT_SESSIONS, settings: Settings | None = None):
        self._sessions: OrderedDict[str, TextSession] = OrderedDict()
        self._max = max_sessions
        self._settings = settings or get_settings()
        self.uses_brain = brain_available(self._settings)
        self._backend: ChatBackend | None = None

    def _brain(self, pack: EmployeePack, localized: Localized) -> Brain | None:
        if not self.uses_brain:
            return None
        s = self._settings
        if self._backend is None:
            backend = make_backend(s)
            cache = s.mitra_llm_cache_dir
            self._backend = CachingBackend(backend, cache) if cache else backend
        config = brain_config(s, text_mode=True)
        return Brain(self._backend, config, pack, localized=localized, clock=brain_clock(s))

    def open(self, body: TextSessionIn) -> TextSession:
        pack = pack_from_eval(body.pack)
        session = TextSession(
            pack=pack,
            greeting=_greeting(body.pack, pack, body.context),
            brain=self._brain(pack, localized_from_eval(body.pack)),
            language=LanguageRef(body.context.language),
        )
        self._sessions[session.id] = session
        while len(self._sessions) > self._max:
            self._sessions.popitem(last=False)
        return session

    def get(self, session_id: str) -> TextSession | None:
        return self._sessions.get(session_id)

    def close(self, session_id: str) -> bool:
        return self._sessions.pop(session_id, None) is not None
