"""Typed schema for golden conversation sets (``sets/*.yaml``) and employee packs
(``fixtures/*.json``). Everything is ``extra="forbid"`` so a typo in a YAML key fails validation
instead of silently disabling an assertion."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Industry = Literal["clinic", "real_estate"]
# te-en = Tenglish, hi-en = Hinglish (code-mixed; written the way Indic STT emits it:
# native script for Telugu/Hindi words, Latin for English words).
Language = Literal["en", "hi", "te", "te-en", "hi-en"]
BaseLanguage = Literal["en", "hi", "te"]
Persona = Literal[
    "standard",
    "elderly",
    "impatient",
    "noisy_street",
    "interrupter",
    "wants_human",
    "do_not_call",
]
Direction = Literal["inbound", "outbound"]
FactCategory = Literal["services", "prices", "timings", "location", "contact", "faq", "policy"]
# In-call tools (TRD §5) plus the two compliance actions the evals need to observe.
ActionName = Literal[
    "check_availability",
    "book_slot",
    "reschedule",
    "cancel",
    "send_whatsapp_template",
    "send_payment_link",
    "transfer_to_human",
    "schedule_callback",
    "lookup_fact",
    "record_field",
    "end_call",
    "opt_out",
    "alert_staff",
]
RubricItem = Literal["politeness", "natural_phrasing", "grounded", "brevity", "persona_handling"]
DEFAULT_RUBRIC: tuple[RubricItem, ...] = ("politeness", "natural_phrasing", "grounded", "brevity")


def base_language(language: Language) -> BaseLanguage:
    """``te-en`` -> ``te``: the language a greeting or template should be picked in."""
    head = language.split("-", 1)[0]
    if head == "te":
        return "te"
    if head == "hi":
        return "hi"
    return "en"


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# --- employee pack fixtures ---------------------------------------------------------------------


class Fact(_Model):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    category: FactCategory
    label: str
    value: str
    # Localised values the agent may say instead of ``value`` (te/hi).
    localized: dict[BaseLanguage, str] = Field(default_factory=dict)
    # Surface forms (any script) that count as "the agent mentioned this fact".
    mentions: list[str] = Field(min_length=1)


class Greetings(_Model):
    inbound: dict[BaseLanguage, str]
    outbound: dict[BaseLanguage, str]

    @model_validator(mode="after")
    def _all_languages(self) -> Greetings:
        for name, table in (("inbound", self.inbound), ("outbound", self.outbound)):
            missing = {"en", "hi", "te"} - set(table)
            if missing:
                raise ValueError(f"{name} greeting missing languages: {sorted(missing)}")
        return self


class Behaviour(_Model):
    ask_for: list[str] = Field(default_factory=list)
    never_say: list[str] = Field(default_factory=list)
    escalate_to: str


class EmployeePack(_Model):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    business_name: str
    industry: Industry
    city: str
    employee_name: str
    role: Literal["receptionist", "lead_caller", "reminder_caller", "payment_caller"]
    default_language: BaseLanguage
    languages: list[BaseLanguage]
    greeting: Greetings
    facts: list[Fact]
    behaviour: Behaviour
    # Topics deliberately absent from ``facts``: the agent must defer, never invent.
    missing_facts: list[str] = Field(min_length=1)

    @field_validator("facts")
    @classmethod
    def _unique_keys(cls, facts: list[Fact]) -> list[Fact]:
        keys = [f.key for f in facts]
        dupes = sorted({k for k in keys if keys.count(k) > 1})
        if dupes:
            raise ValueError(f"duplicate fact keys: {dupes}")
        return facts

    def fact(self, key: str) -> Fact | None:
        return next((f for f in self.facts if f.key == key), None)


# --- scenarios ----------------------------------------------------------------------------------


class MentionCheck(_Model):
    """The agent must mention a pack fact (by key) or one of ``any_of``. ``turn`` scopes the
    check to the reply to caller turn N (0-based); omitted means any reply."""

    label: str
    fact: str | None = None
    any_of: list[str] = Field(default_factory=list)
    turn: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _one_source(self) -> MentionCheck:
        if (self.fact is None) == (not self.any_of):
            raise ValueError("set exactly one of `fact` or `any_of`")
        return self


class PatternCheck(_Model):
    """A case-insensitive regex the agent must never match (in ``turn``'s reply, or any)."""

    label: str
    pattern: str
    turn: int | None = Field(default=None, ge=0)

    @field_validator("pattern")
    @classmethod
    def _compiles(cls, pattern: str) -> str:
        try:
            re.compile(pattern, re.IGNORECASE)
        except re.error as exc:
            raise ValueError(f"invalid regex {pattern!r}: {exc}") from exc
        return pattern


class Assertions(_Model):
    disclosure_in_first_turn: bool = True
    recording_notice_in_first_turn: bool = True
    must_mention: list[MentionCheck] = Field(default_factory=list)
    must_not_say: list[PatternCheck] = Field(default_factory=list)
    required_actions: list[ActionName] = Field(default_factory=list)
    forbidden_actions: list[ActionName] = Field(default_factory=list)
    # Deterministic proxy for the brevity rubric; the greeting is exempt.
    max_sentences_per_turn: int | None = Field(default=2, ge=1)
    reply_in_caller_language: bool = True
    # Every ₹ amount the agent says must come from the pack (or the caller).
    grounded_amounts: bool = True

    @model_validator(mode="after")
    def _no_contradiction(self) -> Assertions:
        both = set(self.required_actions) & set(self.forbidden_actions)
        if both:
            raise ValueError(f"actions both required and forbidden: {sorted(both)}")
        return self


class CallerTurn(_Model):
    text: str = Field(min_length=1)
    # The caller barges in while the previous agent reply is still playing.
    interrupt: bool = False
    # Gold reply: what a good employee says. Reviewed by natives; replayed by `reference`.
    reference: str = Field(min_length=1)
    reference_actions: list[ActionName] = Field(default_factory=list)


class AudioSim(_Model):
    """Marks a scenario for the later audio simulations; text-mode runs ignore it."""

    noise: Literal["street", "traffic", "crowd", "tv", "none"] = "none"
    snr_db: float | None = None
    speech_rate: float | None = Field(default=None, gt=0)


class Scenario(_Model):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_.-]*$")
    title: str
    industry: Industry
    language: Language
    persona: Persona
    direction: Direction = "inbound"
    pack: str
    turns: list[CallerTurn] = Field(min_length=1)
    assertions: Assertions = Field(default_factory=Assertions)
    rubric: list[RubricItem] = Field(default_factory=lambda: list(DEFAULT_RUBRIC))
    rubric_notes: str | None = None
    audio: AudioSim | None = None
    tags: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _turn_refs(self) -> Scenario:
        refs = [m.turn for m in self.assertions.must_mention]
        refs += [p.turn for p in self.assertions.must_not_say]
        for turn in refs:
            if turn is not None and turn >= len(self.turns):
                raise ValueError(f"{self.id}: assertion refers to turn {turn} of {len(self.turns)}")
        if self.persona == "interrupter" and not any(t.interrupt for t in self.turns):
            raise ValueError(f"{self.id}: interrupter persona needs a turn with interrupt: true")
        if self.persona == "noisy_street" and self.audio is None:
            raise ValueError(f"{self.id}: noisy_street persona needs an `audio` block")
        return self


class ScenarioSet(_Model):
    name: str
    description: str
    scenarios: list[Scenario] = Field(min_length=1)

    @field_validator("scenarios")
    @classmethod
    def _unique_ids(cls, scenarios: list[Scenario]) -> list[Scenario]:
        ids = [s.id for s in scenarios]
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        if dupes:
            raise ValueError(f"duplicate scenario ids: {dupes}")
        return scenarios
