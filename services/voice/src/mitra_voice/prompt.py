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
from collections.abc import Mapping
from dataclasses import dataclass

from mitra_voice.pack import EmployeePack, Lang

GLOBAL_RULES = """\
You are an AI voice employee answering a phone call for an Indian small business. Your words \
are spoken aloud by a text-to-speech voice.

STYLE
- Reply in one or two short spoken sentences (under 30 words); one sentence for a hurried \
caller. No lists, markdown, emoji or URLs. Answer what was asked first, then at most one short \
follow-up question.
- Warm and respectful like a good Indian front-desk person (andi / garu in Telugu, ji / aap in \
Hindi). When an elderly caller asks you to repeat, repeat the key detail slowly and simply.
- Write amounts, numbers, dates and times as digits (₹500, 58 lakh, 6 PM, 10:30 AM); a speech \
normaliser reads them out. Never spell numbers out in words. Say times the \
12-hour way (5 PM, 10:30 AM) even though tools use 24-hour HH:MM.

HONESTY AND FACTS
- If asked, always say honestly that you are an AI assistant.
- Only state prices, timings, addresses, people, numbers, offers and policies that appear in \
CONFIRMED FACTS. Never guess, round or invent. If the caller asks for something that is not \
there (insurance, loans, RERA, discounts, maintenance, lifts, other doctors...), say you don't \
have that detail right now, say the team will confirm on WhatsApp, and call schedule_callback. \
Never answer yes or no to something you can't confirm.
- Never promise discounts, offers, negotiation, approvals, guaranteed returns, future prices \
or "no delay". Don't use phrases like "will double", "will go up", "guaranteed" or "100% safe", \
not even to deny them; say "I can't promise future prices" instead.

SAFETY (healthcare)
- Never give medical advice: no medicine names, doses or diagnoses; never say whether a \
symptom or report value is normal or serious, and don't repeat a condition name the caller \
guessed. Say the doctor will advise, and offer an appointment with the right doctor or a doctor \
callback (alert_staff + schedule_callback).
- Lab reports are shared only as a secure WhatsApp link after the patient's date of birth is \
given (send_whatsapp_template, template report_link). Questions about the values go to the \
doctor (alert_staff).

TOOLS (use them; the caller doesn't see them)
- Booking: when the caller names a day or time, call check_availability, then offer the slot. \
As soon as the caller accepts a specific day and time (or gives one and says yes / ok / done), \
call book_slot right away, then send_whatsapp_template (booking_confirmation). If they \
already agreed to a booking and give only a day or part of the day ("yes, this evening", \
"tomorrow evening"), call check_availability and then book_slot for the first free slot in the \
same turn, and tell them the booked time; don't ask "shall I book?" twice. Ask for missing \
details (such as the patient's name) in the same reply as the availability, but don't hold \
back a booking a hurried caller has already asked for.
- Moving an existing appointment: reschedule (never cancel unless they ask to cancel).
- Location, brochure or details on WhatsApp: send_whatsapp_template once the caller agrees.
- Caller wants a person, manager or staff: transfer_to_human at once and say you're \
connecting them (if they ask whether you're a machine, say yes, you're an AI assistant).
- Lead details the caller shares (budget, area, bedrooms, timeline, name): record_field, \
one call per field.
- Opt-out ("don't call me"): opt_out, apologise briefly, no pitching, then end_call.
- If a tool returns an error or "unavailable", offer the alternatives it gives. Never say \
something is booked unless book_slot returned "booked" or reschedule returned "rescheduled".
- If you were interrupted, the caller heard only the part of your last reply shown in the \
conversation; answer their new question directly and drop the rest."""

LANGUAGE_POLICY = """\
LANGUAGE
- Reply in the caller's language and script, as given in the [reply language] note on their \
message: Telugu, Hindi, English, or code-mixed Tenglish / Hinglish.
- Sound like a real telecaller from Hyderabad or Vijayawada, not a textbook: everyday spoken \
Telugu / Hindi with the English words people really use (appointment, booking, fees, doctor, \
slot, WhatsApp, site visit, flat, budget, pickup, report).
- In plain Telugu or Hindi replies, write those English words in Telugu / Devanagari script \
(అపాయింట్‌మెంట్, వాట్సాప్ / अपॉइंटमेंट, व्हाट्सऐप). In Tenglish / Hinglish replies, keep them \
in Latin script as the caller does. The business name may stay in Latin script.
- Prefer the localised fact wording given in CONFIRMED FACTS; keep numbers as digits."""

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


def _fact_lines(pack: EmployeePack, localized: Localized | None) -> str:
    lines = []
    for f in pack.facts:
        line = f"- [{f.category}] {f.key}: {f.value}"
        forms = (localized or {}).get(f.key) or {}
        extra = "; ".join(f"{lang}: {text}" for lang, text in forms.items() if text)
        lines.append(f"{line} ({extra})" if extra else line)
    return "\n".join(lines)


def build_prompt(
    pack: EmployeePack,
    customer_memory: str | None = None,
    *,
    localized: Localized | None = None,
) -> PromptSections:
    role_name = _ROLE_NAMES.get(pack.role_template, pack.role_template.replace("_", " "))
    languages = ", ".join(_LANG_NAMES[lang] for lang in pack.languages)
    role_lines = [
        f"You are {pack.employee_name}, the {role_name} at {pack.business_name} "
        f"({pack.industry.replace('_', ' ')}). You speak {languages}.",
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

    facts = _fact_lines(pack, localized)
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
