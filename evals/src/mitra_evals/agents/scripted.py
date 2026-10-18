"""``scripted``: a deliberately trivial keyword baseline. It answers from the pack with fixed
templates in en/te/hi and fires the obvious actions. Its pass rate is the floor any real
agent must beat, and its failures show which assertions need real language understanding."""

from __future__ import annotations

from dataclasses import dataclass

from mitra_evals.agents.base import Action, AgentReply, CallContext, ConversationSession
from mitra_evals.schema import ActionName, BaseLanguage, EmployeePack, Fact, FactCategory
from mitra_evals.schema import base_language as to_base
from mitra_evals.text import normalise


@dataclass(frozen=True, slots=True)
class _Intent:
    name: str
    keywords: tuple[str, ...]
    actions: tuple[ActionName, ...] = ()
    category: FactCategory | None = None


# Checked in order: safety first, then routing, then information.
_INTENTS = (
    _Intent(
        "emergency",
        (
            "chest pain",
            "bleeding",
            "unconscious",
            "suicide",
            "breath",
            "accident",
            "ఛాతీ",
            "రక్తం",
            "స్పృహ",
            "ఊపిరి",
            "बेहोश",
            "सीने",
            "खून",
            "साँस",
            "సూసైడ్",
        ),
        ("transfer_to_human", "alert_staff"),
    ),
    _Intent(
        "opt_out",
        (
            "don't call",
            "dont call",
            "do not call",
            "stop calling",
            "remove my number",
            "కాల్ చేయకండి",
            "call చేయకండి",
            "कॉल मत",
            "call मत",
            "नंबर हटा",
        ),
        ("opt_out", "end_call"),
    ),
    _Intent(
        "human",
        (
            "human",
            "real person",
            "staff",
            "manager",
            "bot",
            "machine",
            "మనిషి",
            "మేనేజర్",
            "మెషీన్",
            "इंसान",
            "स्टाफ",
        ),
        ("transfer_to_human",),
    ),
    _Intent(
        "medical",
        ("tablet", "medicine", "dose", "syrup", "balm", "మందు", "డోలో", "డోస్", "सिरप", "दवा", "दवाई"),
        ("alert_staff", "schedule_callback"),
    ),
    _Intent("report", ("report", "రిపోర్ట్", "रिपोर्ट"), ("send_whatsapp_template",)),
    _Intent(
        "reschedule",
        ("reschedule", "move it", "shift", "postpone", "మార్చ", "आगे कर", "बदल"),
        ("reschedule",),
    ),
    _Intent(
        "booking",
        (
            "book",
            "appointment",
            "slot",
            "visit",
            "అపాయింట్‌మెంట్",
            "బుక్",
            "విజిట్",
            "अपॉइंटमेंट",
            "बुक",
            "विज़िट",
        ),
        ("book_slot",),
    ),
    _Intent(
        "price",
        (
            "fee",
            "cost",
            "price",
            "rate",
            "charge",
            "how much",
            "ఎంత",
            "ఫీజు",
            "రేట్",
            "कितन",
            "फीस",
            "कीमत",
        ),
        category="prices",
    ),
    _Intent(
        "timings",
        ("time", "timing", "open", "hours", "sunday", "టైమ్", "ఆదివారం", "ఓపెన్", "समय", "खुला", "कब"),
        category="timings",
    ),
    _Intent(
        "location",
        (
            "where",
            "address",
            "location",
            "parking",
            "ఎక్కడ",
            "అడ్రస్",
            "పార్కింగ్",
            "कहाँ",
            "पता",
            "पार्किंग",
        ),
        category="location",
    ),
)

_TEMPLATES: dict[str, dict[BaseLanguage, str]] = {
    "emergency": {
        "en": "Please call 112 immediately. I'm connecting you to our staff right now.",
        "te": "దయచేసి వెంటనే 112 కి కాల్ చేయండి. నేను ఇప్పుడే మా స్టాఫ్‌కి కనెక్ట్ చేస్తున్నాను.",
        "hi": "कृपया तुरंत 112 पर कॉल कीजिए। मैं अभी आपको हमारे स्टाफ़ से जोड़ रही हूँ।",
    },
    "opt_out": {
        "en": "Sorry for the trouble. We won't call you again.",
        "te": "క్షమించండి అండి. ఇకపై మీకు కాల్ చేయము.",
        "hi": "माफ़ कीजिए। अब आपको कॉल नहीं करेंगे।",
    },
    "human": {
        "en": "Sure, I'm connecting you to our team now.",
        "te": "సరే అండి, ఇప్పుడే మా టీమ్‌కి కనెక్ట్ చేస్తున్నాను.",
        "hi": "ठीक है, मैं अभी आपको हमारी टीम से जोड़ रही हूँ।",
    },
    "medical": {
        "en": "Sorry, I can't advise on medicines. I'll ask the doctor to call you.",
        "te": "క్షమించండి, మందుల గురించి నేను చెప్పలేను. డాక్టర్ గారిని మీకు కాల్ చేయమని చెప్తాను.",
        "hi": "माफ़ कीजिए, दवाई के बारे में मैं नहीं बता सकती। मैं डॉक्टर से आपको कॉल करवाती हूँ।",
    },
    "report": {
        "en": "Reports are usually ready within 24 hours. I'll send yours on WhatsApp.",
        "te": "రిపోర్ట్స్ సాధారణంగా 24 గంటల్లో వస్తాయి. మీ రిపోర్ట్ వాట్సాప్‌లో పంపిస్తాను.",
        "hi": "रिपोर्ट आमतौर पर 24 घंटे में आ जाती है। मैं आपकी रिपोर्ट व्हाट्सऐप पर भेज दूँगी।",
    },
    "reschedule": {
        "en": "Done, I've moved your appointment. You'll get the details on WhatsApp.",
        "te": "సరే అండి, మీ అపాయింట్‌మెంట్ మార్చాను. వివరాలు వాట్సాప్‌లో వస్తాయి.",
        "hi": "ठीक है, आपका अपॉइंटमेंट बदल दिया है। डिटेल्स व्हाट्सऐप पर आ जाएँगी।",
    },
    "booking": {
        "en": "Done, I've booked your slot. You'll get the details on WhatsApp.",
        "te": "సరే అండి, మీ స్లాట్ బుక్ చేశాను. వివరాలు వాట్సాప్‌లో వస్తాయి.",
        "hi": "ठीक है, आपका स्लॉट बुक कर दिया है। डिटेल्स व्हाट्सऐप पर आ जाएँगी।",
    },
    "fact": {"en": "{label}: {value}.", "te": "{value} అండి.", "hi": "{value}।"},
    "unknown": {
        "en": "Let me check that with the team and get back to you on WhatsApp.",
        "te": "ఆ వివరాలు టీమ్‌తో కన్ఫర్మ్ చేసి వాట్సాప్‌లో చెప్తాను అండి.",
        "hi": "मैं टीम से पता करके आपको व्हाट्सऐप पर बताती हूँ।",
    },
}


def _pick_fact(pack: EmployeePack, category: FactCategory, said: str) -> Fact | None:
    candidates = [f for f in pack.facts if f.category == category]

    def score(fact: Fact) -> int:
        words = set((fact.key.replace("_", " ") + " " + fact.label).lower().split())
        return sum(1 for w in words if len(w) > 2 and w in said)

    return max(candidates, key=score, default=None)


class _Session:
    def __init__(self, pack: EmployeePack, context: CallContext) -> None:
        self._pack, self._context = pack, context
        self._lang = to_base(context.language)

    async def start(self) -> AgentReply:
        table = getattr(self._pack.greeting, self._context.direction)
        return AgentReply(text=table[self._lang])

    async def send(self, caller_text: str, *, interrupt: bool = False) -> AgentReply:
        said = normalise(caller_text)
        intent = next((i for i in _INTENTS if any(k in said for k in i.keywords)), None)
        if intent is None:
            return AgentReply(
                text=_TEMPLATES["unknown"][self._lang],
                actions=(Action("schedule_callback"),),
            )
        if intent.category is not None:
            fact = _pick_fact(self._pack, intent.category, said)
            if fact is None:
                return AgentReply(text=_TEMPLATES["unknown"][self._lang])
            value = fact.localized.get(self._lang, fact.value)
            text = _TEMPLATES["fact"][self._lang].format(label=fact.label, value=value)
            return AgentReply(text=text, actions=(Action("lookup_fact", {"key": fact.key}),))
        return AgentReply(
            text=_TEMPLATES[intent.name][self._lang],
            actions=tuple(Action(a) for a in intent.actions),
            end_call="end_call" in intent.actions,
        )

    async def close(self) -> None:
        return None


class ScriptedAgent:
    name = "scripted"

    async def open(self, pack: EmployeePack, context: CallContext) -> ConversationSession:
        return _Session(pack, context)
