"""Ready-made AI teams per industry (TEAM-01, ONB-14) and hand-off vocabulary (TEAM-02).

A team role sits on top of one of the four base roles the voice brain knows
(``RoleTemplate``); the role adds its own name, default voice and behaviour sentences. Hand-off
rules in a template refer to members by team role and are resolved to employee ids on hire.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from mitra_core.models.enums import CallResult, Industry, RoleTemplate

# Tasks the next employee (or staff) can be given; the web shows each as a sentence.
TASKS = (
    "book_visit",
    "remind_appointment",
    "follow_up",
    "collect_payment",
    "feedback",
    "send_report",
    "call_back",
    "brief_staff",
)
CHANNELS = ("call", "whatsapp", "whatsapp_then_call")
# Results a rule can react to ("When a lead is Interested ...").
RULE_RESULTS = tuple(r.value for r in CallResult if r != CallResult.TRANSFERRED)
# Tasks scheduled relative to the customer's appointment rather than the call end.
BEFORE_APPOINTMENT_MIN = {"remind_appointment": 24 * 60, "brief_staff": 120}


@dataclass(frozen=True, slots=True)
class TeamRole:
    id: str
    name: str  # default employee name
    title: str  # role shown on the map ("Visit Coordinator")
    base: RoleTemplate
    voice_id: str
    ask_for: tuple[str, ...] = ()
    transfer_when: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RuleTemplate:
    from_role: str
    when_result: str
    to_role: str | None  # None = human staff (WhatsApp brief)
    task: str
    channel: str
    delay_minutes: int = 10


@dataclass(frozen=True, slots=True)
class TeamTemplate:
    id: str
    industry: Industry
    name: str
    roles: tuple[TeamRole, ...]
    rules: tuple[RuleTemplate, ...] = field(default_factory=tuple)


_STAFF = "the caller asks for a person"

REAL_ESTATE = TeamTemplate(
    id="real_estate",
    industry=Industry.REAL_ESTATE,
    name="Real estate team",
    roles=(
        TeamRole(
            "lead_caller",
            "Priya",
            "Lead Caller",
            RoleTemplate.LEAD_CALLER,
            "priya-te-hyd",
            ("budget", "preferred location", "bedrooms", "when they plan to buy"),
            (_STAFF,),
        ),
        TeamRole(
            "visit_coordinator",
            "Meena",
            "Visit Coordinator",
            RoleTemplate.REMINDER_CALLER,
            "lakshmi-te-sig",
            ("a site visit day and time", "how many people will come"),
            (_STAFF,),
        ),
        TeamRole(
            "sales_assistant",
            "Arjun",
            "Sales Assistant",
            RoleTemplate.LEAD_CALLER,
            "arjun-te-vij",
            ("what they liked at the visit", "any concerns about price or location"),
            ("the caller wants to negotiate the price", _STAFF),
        ),
        TeamRole(
            "payment_caller",
            "Kavya",
            "Payment Caller",
            RoleTemplate.PAYMENT_CALLER,
            "kavya-en-blr",
            ("when they can pay the booking amount",),
            ("the caller disputes an amount", _STAFF),
        ),
    ),
    rules=(
        RuleTemplate(
            "lead_caller", "interested", "visit_coordinator", "book_visit", "whatsapp_then_call", 10
        ),
        RuleTemplate("lead_caller", "call_back", "lead_caller", "call_back", "call", 0),
        RuleTemplate("visit_coordinator", "booked", None, "brief_staff", "whatsapp", 0),
        RuleTemplate("visit_coordinator", "booked", "sales_assistant", "follow_up", "call", 1440),
        RuleTemplate(
            "sales_assistant", "interested", "payment_caller", "collect_payment", "call", 60
        ),
    ),
)

CLINIC = TeamTemplate(
    id="clinic",
    industry=Industry.CLINIC,
    name="Clinic team",
    roles=(
        TeamRole(
            "receptionist",
            "Priya",
            "Receptionist",
            RoleTemplate.RECEPTIONIST,
            "priya-te-hyd",
            ("patient name", "age", "which doctor or test"),
            ("the caller describes an emergency", _STAFF),
        ),
        TeamRole(
            "reminder_caller",
            "Lakshmi",
            "Reminder Caller",
            RoleTemplate.REMINDER_CALLER,
            "lakshmi-te-sig",
            ("whether they can come at the booked time",),
            (_STAFF,),
        ),
        TeamRole(
            "follow_up_caller",
            "Vikram",
            "Follow-up Caller",
            RoleTemplate.REMINDER_CALLER,
            "vikram-en-hyd",
            ("how they are feeling after the visit", "whether they need a review visit"),
            ("the caller reports a side effect or new symptom", _STAFF),
        ),
        TeamRole(
            "report_sender",
            "Ananya",
            "Report Sender",
            RoleTemplate.REMINDER_CALLER,
            "ananya-hi-del",
            ("date of birth to confirm identity",),
            ("the caller asks what the report means", _STAFF),
        ),
    ),
    rules=(
        RuleTemplate("receptionist", "booked", "reminder_caller", "remind_appointment", "call"),
        RuleTemplate("receptionist", "booked", None, "brief_staff", "whatsapp", 0),
        RuleTemplate("receptionist", "call_back", "receptionist", "call_back", "call", 0),
        RuleTemplate("reminder_caller", "booked", "follow_up_caller", "feedback", "call", 1440),
        RuleTemplate(
            "follow_up_caller", "interested", "report_sender", "send_report", "whatsapp", 0
        ),
    ),
)

COACHING = TeamTemplate(
    id="coaching",
    industry=Industry.EDUCATION,
    name="Coaching centre team",
    roles=(
        TeamRole(
            "lead_caller",
            "Rohan",
            "Lead Caller",
            RoleTemplate.LEAD_CALLER,
            "rohan-hi-mum",
            ("student's class", "course of interest", "preferred batch timing"),
            (_STAFF,),
        ),
        TeamRole(
            "counsellor",
            "Meera",
            "Counsellor",
            RoleTemplate.LEAD_CALLER,
            "meera-hi-sig",
            ("a demo class day", "parent's main concern"),
            ("the parent wants a fee discount", _STAFF),
        ),
        TeamRole(
            "payment_caller",
            "Kavya",
            "Fee Reminder",
            RoleTemplate.PAYMENT_CALLER,
            "kavya-en-blr",
            ("when they can pay the fee instalment",),
            ("the caller disputes an amount", _STAFF),
        ),
        TeamRole(
            "feedback_caller",
            "Vikram",
            "Feedback Caller",
            RoleTemplate.REMINDER_CALLER,
            "vikram-en-hyd",
            ("how the student finds the classes",),
            (_STAFF,),
        ),
    ),
    rules=(
        RuleTemplate(
            "lead_caller", "interested", "counsellor", "book_visit", "whatsapp_then_call", 10
        ),
        RuleTemplate("counsellor", "booked", None, "brief_staff", "whatsapp", 0),
        RuleTemplate("counsellor", "interested", "payment_caller", "collect_payment", "call", 60),
        RuleTemplate("payment_caller", "booked", "feedback_caller", "feedback", "call", 10080),
    ),
)

TEAM_TEMPLATES: dict[str, TeamTemplate] = {t.id: t for t in (REAL_ESTATE, CLINIC, COACHING)}
TEMPLATE_FOR_INDUSTRY: dict[Industry, str] = {
    Industry.REAL_ESTATE: "real_estate",
    Industry.CLINIC: "clinic",
    Industry.EDUCATION: "coaching",
    Industry.OTHER: "clinic",
}
