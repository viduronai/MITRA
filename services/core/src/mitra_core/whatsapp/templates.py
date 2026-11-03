"""Approved WhatsApp message templates (docs/whatsapp-templates.md), in code.

Every template is Utility, uses NAMED parameters and exists in en / hi / te. ``TEMPLATES`` must
stay identical to the doc: the bodies here are what Meta approved, and the tests check that
every ``{{param}}`` in every language matches ``params`` and that no body starts or ends with a
variable. Code never sends a template that is not in this registry (``spec`` raises).

Variables are flattened before sending (``flatten``): Meta rejects line breaks, tabs and more
than 4 spaces in a row inside a variable.
"""

# ruff: noqa: E501  (bodies are kept verbatim as approved by Meta)

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

Lang = Literal["en", "hi", "te"]
LANGUAGES: tuple[Lang, ...] = ("en", "hi", "te")
# App links ("Open in Mitra", "Open report") use the ``app_base_url`` setting, never a
# hard-coded domain: ``url_base=None`` on a URL button means "the app". TODO(founder): domain.
APP_URL_BASE: str | None = None
MAPS_URL_BASE = "https://maps.app.goo.gl/"
PAY_URL_BASE = "https://rzp.io/"


@dataclass(frozen=True, slots=True)
class TemplateButton:
    kind: Literal["quick_reply", "url"]
    title: str
    # url buttons: the approved base; the code sends only the dynamic suffix ({{1}}).
    url_base: str | None = None
    # url buttons without a dynamic part need no parameter at send time.
    dynamic: bool = True


@dataclass(frozen=True, slots=True)
class TemplateSpec:
    name: str
    params: tuple[str, ...]
    bodies: dict[Lang, str]
    buttons: tuple[TemplateButton, ...] = ()
    header: Literal["document"] | None = None
    category: str = "UTILITY"

    @property
    def quick_replies(self) -> tuple[TemplateButton, ...]:
        return tuple(b for b in self.buttons if b.kind == "quick_reply")

    @property
    def dynamic_url(self) -> TemplateButton | None:
        return next((b for b in self.buttons if b.kind == "url" and b.dynamic), None)


def _qr(title: str) -> TemplateButton:
    return TemplateButton("quick_reply", title)


def _url(title: str, base: str | None, *, dynamic: bool = True) -> TemplateButton:
    return TemplateButton("url", title, base, dynamic)


_SPECS = (
    # --- A. customers --------------------------------------------------------------------------
    TemplateSpec(
        "call_heads_up",
        ("name", "business", "minutes"),
        {
            "en": "Hi {{name}}, this is {{business}}. We'll call you in about {{minutes}} minutes about your enquiry.",
            "hi": "नमस्ते {{name}}, हम {{business}} से हैं। आपकी enquiry के बारे में हम लगभग {{minutes}} मिनट में आपको call करेंगे।",
            "te": "నమస్కారం {{name}}, మేము {{business}} నుంచి. మీ enquiry గురించి సుమారు {{minutes}} నిమిషాల్లో మీకు call చేస్తాం.",
        },
        (_qr("Call me later"), _qr("Don't call me")),
    ),
    TemplateSpec(
        "missed_call_callback",
        ("business", "time"),
        {
            "en": "Thanks for calling {{business}}. We'll call you back at {{time}}.",
            "hi": "नमस्ते! {{business}} को call करने के लिए धन्यवाद। हम आपको {{time}} बजे call करेंगे।",
            "te": "నమస్కారం! {{business}}కి call చేసినందుకు ధన్యవాదాలు. మేము మీకు {{time}}కి తిరిగి call చేస్తాం.",
        },
    ),
    TemplateSpec(
        "booking_confirmation",
        ("name", "business", "when"),
        {
            "en": "Hi {{name}}, your appointment at {{business}} is confirmed for {{when}}.",
            "hi": "नमस्ते {{name}}, {{business}} में आपकी appointment {{when}} के लिए confirm हो गई है।",
            "te": "నమస్కారం {{name}}, {{business}}లో మీ appointment {{when}}కి confirm అయింది.",
        },
        (_qr("Change time"), _url("Get directions", MAPS_URL_BASE)),
    ),
    TemplateSpec(
        "appointment_reminder",
        ("business", "when"),
        {
            "en": "Reminder: your appointment at {{business}} is on {{when}}.",
            "hi": "याद दिला रहे हैं: {{business}} में आपकी appointment {{when}} को है।",
            "te": "గుర్తు చేస్తున్నాం: {{business}}లో మీ appointment {{when}}న ఉంది.",
        },
        (_qr("I'll come"), _qr("Change time")),
    ),
    TemplateSpec(
        "share_document",
        ("document", "business"),
        {
            "en": "Here is the {{document}} from {{business}} that you asked for.",
            "hi": "आपने जो {{document}} माँगा था, वह {{business}} की ओर से यहाँ है।",
            "te": "మీరు అడిగిన {{document}} ఇదిగో, {{business}} నుంచి.",
        },
        header="document",
    ),
    TemplateSpec(
        "share_location",
        ("business", "address"),
        {
            "en": "You can find {{business}} at {{address}}. Tap below for directions.",
            "hi": "पता: {{business}}, {{address}}. रास्ते के लिए नीचे tap करें।",
            "te": "అడ్రస్: {{business}}, {{address}}. దారి కోసం కింద tap చేయండి.",
        },
        (_url("Open map", MAPS_URL_BASE),),
    ),
    TemplateSpec(
        "enquiry_follow_up",
        ("name", "business", "topic"),
        {
            "en": "Hi {{name}}, {{business}} here, following up on your enquiry about {{topic}}. Reply here or tap below and we'll call you.",
            "hi": "नमस्ते {{name}}, {{business}} से बात कर रहे हैं, {{topic}} के बारे में आपकी enquiry पर follow-up। यहाँ reply करें या नीचे tap करें, हम call करेंगे।",
            "te": "నమస్కారం {{name}}, {{business}} నుంచి, {{topic}} గురించి మీ enquiry మీద follow-up. ఇక్కడ reply చేయండి లేదా కింద tap చేయండి, మేము call చేస్తాం.",
        },
        (_qr("Call me"), _qr("Not now")),
    ),
    TemplateSpec(
        "payment_link",
        ("name", "business", "purpose", "amount"),
        {
            "en": "Hi {{name}}, here is your payment link from {{business}} for {{purpose}}: ₹{{amount}}. You can pay by UPI or card.",
            "hi": "नमस्ते {{name}}, {{business}} की ओर से {{purpose}} के लिए आपका payment link: ₹{{amount}}. UPI या card से pay कर सकते हैं।",
            "te": "నమస్కారం {{name}}, {{purpose}} కోసం {{business}} నుంచి మీ payment link: ₹{{amount}}. UPI లేదా card తో pay చేయవచ్చు.",
        },
        (_url("Pay now", PAY_URL_BASE),),
    ),
    TemplateSpec(
        "payment_reminder",
        ("business", "amount", "purpose", "due"),
        {
            "en": "A gentle reminder from {{business}}: ₹{{amount}} for {{purpose}} is due on {{due}}.",
            "hi": "एक reminder, {{business}} की ओर से: {{purpose}} के ₹{{amount}} की due date {{due}} है।",
            "te": "ఒక reminder, {{business}} నుంచి: {{purpose}} కోసం ₹{{amount}} చెల్లించాల్సిన తేదీ {{due}}.",
        },
        (_url("Pay now", PAY_URL_BASE), _qr("Already paid")),
    ),
    TemplateSpec(
        "payment_received",
        ("name", "business", "amount", "purpose"),
        {
            "en": "Thank you, {{name}}. {{business}} has received ₹{{amount}} for {{purpose}}.",
            "hi": "धन्यवाद {{name}}। {{business}} को {{purpose}} के लिए ₹{{amount}} मिल गए हैं।",
            "te": "ధన్యవాదాలు {{name}}. {{purpose}} కోసం ₹{{amount}} {{business}}కి అందాయి.",
        },
    ),
    TemplateSpec(
        "payment_upi_request",
        ("name", "business", "amount", "purpose", "upi_id"),
        {
            "en": "Hi {{name}}, {{business}} has requested ₹{{amount}} for {{purpose}}. Please pay to UPI ID {{upi_id}}. Reply PAID once done.",
            "hi": "नमस्ते {{name}}, {{business}} ने {{purpose}} के लिए ₹{{amount}} का request भेजा है। कृपया UPI ID {{upi_id}} पर pay करें। Pay करने के बाद PAID reply करें।",
            "te": "నమస్కారం {{name}}, {{purpose}} కోసం {{business}} ₹{{amount}} request చేసింది. దయచేసి UPI ID {{upi_id}}కి pay చేయండి. Pay చేశాక PAID అని reply చేయండి.",
        },
    ),
    # --- B. owners, managers, staff --------------------------------------------------------------
    TemplateSpec(
        "owner_alert",
        ("title", "business", "detail"),
        {
            "en": "Alert: {{title}} at {{business}}. {{detail}} Open Mitra for details.",
            "hi": "Alert: {{business}} में {{title}}। {{detail}} पूरी जानकारी Mitra में देखें।",
            "te": "Alert: {{business}}లో {{title}}. {{detail}} పూర్తి వివరాలు Mitraలో చూడండి.",
        },
        (_url("Open in Mitra", APP_URL_BASE),),
    ),
    TemplateSpec(
        "daily_report",
        ("business", "calls", "booked", "attention"),
        {
            "en": "Good morning! Yesterday at {{business}}: {{calls}} calls, {{booked}} booked, {{attention}} need your attention.",
            "hi": "सुप्रभात! कल {{business}} में: {{calls}} calls, {{booked}} booking, {{attention}} पर आपका ध्यान चाहिए।",
            "te": "శుభోదయం! నిన్న {{business}}లో: {{calls}} calls, {{booked}} bookings, {{attention}} విషయాలు మీరు చూడాలి.",
        },
        (_url("Open report", APP_URL_BASE),),
    ),
    TemplateSpec(
        "approval_request",
        ("business", "employee", "summary"),
        {
            "en": "Approval needed at {{business}}: {{employee}} needs your OK. {{summary}} Tap a button below.",
            "hi": "मंज़ूरी चाहिए, {{business}}: {{employee}} को आपकी मंज़ूरी चाहिए। {{summary}} नीचे एक button tap करें।",
            "te": "Approval కావాలి, {{business}}: {{employee}}కి మీ approval కావాలి. {{summary}} కింద ఒక button tap చేయండి.",
        },
        (_qr("Approve"), _qr("Decline")),
    ),
    TemplateSpec(
        "staff_handoff",
        ("business", "action", "customer", "brief"),
        {
            "en": "Task from {{business}}: please {{action}} {{customer}}. {{brief}} Tap Done when finished.",
            "hi": "नया काम, {{business}} से: कृपया {{customer}} को {{action}}। {{brief}} हो जाने पर Done tap करें।",
            "te": "కొత్త పని, {{business}} నుంచి: దయచేసి {{customer}}కి {{action}}. {{brief}} అయ్యాక Done tap చేయండి.",
        },
        (_qr("Done"),),
    ),
)
TEMPLATES: dict[str, TemplateSpec] = {s.name: s for s in _SPECS}

# Longest value per parameter after flattening (Meta's own cap is far higher; these keep the
# message readable). Anything not listed gets DEFAULT_MAX.
DEFAULT_MAX = 80
MAX_LEN: dict[str, int] = {
    "detail": 300,
    "summary": 300,
    "brief": 300,
    "address": 200,
    "topic": 100,
    "purpose": 100,
    "document": 60,
    "business": 60,
    "name": 60,
    "customer": 80,
    "title": 60,
    "upi_id": 60,
}

# Name fallback when the customer's name is unknown (no English "there" in hi / te).
# TODO(i18n): native-speaker review with the templates themselves.
NAME_FALLBACK: dict[Lang, str] = {"en": "there", "hi": "जी", "te": "అండి"}
# Telugu adds the honorific to a known name here, not in the template, so that an unknown name
# reads "నమస్కారం అండి," instead of "నమస్కారం <word> గారు,". TODO(i18n): founder review.
TE_HONORIFIC = "గారు"

# staff_handoff ``action`` per language (the doc requires translated values).
STAFF_ACTIONS: dict[str, dict[Lang, str]] = {
    "call_back": {"en": "call back", "hi": "call करें", "te": "call చేయండి"},
    "meet": {"en": "meet", "hi": "मिलें", "te": "కలవండి"},
    "help": {"en": "help", "hi": "मदद करें", "te": "సహాయం చేయండి"},
}

# owner_alert ``title`` per alert kind and language.
ALERT_TITLES: dict[str, dict[Lang, str]] = {
    "hot_lead": {"en": "Hot lead", "hi": "गरम लीड", "te": "హాట్ లీడ్"},
    "angry": {"en": "Upset customer", "hi": "नाराज़ ग्राहक", "te": "కోపంగా ఉన్న కస్టమర్"},
    "vip": {"en": "VIP caller", "hi": "VIP कॉलर", "te": "VIP కాలర్"},
    "urgent": {"en": "Urgent", "hi": "ज़रूरी", "te": "అత్యవసరం"},
    "payment_failed": {"en": "Payment failed", "hi": "पेमेंट फेल", "te": "పేమెంట్ విఫలం"},
    "campaign_paused": {
        "en": "List calling paused",
        "hi": "लिस्ट कॉलिंग रुकी",
        "te": "లిస్ట్ కాలింగ్ ఆగింది",
    },
    "payment_claimed": {
        "en": "Customer says they paid",
        "hi": "ग्राहक ने कहा पेमेंट कर दिया",
        "te": "కస్టమర్ పే చేశామన్నారు",
    },
    "whatsapp_blocked": {
        "en": "WhatsApp not sent",
        "hi": "WhatsApp नहीं गया",
        "te": "WhatsApp పంపలేదు",
    },
    "team_escalation": {
        "en": "Customer needs you",
        "hi": "ग्राहक को आपकी ज़रूरत",
        "te": "కస్టమర్‌కి మీరు కావాలి",
    },
}

_PARAM = re.compile(r"\{\{(\w+)\}\}")
_WS = re.compile(r"\s+")
_LINES = re.compile(r"[\r\n\v\f\u2028\u2029]+")
_ENDS = frozenset(".!?।:;…·,")
# Parameters followed by a new sentence in every body: they must end like a sentence.
SENTENCE_PARAMS = frozenset({"detail", "summary", "brief"})


class TemplateError(ValueError):
    """Unknown template, unknown language or missing parameters."""


def spec(name: str) -> TemplateSpec:
    try:
        return TEMPLATES[name]
    except KeyError:
        raise TemplateError(f"unknown WhatsApp template {name!r}") from None


def body_params(body: str) -> list[str]:
    return _PARAM.findall(body)


def flatten(value: object, limit: int = DEFAULT_MAX) -> str:
    """One line: no line breaks, tabs or runs of spaces; trimmed to ``limit`` characters.

        Former lines stay separate sentences: joined with ". " unless the line already ends with
        punctuation ("Paused
    No calling number" -> "Paused. No calling number").
    """
    text = ""
    for line in _LINES.split(str(value)):
        part = _WS.sub(" ", line).strip()
        if not part:
            continue
        if not text:
            text = part
        elif text[-1] in _ENDS:
            text += " " + part
        else:
            text += ". " + part
    if len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return text


def alert_title(kind: str, lang: Lang) -> str:
    titles = ALERT_TITLES.get(kind)
    if titles:
        return titles[lang]
    return kind.replace("_", " ").capitalize()


def name_value(name: str, lang: Lang) -> str:
    """The ``{{name}}`` value: "Ravi" / "Ravi గారు" (te), or the per-language fallback."""
    if not name:
        return NAME_FALLBACK[lang]
    return f"{name} {TE_HONORIFIC}" if lang == "te" else name


def prepare(name: str, lang: Lang, params: dict[str, object]) -> dict[str, str]:
    """Validate and flatten the named parameters for one template, in template order."""
    s = spec(name)
    if lang not in s.bodies:
        raise TemplateError(f"template {name!r} has no {lang!r} version")
    missing = [p for p in s.params if p not in params]
    if missing:
        raise TemplateError(f"template {name!r} is missing {', '.join(missing)}")
    out: dict[str, str] = {}
    for p in s.params:
        value = flatten(params[p], MAX_LEN.get(p, DEFAULT_MAX))
        if p == "name":
            value = name_value(value, lang)
        elif p in SENTENCE_PARAMS and value and value[-1] not in _ENDS:
            value += "."
        if not value:
            raise TemplateError(f"template {name!r}: {p} is empty")
        out[p] = value
    return out


def render(name: str, lang: Lang, values: dict[str, str]) -> str:
    """The text the recipient sees (stored, and shown by the simulator)."""
    return _PARAM.sub(lambda m: values.get(m.group(1), ""), spec(name).bodies[lang])
