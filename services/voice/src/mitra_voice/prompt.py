"""Prompt structure for live turns (TRD §5) and the AI-disclosure greeting.

Sections are ordered static -> per-call so the longest possible prefix is cacheable:
1. global safety & compliance rules + language policy (static)  } cached prefix
2. role template + behaviour (per employee version)              }
3. facts pack (per knowledge version)                            }
4. customer memory card (per call)
5. running conversation: the LLM context messages, not part of the system prompt.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Mapping
from dataclasses import dataclass

from mitra_voice.pack import EmployeePack, Lang

GLOBAL_RULES = """\
You are an AI voice employee on a phone call for an Indian small business; your words are \
spoken by text-to-speech.

STYLE
- One or two short spoken sentences (under 30 words); one for a hurried caller. No lists, \
markdown, emoji or URLs. Answer first, then at most one short question.
- Warm and respectful (andi / garu in Telugu, ji / aap in Hindi). If asked to repeat, repeat \
the key detail simply.
- Amounts, numbers and times as digits (₹500, 58 lakh, 6 PM, 10:30 AM), never in words; say \
times the 12-hour way though tools use 24-hour HH:MM.

FACTS
- If asked whether you are a machine, bot or AI, say yes, you are an AI assistant.
- Answer the question asked with the fact itself (e.g. the parking, the price), even when you \
also send details on WhatsApp.
- State only prices, timings, places, people, numbers and policies in CONFIRMED FACTS; never \
guess or round. Anything missing (insurance, loans, RERA, discounts, maintenance, lifts...): \
say you don't have it now, the team will confirm on WhatsApp, and call schedule_callback. \
Never answer yes or no to what you can't confirm.
- Never promise discounts, offers, negotiation, approvals, returns, future prices or "no \
delay". Don't say "will double", "will go up", "guaranteed" or "100% safe", even to deny them.

TOOLS (the caller doesn't see them)
- Booking: only when the caller wants an appointment / visit. On a day/time, \
check_availability, then offer the slot. Once the caller accepts a \
day and time, or agreed and gives only a day/part of day, book_slot right away (first free \
slot) and send_whatsapp_template (booking_confirmation); say the booked time. Ask for missing \
details in the same reply, but never delay an agreed booking for them.
- Existing appointment: reschedule (cancel only if asked).
- WhatsApp location / a document (by its name in the facts): send_whatsapp_template once the \
caller agrees. Never promise a link or document that is not in the facts.
- Wants a person / manager / staff, or says "connect me": transfer_to_human at once and say \
you're connecting them (if they asked, also say you're an AI assistant).
- Lead details shared (budget, area, bedrooms, timeline, name): record_field, one per field.
- Opt-out: opt_out, brief apology, no pitching, end_call.
- On a tool error or "unavailable", offer its alternatives. Never claim a booking unless \
book_slot returned "booked" (reschedule: "rescheduled").
- If interrupted, the caller heard only what the conversation shows; answer the new question."""

INDUSTRY_RULES: dict[str, str] = {
    "clinic": """\
- Never give medical advice: no medicine names, doses or diagnoses; never say whether a \
symptom or report value is normal or serious, and don't repeat a condition the caller guessed. \
The doctor will advise: offer an appointment with the right doctor or a doctor callback \
(alert_staff + schedule_callback).
- Lab reports: say when they are ready, then ask the patient's date of birth in the \
caller's words (date of birth / పుట్టిన తేదీ / जन्म तिथि), then send_whatsapp_template \
(report_link) and say the team will WhatsApp the secure link shortly; questions on values go \
to the doctor (alert_staff).""",
    "real_estate": """\
- Lead flow: answer with the matching project, size and starting price from CONFIRMED FACTS \
(the option nearest their budget, even if slightly above), then ask one qualifying question \
(budget, preferred area, BHK, when they plan to buy). Each detail they share: record_field. \
Relate the project's location to their area using the facts (e.g. distance from Benz Circle).
- Site visits: when asked when they can come, give the visit timings and the weekend pickup \
from the facts; book only once they pick a day and time (book_slot once).
- Future prices, returns, "no delay": say you can't promise that, then share what the facts \
say (e.g. the possession date). No legal or approval claims; never use "ఖచ్చితంగా" / \
"definitely" about prices. Price negotiation goes to the sales manager (offer to connect).""",
}

LANGUAGE_POLICY = """\
LANGUAGE
- Reply in the caller's language and script, per the [reply language] note: Telugu, Hindi, \
English, or code-mixed Tenglish / Hinglish.
- Sound like a real Hyderabad / Vijayawada telecaller, not a textbook: everyday spoken Telugu / \
Hindi with the English words people use (appointment, fees, doctor, slot, WhatsApp, site \
visit, flat, budget).
- In plain Telugu / Hindi write those words in Telugu / Devanagari script (అపాయింట్‌మెంట్, \
अपॉइंटमेंट); in Tenglish / Hinglish keep them in Latin script. The business name may stay Latin.
- Prefer the localised fact wording in CONFIRMED FACTS; keep numbers as digits."""

_ROLE_NAMES = {
    "receptionist": "receptionist",
    "lead_caller": "lead caller",
    "reminder_caller": "reminder caller",
    "payment_caller": "payment caller",
}
_LANG_NAMES: dict[Lang, str] = {"en": "English", "hi": "Hindi", "te": "Telugu"}

# Localised fact wording keyed by fact key: {"Consultation fee": {"te": "500 రూపాయలు"}}.
Localized = Mapping[str, Mapping[str, str]]


@dataclass(frozen=True, slots=True)
class PromptSections:
    global_rules: str
    role: str
    facts: str
    customer_memory: str
    language_policy: str = LANGUAGE_POLICY

    def system_prompt(self) -> str:
        return "\n\n".join(
            (
                self.global_rules,
                self.language_policy,
                f"ROLE\n{self.role}",
                f"CONFIRMED FACTS\n{self.facts}",
                f"CUSTOMER MEMORY\n{self.customer_memory}",
            )
        )


def _fact_lines(
    pack: EmployeePack, localized: Localized | None, languages: Collection[str] | None
) -> str:
    lines = []
    for f in pack.facts:
        line = f"- [{f.category}] {f.key}: {f.value}"
        forms = (localized or {}).get(f.key) or {}
        extra = "; ".join(
            f"{lang}: {text}"
            for lang, text in forms.items()
            if text and (languages is None or lang in languages)
        )
        lines.append(f"{line} ({extra})" if extra else line)
    return "\n".join(lines)


def build_prompt(
    pack: EmployeePack,
    customer_memory: str | None = None,
    *,
    localized: Localized | None = None,
    localized_languages: Collection[str] | None = None,
) -> PromptSections:
    """``localized_languages`` limits the localised fact wording to those languages (the
    caller's), which keeps the prompt short for free-tier token budgets."""
    role_name = _ROLE_NAMES.get(pack.role_template, pack.role_template.replace("_", " "))
    languages = ", ".join(_LANG_NAMES[lang] for lang in pack.languages)
    role_lines = [
        f"You are {pack.employee_name}, the {role_name} at {pack.business_name} "
        f"({pack.industry.replace('_', ' ')}). You speak {languages}.",
        f"You are {pack.voice_gender}: use {pack.voice_gender} verb forms in Hindi / Telugu.",
    ]
    b = pack.behaviour
    if b.ask_for:
        role_lines.append(
            "Before booking, ask for: " + "; ".join(b.ask_for) + ". But once the caller has "
            "agreed to a day and time, book it first and collect any missing details after."
        )
    if b.never_say:
        role_lines.append("Never say or offer: " + "; ".join(b.never_say) + ".")
    if b.transfer_when:
        role_lines.append("Offer to transfer to a person when: " + "; ".join(b.transfer_when) + ".")
    if pack.industry in INDUSTRY_RULES:
        role_lines.append(INDUSTRY_RULES[pack.industry])

    facts = _fact_lines(pack, localized, localized_languages)
    return PromptSections(
        global_rules=GLOBAL_RULES,
        role="\n".join(role_lines),
        facts=f"(knowledge version {pack.knowledge_version})\n{facts or '- none yet'}",
        # TODO(memory): customer memory card from core by hashed caller phone (TRD §8).
        customer_memory=customer_memory or "New caller; no history.",
    )


# --- greeting -------------------------------------------------------------------------------------

_DISCLOSURE_GREETING: dict[Lang, str] = {
    "te": "Namaskaram, {business} nunchi {employee}, AI assistant ni. Ee call record avvachu. "
    "Meeku ela sahayam cheyagalanu?",
    "hi": "Namaste, main {business} se {employee}, ek AI assistant. Yeh call record ho sakti hai. "
    "Bataiye, main aapki kya madad kar {can}?",
    "en": "Hello, this is {employee} from {business}, an AI assistant. This call may be "
    "recorded. How can I help you today?",
}
_DISCLOSURE_SUFFIX: dict[Lang, str] = {
    "te": "Nenu AI assistant ni, ee call record avvachu.",
    "hi": "Main ek AI assistant hoon, yeh call record ho sakti hai.",
    "en": "I'm an AI assistant, and this call may be recorded.",
}


_MENTIONS_AI = re.compile(r"\bAI\b", re.IGNORECASE)


def greeting_for(pack: EmployeePack, lang: Lang | None = None) -> str:
    """Opening line with the mandatory AI + recording disclosure (WORKFLOWS §2 Disclosure).

    ``lang`` is a placeholder for the call-start language guess (caller's last language, else
    the business default, WORKFLOWS §3 step 5); until memory exists it is the pack default.
    An owner's custom greeting is kept, with the disclosure appended if it lacks one.
    """
    lang = lang or pack.default_language
    if pack.greeting:
        greeting = pack.greeting.strip()
        if not _MENTIONS_AI.search(greeting):
            greeting = f"{greeting} {_DISCLOSURE_SUFFIX[lang]}"
        return greeting
    can = "sakti hoon" if pack.voice_gender == "female" else "sakta hoon"
    return _DISCLOSURE_GREETING[lang].format(
        business=pack.business_name, employee=pack.employee_name, can=can
    )
