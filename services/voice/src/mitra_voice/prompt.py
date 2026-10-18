"""Prompt structure for live turns (TRD §5) and the AI-disclosure greeting.

Sections are ordered static -> per-call so the longest possible prefix is cacheable:
1. global safety & compliance rules (static)      } cached prefix
2. role template + behaviour (per employee version) }
3. facts pack (per knowledge version)              }
4. customer memory card (per call)
5. running conversation: the LLM context messages, not part of the system prompt.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from mitra_voice.pack import EmployeePack, Lang

GLOBAL_RULES = """\
You are an AI voice employee answering a phone call for an Indian small business.
- This is a phone call: reply in one or two short spoken sentences (under 30 words). No lists, \
markdown, emoji or URLs.
- Reply in the caller's language (Telugu, Hindi or English); natural code-mixing is fine.
- Only state prices, timings, addresses, numbers and policies that appear in CONFIRMED FACTS. \
If a fact is missing, say you will confirm with the team and follow up on WhatsApp. Never guess.
- Write amounts, numbers, dates and times as digits (e.g. ₹500, 5 PM); a speech normaliser \
reads them out naturally.
- If asked, always say honestly that you are an AI assistant.
- Never give medical, legal or financial advice. Offer to connect the caller with a person instead.
- If you were interrupted, the caller heard only the part of your last reply shown in the \
conversation; continue from there."""

_ROLE_NAMES = {
    "receptionist": "receptionist",
    "lead_caller": "lead caller",
    "reminder_caller": "reminder caller",
    "payment_caller": "payment caller",
}
_LANG_NAMES: dict[Lang, str] = {"en": "English", "hi": "Hindi", "te": "Telugu"}


@dataclass(frozen=True, slots=True)
class PromptSections:
    global_rules: str
    role: str
    facts: str
    customer_memory: str

    def system_prompt(self) -> str:
        return "\n\n".join(
            (
                self.global_rules,
                f"ROLE\n{self.role}",
                f"CONFIRMED FACTS\n{self.facts}",
                f"CUSTOMER MEMORY\n{self.customer_memory}",
            )
        )


def build_prompt(pack: EmployeePack, customer_memory: str | None = None) -> PromptSections:
    role_name = _ROLE_NAMES.get(pack.role_template, pack.role_template.replace("_", " "))
    languages = ", ".join(_LANG_NAMES[lang] for lang in pack.languages)
    role_lines = [
        f"You are {pack.employee_name}, the {role_name} at {pack.business_name} "
        f"({pack.industry.replace('_', ' ')}). You speak {languages}.",
    ]
    b = pack.behaviour
    if b.ask_for:
        role_lines.append("Before booking, ask for: " + "; ".join(b.ask_for) + ".")
    if b.never_say:
        role_lines.append("Never say or offer: " + "; ".join(b.never_say) + ".")
    if b.transfer_when:
        role_lines.append("Offer to transfer to a person when: " + "; ".join(b.transfer_when) + ".")

    facts = "\n".join(f"- [{f.category}] {f.key}: {f.value}" for f in pack.facts)
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
