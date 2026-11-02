"""Post-call analysis: summary (≤ 80 words), result, collected fields, sentiment, customer memory
(confirmed vs inferred), commitments and unknown questions (WORKFLOWS §4).

``HeuristicSummarizer`` is deterministic and needs nothing external; it is the default and what
the tests use. ``LlmSummarizer`` (enabled only when ``MITRA_SUMMARIZER=llm`` and an
OpenAI-compatible endpoint, key and model are configured) rewrites the summary, sentiment,
memory and unknown questions with an LLM, keeping the action-derived result, fields and
commitments, and falls back to the heuristic on any error.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, replace
from datetime import datetime, time, timedelta
from typing import Any, Literal, Protocol
from zoneinfo import ZoneInfo

import httpx

from mitra_core.calls.labels import fmt_booking, is_ok, parse_booking
from mitra_core.config import Settings
from mitra_core.logging import get_logger
from mitra_core.models.enums import CallDirection, CallResult, MemoryStatus, Sentiment

log = get_logger(__name__)

MAX_SUMMARY_WORDS = 80
INFERRED_TTL = timedelta(days=180)
CALLBACK_DEFAULT_DELAY = timedelta(days=1)

LANGUAGE_NAMES = {"en": "English", "hi": "Hindi", "te": "Telugu"}


@dataclass(frozen=True, slots=True)
class Turn:
    role: Literal["user", "assistant"]
    text: str


@dataclass(frozen=True, slots=True)
class ActionRecord:
    name: str
    args: dict[str, Any]
    result: dict[str, Any]
    ok: bool


@dataclass(frozen=True, slots=True)
class CallInput:
    transcript: list[Turn]
    actions: list[ActionRecord]
    direction: CallDirection
    language: str | None
    ended_at: datetime
    timezone: str = "Asia/Kolkata"
    result_hint: CallResult | None = None
    fields_hint: dict[str, str] = field(default_factory=dict)
    unknown_hint: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class MemoryCandidate:
    key: str
    value: str
    status: MemoryStatus
    confidence: float
    expires_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class CommitmentCandidate:
    kind: str
    description: str
    due_at: datetime | None


@dataclass(frozen=True, slots=True)
class CallAnalysis:
    summary: str
    result: CallResult
    fields: dict[str, str]
    sentiment: Sentiment
    next_step: str | None
    memory: list[MemoryCandidate]
    commitments: list[CommitmentCandidate]
    unknown_questions: list[str]


class Summarizer(Protocol):
    async def analyze(self, call: CallInput) -> CallAnalysis: ...


# --- heuristics ----------------------------------------------------------------------------------

_NEGATIVE = (
    "angry",
    "worst",
    "useless",
    "complaint",
    "cheat",
    "fraud",
    "rubbish",
    "waste of time",
    "very bad",
    "disgusting",
    "bakwas",
    "bekar",
    "ghatiya",
    "pagal",
    "బాలేదు",
    "చెత్త",
    "बकवास",
    "बेकार",
    "घटिया",
)
_POSITIVE = (
    "thank",
    "great",
    "perfect",
    "super",
    "wonderful",
    "dhanyavad",
    "shukriya",
    "bahut accha",
    "chala bagundi",
    "ధన్యవాదాలు",
    "థాంక్స్",
    "धन्यवाद",
    "शुक्रिया",
)
_NOT_INTERESTED = (
    "not interested",
    "don't call",
    "do not call",
    "no need",
    "nahi chahiye",
    "interest nahi",
    "vaddu",
    "వద్దు",
    "नहीं चाहिए",
)
# The employee deferring to the team: the caller's previous question is a knowledge gap.
_DEFER = (
    "i'll check",
    "i will check",
    "let me check with",
    "confirm with the",
    "get back to you",
    "team will call",
    "doctor will call",
    "i don't have that",
    "i do not have that",
    "కనుక్కొని",
    "తెలియదు",
    "पता करके",
    "पता नहीं",
    "जानकारी नहीं",
)
_BUDGET = re.compile(r"(\d+(?:\.\d+)?)\s*(lakhs?|lacs?|l\b|cr\b|crores?)", re.IGNORECASE)
_FIELD_KEY = re.compile(r"[^a-z0-9]+")


def _norm_key(key: str) -> str:
    return _FIELD_KEY.sub("_", key.strip().lower()).strip("_")[:60] or "detail"


def _words(text: str, limit: int) -> str:
    words = text.split()
    return " ".join(words[:limit]) + ("…" if len(words) > limit else "")


def _cap_words(text: str, limit: int = MAX_SUMMARY_WORDS) -> str:
    words = text.split()
    if len(words) <= limit:
        return text
    return " ".join(words[:limit]).rstrip(".,;") + "…"


def _contains(text: str, needles: tuple[str, ...]) -> bool:
    low = text.lower()
    return any(n in low for n in needles)


def _sentiment(user_text: str) -> Sentiment:
    neg = sum(user_text.lower().count(w) for w in _NEGATIVE)
    pos = sum(user_text.lower().count(w) for w in _POSITIVE)
    if neg > pos:
        return Sentiment.NEGATIVE
    if pos > 0:
        return Sentiment.POSITIVE
    return Sentiment.NEUTRAL


def _dedupe(items: list[str], limit: int) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        text = " ".join(item.split())[:300]
        if text and text.lower() not in seen:
            seen.add(text.lower())
            out.append(text)
    return out[:limit]


class HeuristicSummarizer:
    """Deterministic analysis from the structured actions plus simple transcript cues."""

    async def analyze(self, call: CallInput) -> CallAnalysis:
        return analyze_heuristic(call)


def _result(call: CallInput, user_turns: list[str]) -> CallResult:
    if call.result_hint is not None:
        return call.result_hint
    ok_names = {a.name for a in call.actions if a.ok}
    if ok_names & {"book_slot", "reschedule"}:
        return CallResult.BOOKED
    if "transfer_to_human" in ok_names:
        return CallResult.TRANSFERRED
    if "opt_out" in ok_names:
        return CallResult.NOT_INTERESTED
    if "schedule_callback" in ok_names:
        return CallResult.CALL_BACK
    if not user_turns:
        return CallResult.MISSED
    if _contains(" ".join(user_turns), _NOT_INTERESTED):
        return CallResult.NOT_INTERESTED
    if "record_field" in ok_names:
        return CallResult.INTERESTED
    return CallResult.INFO_ONLY


def _bookings(call: CallInput) -> list[tuple[ActionRecord, Any]]:
    out = []
    for a in call.actions:
        if a.name in {"book_slot", "reschedule"} and a.ok:
            parsed = parse_booking(a.args, a.result)
            if parsed is not None:
                out.append((a, parsed))
    return out


def analyze_heuristic(call: CallInput) -> CallAnalysis:
    tz = ZoneInfo(call.timezone)
    user_turns = [t.text.strip() for t in call.transcript if t.role == "user" and t.text.strip()]
    result = _result(call, user_turns)

    fields: dict[str, str] = {_norm_key(k): v for k, v in call.fields_hint.items() if v}
    for a in call.actions:
        if a.name == "record_field" and a.args.get("field"):
            value = str(a.args.get("value", "")).strip()
            if value:
                fields[_norm_key(str(a.args["field"]))] = value[:300]
    bookings = _bookings(call)
    for a, (day, at) in bookings[-1:]:
        fields["appointment"] = fmt_booking(day, at)
        if a.args.get("name"):
            fields.setdefault("name", str(a.args["name"])[:120])

    # Memory: what the caller stated is confirmed; guesses are inferred and expire.
    memory: list[MemoryCandidate] = []
    expires = call.ended_at + INFERRED_TTL
    for key, value in fields.items():
        if key != "appointment":
            memory.append(MemoryCandidate(key, value, MemoryStatus.CONFIRMED, 0.9))
    if call.language in LANGUAGE_NAMES and user_turns:
        memory.append(
            MemoryCandidate(
                "preferred_language",
                LANGUAGE_NAMES[call.language],
                MemoryStatus.INFERRED,
                0.6,
                expires,
            )
        )
    if bookings:
        booked_at: time = bookings[-1][1][1]
        hour = booked_at.hour
        part = "morning" if hour < 12 else "afternoon" if hour < 16 else "evening"
        memory.append(MemoryCandidate("preferred_time", part, MemoryStatus.INFERRED, 0.5, expires))
    if "budget" not in fields:
        match = next((m for t in user_turns if (m := _BUDGET.search(t))), None)
        if match:
            memory.append(
                MemoryCandidate("budget", match.group(0), MemoryStatus.INFERRED, 0.6, expires)
            )

    # Commitments: bookings and promised callbacks.
    commitments: list[CommitmentCandidate] = []
    for _, (day, at) in bookings[-1:]:
        due = datetime.combine(day, at, tzinfo=tz)
        commitments.append(
            CommitmentCandidate("appointment", f"Appointment {fmt_booking(day, at)}", due)
        )
    callback_topics: list[str] = []
    for a in call.actions:
        if a.name == "schedule_callback" and a.ok:
            topic = str(a.args.get("topic") or "").strip()
            when = str(a.args.get("when") or "").strip()
            callback_topics.append(topic)
            text = f"Call back: {topic}" if topic else "Call back"
            if when:
                text += f" ({when})"
            # TODO(nlp): parse ``when`` ("tomorrow evening") into a due time.
            commitments.append(
                CommitmentCandidate("callback", text[:300], call.ended_at + CALLBACK_DEFAULT_DELAY)
            )

    # Unknown questions: explicit hints, callback topics, and questions the employee deferred.
    deferred: list[str] = []
    last_user: str | None = None
    for t in call.transcript:
        if t.role == "user":
            last_user = t.text.strip()
        elif last_user and _contains(t.text, _DEFER):
            deferred.append(last_user)
            last_user = None
    unknown = _dedupe([*call.unknown_hint, *[c for c in callback_topics if c], *deferred], 5)

    next_step = commitments[0].description if commitments else None
    summary = _summary(call, result, user_turns, fields, bookings, next_step)
    return CallAnalysis(
        summary=summary,
        result=result,
        fields=fields,
        sentiment=_sentiment(" ".join(user_turns)),
        next_step=next_step,
        memory=memory,
        commitments=commitments,
        unknown_questions=unknown,
    )


def _summary(
    call: CallInput,
    result: CallResult,
    user_turns: list[str],
    fields: dict[str, str],
    bookings: list[tuple[ActionRecord, Any]],
    next_step: str | None,
) -> str:
    if result == CallResult.MISSED or not user_turns:
        return (
            "Missed call: nobody spoke."
            if call.direction != CallDirection.OUTBOUND
            else "No answer: the customer did not speak."
        )
    topic = next((t for t in user_turns if len(t.split()) >= 3), user_turns[0])
    sentences = [f'Caller said: "{_words(topic, 14)}".']
    if result == CallResult.BOOKED and bookings:
        day, at = bookings[-1][1]
        sentences.append(f"Booked for {fmt_booking(day, at)}.")
    elif result == CallResult.TRANSFERRED:
        sentences.append("Transferred to a person.")
    elif result == CallResult.NOT_INTERESTED:
        sentences.append("Not interested.")
    elif result == CallResult.CALL_BACK:
        sentences.append("Asked for a callback.")
    elif result == CallResult.INTERESTED:
        shared = ", ".join(k.replace("_", " ") for k in list(fields)[:4])
        sentences.append(f"Interested; shared {shared}." if shared else "Interested.")
    else:
        sentences.append("Got the information they needed.")
    if next_step and result != CallResult.BOOKED:
        sentences.append(f"Next: {next_step}.")
    return _cap_words(" ".join(sentences))


# --- LLM -----------------------------------------------------------------------------------------

_LLM_PROMPT = """You analyse one phone call between an AI receptionist ("assistant") and a caller
("user") for the business owner. Reply with ONLY a JSON object:
{"summary": "<= 60 words, English, plain, what the caller wanted and what happened",
 "sentiment": "positive" | "neutral" | "negative",
 "memory": [{"key": "snake_case", "value": "short", "status": "confirmed" | "inferred"}],
 "unknown_questions": ["questions the assistant could not answer"]}
"confirmed" = the caller stated it; "inferred" = your guess. Max 8 memory items."""


class LlmSummarizer:
    """OpenAI-compatible chat completion (e.g. the brain's provider). Never required."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout_s: float = 20.0,
    ) -> None:
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._key = api_key
        self._model = model
        self._transport = transport
        self._timeout = timeout_s

    async def analyze(self, call: CallInput) -> CallAnalysis:
        base = analyze_heuristic(call)
        if not any(t.role == "user" for t in call.transcript):
            return base
        try:
            data = await self._complete(call)
            return _merge_llm(base, data, call.ended_at + INFERRED_TTL)
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            log.warning("summarizer.llm_failed", error=type(exc).__name__)
            return base

    async def _complete(self, call: CallInput) -> dict[str, Any]:
        lines = "\n".join(f"{t.role}: {t.text}" for t in call.transcript[-80:])
        actions = "\n".join(f"- {a.name} {json.dumps(a.args)[:200]}" for a in call.actions[:30])
        body = {
            "model": self._model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": _LLM_PROMPT},
                {"role": "user", "content": f"Transcript:\n{lines}\n\nActions:\n{actions}"},
            ],
        }
        async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
            res = await client.post(
                self._url, json=body, headers={"Authorization": f"Bearer {self._key}"}
            )
        res.raise_for_status()
        content = res.json()["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        if not isinstance(parsed, dict):
            raise ValueError("not an object")
        return parsed


def _merge_llm(base: CallAnalysis, data: dict[str, Any], expires: datetime) -> CallAnalysis:
    summary = str(data.get("summary") or "").strip() or base.summary
    try:
        sentiment = Sentiment(str(data.get("sentiment")))
    except ValueError:
        sentiment = base.sentiment
    memory = {m.key: m for m in base.memory}
    for item in list(data.get("memory") or [])[:8]:
        if not isinstance(item, dict) or not item.get("key") or not item.get("value"):
            continue
        key = _norm_key(str(item["key"]))
        if key in memory and memory[key].status == MemoryStatus.CONFIRMED:
            continue  # facts from actions win over the model's reading
        confirmed = item.get("status") == "confirmed"
        memory[key] = MemoryCandidate(
            key,
            str(item["value"])[:300],
            MemoryStatus.CONFIRMED if confirmed else MemoryStatus.INFERRED,
            0.8 if confirmed else 0.5,
            None if confirmed else expires,
        )
    unknown = [str(q) for q in list(data.get("unknown_questions") or []) if isinstance(q, str)]
    return replace(
        base,
        summary=_cap_words(summary),
        sentiment=sentiment,
        memory=list(memory.values()),
        unknown_questions=_dedupe([*base.unknown_questions, *unknown], 5),
    )


def get_summarizer(settings: Settings) -> Summarizer:
    if (
        settings.summarizer == "llm"
        and settings.summarizer_llm_url
        and settings.summarizer_llm_api_key
        and settings.summarizer_llm_model
    ):
        return LlmSummarizer(
            settings.summarizer_llm_url,
            settings.summarizer_llm_api_key.get_secret_value(),
            settings.summarizer_llm_model,
        )
    return HeuristicSummarizer()


__all__ = [
    "ActionRecord",
    "CallAnalysis",
    "CallInput",
    "HeuristicSummarizer",
    "LlmSummarizer",
    "Summarizer",
    "Turn",
    "analyze_heuristic",
    "get_summarizer",
    "is_ok",
]
