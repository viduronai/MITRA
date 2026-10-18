"""Deterministic guardrails around the LLM (08-COMPLIANCE §4-5, TRD §6). They run in code on
every turn, whatever the prompt says.

Before the LLM (:func:`pre_check`):
- **Emergency** keywords (en/hi/te, incl. code-mixed and romanised) short-circuit the turn:
  urge calling 112, then ``transfer_to_human`` + ``alert_staff``. No LLM call, no fees.
- **Opt-out** phrases: ``opt_out`` + ``end_call`` and a polite close, nothing else.
- **Medical-advice** requests: the LLM still answers (it may offer the right doctor), but with a
  turn-level instruction to refuse; the post-check enforces it.

After the LLM (:func:`post_check`), sentence by sentence:
- every ₹ amount must appear in the facts pack (or have been said by the caller);
- clinic: no medicine names, doses, dose frequencies or diagnoses; on a medical turn also no
  condition names or "your report is normal";
- real estate: no guaranteed returns / legal-approval claims.
An offending sentence is dropped and replaced (once) by a safe deferral in the caller's language.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Literal

from mitra_voice.brain.language import CallerLanguage, base_language
from mitra_voice.pack import EmployeePack, Industry

GuardKind = Literal["emergency", "opt_out", "medical"]
Violation = Literal["amount", "medical", "claim"]

# --- text helpers ---------------------------------------------------------------------------------

_INDIC_DIGITS = str.maketrans("౦౧౨౩౪౫౬౭౮౯०१२३४५६७८९", "01234567890123456789")
_DIGIT_COMMA = re.compile(r"(?<=\d),(?=\d)")


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFC", text).translate(_INDIC_DIGITS).casefold()
    return text.replace("‌", "").replace("‍", "")


_NUM = r"\d+(?:\.\d+)?"
_UNIT = r"lakhs?|lacs?|crores?|cr(?![a-z])|k(?![a-z])|లక్ష\S*|కోటి|కోట్ల\S*|लाख|करोड़?"
_RUPEES = r"rupees?|రూపాయ\S*|रुपये|रुपए|रुपया"
_MONEY = re.compile(
    rf"(?:₹|(?<![a-z])rs\.?|(?<![a-z])inr)\s?(?P<a>{_NUM})\s*(?P<au>{_UNIT})?"
    rf"|(?P<b>{_NUM})\s*(?P<bu>{_UNIT}|{_RUPEES})"
)


def _multiplier(unit: str | None) -> int:
    if not unit:
        return 1
    if unit.startswith(("lakh", "lac", "లక్ష", "लाख")):
        return 100_000
    if unit.startswith(("cr", "కోట", "కోటి", "करोड")):
        return 10_000_000
    return 1_000 if unit == "k" else 1


def money_amounts(text: str) -> list[int]:
    """Rupee amounts said with a currency marker or a lakh/crore unit, in rupees. Bare numbers
    ("call 112", "1,150 sq ft") are deliberately not money."""
    amounts: list[int] = []
    for m in _MONEY.finditer(_DIGIT_COMMA.sub("", _norm(text))):
        number = m.group("a") or m.group("b")
        unit = m.group("au") if m.group("a") else m.group("bu")
        amounts.append(round(float(number) * _multiplier(unit)))
    return amounts


def allowed_amounts(pack: EmployeePack, caller_texts: Iterable[str] = ()) -> set[int]:
    allowed: set[int] = set()
    for fact in pack.facts:
        allowed.update(money_amounts(fact.value))
    for text in caller_texts:
        allowed.update(money_amounts(text))
    return allowed


_SENTENCE = re.compile(r"(?<=[.!?।])\s+|\n+")
_ABBREV = re.compile(r"(?<![A-Za-z])(Dr|Mr|Mrs|Ms|No|St|Rd|vs|डॉ|డా|శ్రీ|श्री)\.\s+")


def split_sentences(text: str) -> list[str]:
    """Sentences, keeping "Dr. Kavitha" / "Road No. 5" together."""
    protected = _ABBREV.sub(lambda m: f"{m.group(1)}.⁠", text.strip())
    parts = [p.replace("⁠", " ").strip() for p in _SENTENCE.split(protected)]
    return [p for p in parts if p]


# --- pre-check patterns ---------------------------------------------------------------------------

_EMERGENCY = re.compile(
    r"chest pain|pain in (?:my |his |her )?chest|heart attack|can'?t breathe|cannot breathe|"
    r"not breathing|difficulty (?:in )?breathing|unconscious|collapsed|fainted|passed out|"
    r"not responding|bleeding|blood loss|accident|suicid|kill (?:my|him|her|them)sel|"
    r"end (?:my|his|her) life|overdose|poison|seizure|choking|stroke\b|"
    r"सीने में (?:तेज़ |तेज )?दर्द|छाती में (?:तेज़ |तेज )?दर्द|दिल का दौरा|हार्ट अटैक|"
    r"सा(?:ँ|ं)स (?:नहीं|लेने में तकलीफ़?)|बेहोश|खून बह|ब्लीडिंग|एक्सीडेंट|दुर्घटना|आत्महत्या|"
    r"सुसाइड|खुदकुशी|ख़ुदकुशी|जान दे|ज़हर खा|जहर खा|दौरा पड़|"
    r"ఛాతీ ?(?:లో )?నొప్పి|ఛాతి ?(?:లో )?నొప్పి|గుండె నొప్పి|హార్ట్ అటాక్|ఊపిరి ఆడ|"
    r"శ్వాస (?:ఆడ|తీసుకోలే)|స్పృహ (?:లేదు|తప్పి|కోల్పో)|రక్తం (?:కారు|పోతు|వస్తు)|బ్లీడింగ్|"
    r"యాక్సిడెంట్|ప్రమాదం జరిగ|ఆత్మహత్య|సూసైడ్|చనిపోతా|విషం తాగ|ఫిట్స్|"
    r"seene me(?:in)? dard|behosh|chaathi noppi|chathi noppi|aatmahatya|atmahatya",
    re.IGNORECASE,
)
_MENTAL_HEALTH = re.compile(
    r"suicid|kill (?:my|him|her|them)sel|end (?:my|his|her) life|आत्महत्या|सुसाइड|खुदकुशी|"
    r"ख़ुदकुशी|जान दे|ఆత్మహత్య|సూసైడ్|చనిపోతా|aatmahatya|atmahatya",
    re.IGNORECASE,
)
_OPT_OUT = re.compile(
    r"(?:don'?t|do not|never|stop) (?:ever )?call(?:ing)?(?: me| us| this number)?|"
    r"remove my (?:number|name)|take me off|unsubscribe|"
    r"(?:कॉल|call|फ़ोन|फोन|phone) (?:मत|न|ना) (?:करो|करें|करना|कीजिए|करिए|करिये)|"
    r"(?:मत|ना) (?:करो|करना) (?:कॉल|call|फोन)|नंबर हटा|number हटा|"
    r"(?:కాల్|call|ఫోన్|phone) (?:చేయకండి|చెయ్యకండి|చేయొద్దు|చెయ్యొద్దు|చేయవద్దు)|"
    r"నంబర్ (?:తీసేయండి|తీసివేయండి)|number (?:తీసేయండి|తీసివేయండి)|"
    r"call (?:mat|mat karo|cheyakandi|cheyyakandi|cheyodhu)|mat karo call",
    re.IGNORECASE,
)
_MEDICAL = re.compile(
    r"\b(?:which|what|any) (?:tablet|medicine|syrup|drug|ointment|balm|cream|antibiotic)|"
    r"should i (?:take|give|apply)|(?:can|could) i (?:take|give|apply) (?:a |the |some |any )?"
    r"(?:tablet|medicine|syrup|dolo|crocin|paracetamol|balm|cream|ointment|antibiotic)|"
    r"how many (?:tablets|times|ml|mg)|"
    r"\bdose\b|dosage|double dose|\bis (?:it|this) (?:\w+ )?(?:arthritis|serious|normal|cancer|"
    r"infection|viral|gastric|ulcer|dengue|typhoid|diabetes|bp)|is (?:my|the) (?:report|result|"
    r"tsh|sugar|bp|count)\b.{0,20}(?:normal|high|low|ok)|"
    r"कौन (?:सी|सा) (?:दवा|दवाई|गोली|सिरप|टैबलेट|tablet|syrup)|कितने ml|कितनी गोली|खुराक|"
    r"डोज़|डोज|(?:tsh|sugar|शुगर|बीपी|bp|report|रिपोर्ट|value)\S*.{0,15}"
    r"(?:ज़्यादा|ज्यादा|कम|नॉर्मल|normal)|"
    r"మందు|మాత్ర|టాబ్లెట్|సిరప్|డోస్|వేసుకోవచ్చా|వేసుకోవాలి|నార్మల్‌?గా ఉందా|"
    r"(?:problem|ప్రాబ్లం|ulcer|అల్సర్|gastric|గ్యాస్ట్రిక్) ?ఆ\b|ఏ జబ్బు|"
    r"kaun si dawa|kitni goli|dawai",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class GuardHit:
    """A pre-LLM guardrail decision. ``reply`` is set when the turn is fully short-circuited."""

    kind: GuardKind
    reply: str | None = None
    actions: tuple[tuple[str, dict[str, str]], ...] = ()
    end_call: bool = False
    turn_instruction: str | None = None


_EMERGENCY_REPLY: dict[CallerLanguage, str] = {
    "en": "Please call 112 right now for an ambulance, or go to the nearest hospital emergency. "
    "I'm alerting our doctor and connecting you to our staff immediately.",
    "te": "వెంటనే 112 కి కాల్ చేయండి అండి, ఆంబులెన్స్ వస్తుంది, లేదా దగ్గర్లోని హాస్పిటల్ "
    "ఎమర్జెన్సీకి వెళ్ళండి. నేను ఇప్పుడే మా డాక్టర్‌కి చెప్పి, మిమ్మల్ని స్టాఫ్‌కి కనెక్ట్ చేస్తున్నాను.",
    "te-en": "వెంటనే 112 కి call చేయండి అండి, ambulance వస్తుంది, లేదా దగ్గర్లో ఉన్న hospital "
    "emergency కి వెళ్ళండి. నేను ఇప్పుడే మా staff కి connect చేస్తున్నాను, doctor కి కూడా చెప్తున్నాను.",
    "hi": "तुरंत 112 पर कॉल कीजिए और एम्बुलेंस बुलाइए, या पास के अस्पताल की इमरजेंसी में जाइए। "
    "मैं अभी डॉक्टर को बता रही हूँ और आपको हमारे स्टाफ़ से जोड़ रही हूँ।",
    "hi-en": "आप तुरंत 112 पर call कीजिए और ambulance बुलाइए, या पास के hospital की emergency में "
    "जाइए। मैं अभी आपको हमारे staff से connect कर रही हूँ और doctor को भी बता रही हूँ।",
}
_CRISIS_REPLY: dict[CallerLanguage, str] = {
    "en": "Please call 112 right now and stay with them, don't leave them alone. "
    "I'm connecting you to our staff and alerting the doctor immediately.",
    "te": "దయచేసి వెంటనే 112 కి కాల్ చేయండి అండి, వాళ్ళని ఒంటరిగా వదలకండి. "
    "నేను ఇప్పుడే మా స్టాఫ్‌కి కనెక్ట్ చేసి, డాక్టర్‌కి చెప్తున్నాను.",
    "te-en": "దయచేసి వెంటనే 112 కి call చేయండి అండి, వాళ్ళని ఒంటరిగా వదలకండి. "
    "నేను ఇప్పుడే మా staff కి connect చేసి, doctor కి చెప్తున్నాను.",
    "hi": "आप अभी 112 पर कॉल कीजिए और उनके साथ ही रहिए, उन्हें अकेला मत छोड़िए। "
    "मैं आपको तुरंत हमारे स्टाफ़ से जोड़ रही हूँ और डॉक्टर को बता रही हूँ।",
    "hi-en": "आप अभी 112 पर call कीजिए और उनके साथ ही रहिए, उन्हें अकेला मत छोड़िए। "
    "मैं आपको तुरंत हमारे staff से connect कर रही हूँ और doctor को बता रही हूँ।",
}
_OPT_OUT_REPLY: dict[CallerLanguage, str] = {
    "en": "Sorry for the trouble. I've removed your number, and {business} won't call you again.",
    "te": "క్షమించండి అండి, ఇబ్బంది పెట్టినందుకు. మీ నంబర్ తీసేశాను, ఇకపై {business} నుండి కాల్స్ రావు.",
    "te-en": "Sorry అండి, ఇబ్బంది పెట్టినందుకు. మీ number తీసేశాను, ఇకపై {business} నుండి calls రావు.",
    "hi": "माफ़ कीजिए, आपको परेशानी हुई। आपका नंबर हटा दिया है, अब {business} से कॉल नहीं आएगी।",
    "hi-en": "Sorry, आपको परेशानी हुई। आपका number हटा दिया है, अब {business} से call नहीं आएगी।",
}

_MEDICAL_INSTRUCTION = (
    "GUARDRAIL: the caller wants medical advice (medicine, dose, diagnosis or what a report "
    "means). Say kindly that you can't advise on that and the doctor will. Do NOT name or repeat "
    "any medicine, dose, condition, disease or test value, and never say whether something is "
    "normal, high, low or serious. The doctor's team has already been alerted (don't call "
    "alert_staff again). Offer an appointment with the right doctor from the facts (name them), "
    "or a doctor callback; if they want the callback, call schedule_callback."
)


def pre_check(text: str, lang: CallerLanguage, pack: EmployeePack) -> GuardHit | None:
    """Classify the caller's utterance before any LLM call. Safety first, then opt-out."""
    if _EMERGENCY.search(text):
        table = _CRISIS_REPLY if _MENTAL_HEALTH.search(text) else _EMERGENCY_REPLY
        reason = "mental-health crisis" if table is _CRISIS_REPLY else "medical emergency"
        return GuardHit(
            kind="emergency",
            reply=table[lang],
            actions=(
                ("alert_staff", {"reason": reason, "urgency": "emergency", "caller_said": text}),
                ("transfer_to_human", {"reason": reason}),
            ),
        )
    if _OPT_OUT.search(text):
        return GuardHit(
            kind="opt_out",
            reply=_OPT_OUT_REPLY[lang].format(business=pack.business_name),
            actions=(("opt_out", {"caller_said": text}), ("end_call", {"reason": "opt_out"})),
            end_call=True,
        )
    if pack.industry == "clinic" and _MEDICAL.search(text):
        # Compliance §5: a medical question always reaches the doctor's team.
        return GuardHit(
            kind="medical",
            actions=(
                ("alert_staff", {"reason": "caller asked for medical advice", "caller_said": text}),
            ),
            turn_instruction=_MEDICAL_INSTRUCTION,
        )
    return None


# --- post-check -----------------------------------------------------------------------------------

_MEDICINES = (
    r"paracetamol|dolo|crocin|calpol|ibuprofen|combiflam|amoxicillin|azithromycin|cetirizine|"
    r"metformin|aspirin|pantoprazole|pantop|omeprazole|digene|eno|benadryl|ascoril|antacid|"
    r"antibiotic|పారాసిటమాల్|డోలో|యాంటీబయాటిక్|पैरासिटामोल|डोलो|क्रोसिन|एंटीबायोटिक"
)
_DOSAGE = (
    r"\d+(?:\.\d+)?\s?(?:mg|ml|mcg)(?![a-z])|మి\.?గ్రా|मि\.?ग्रा|मिलीग्राम|"
    r"(?:once|twice|thrice|\d+ times) (?:a|per) day|రోజుకు (?:ఒక|రెండు|మూడు|\d+) సార్లు|"
    r"दिन में (?:एक|दो|तीन|\d+) बार|चम्मच|స్పూన్"
)
_DIAGNOSIS = (
    r"\bsounds like\b|\b(?:you|he|she|they) (?:probably |might |may |must |likely )?"
    r"(?:have|has) (?:an? )?(?:viral|infection|migraine|gastritis|dengue|typhoid|heart attack|"
    r"stroke|flu|arthritis|ulcer)"
)
_CLINIC_ALWAYS = re.compile(f"{_MEDICINES}|{_DOSAGE}|{_DIAGNOSIS}", re.IGNORECASE)
# Only on a medical-advice turn: don't even echo the condition the caller guessed.
_CONDITIONS = re.compile(
    r"arthritis|gastric|gastritis|ulcer|acidity|migraine|viral|infection|dengue|typhoid|"
    r"diabetes|thyroid problem|heart attack|"
    r"గ్యాస్ట్రిక్|అల్సర్|ఎసిడిటీ|ఆర్థరైటిస్|गैस्ट्रिक|अल्सर|एसिडिटी|गठिया|"
    r"(?:report|result|values?|tsh|sugar|రిపోర్ట్|रिपोर्ट)\S*\s+(?:\S+\s+)?"
    r"(?:is |are |looks? |seems? )?(?:normal|fine|high|low|ok)\b|"
    r"నార్మల్‌?\s?గా ఉంది|నార్మల్ ఉంది|బాగానే ఉంది|అంతా ఓకే|"
    r"(?:ज़्यादा|ज्यादा|कम|नॉर्मल|normal|high|low) (?:है|नहीं है)",
    re.IGNORECASE,
)
_CLAIMS: dict[Industry, re.Pattern[str]] = {
    "real_estate": re.compile(
        r"guarantee|(?:will|definitely|surely|sure to) (?:double|appreciate|go up|increase)|"
        r"100% (?:legal|safe|clear title)|(?:fully|completely|totally) (?:legal|safe)|"
        r"ఖచ్చితంగా (?:డబుల్|పెరుగుతుంది)|पक्का (?:डबल|बढ़ेगा)|"
        r"\b(?:i|we)(?:'ll| will| can| could)? (?:give|offer) (?:you )?(?:an? )?(?:\d+% )?discount",
        re.IGNORECASE,
    ),
    "clinic": re.compile(
        r"\b(?:i|we)(?:'ll| will| can| could)? (?:give|offer) (?:you )?(?:an? )?(?:\d+% )?discount",
        re.IGNORECASE,
    ),
}

_SAFE_LINE: dict[Violation, dict[str, str]] = {
    "amount": {
        "en": "Let me confirm the exact amount with the team and send it to you on WhatsApp.",
        "te": "ఖచ్చితమైన అమౌంట్ టీమ్‌తో కన్ఫర్మ్ చేసి వాట్సాప్‌లో పంపిస్తాను అండి.",
        "hi": "सही रकम मैं टीम से कन्फ़र्म करके आपको व्हाट्सऐप पर भेज दूँगी।",
    },
    "medical": {
        "en": "I'm sorry, I can't advise on that, but our doctor can. "
        "Shall I book an appointment, or ask the doctor to call you back?",
        "te": "క్షమించండి అండి, దాని గురించి నేను చెప్పలేను, డాక్టర్ గారే చెప్తారు. "
        "అపాయింట్‌మెంట్ బుక్ చేయమంటారా, లేదా డాక్టర్ గారిని కాల్ చేయమంటారా?",
        "hi": "माफ़ कीजिए, इस बारे में मैं नहीं बता सकती, यह डॉक्टर ही बताएँगे। "
        "क्या मैं अपॉइंटमेंट बुक कर दूँ, या डॉक्टर से आपको कॉल करवा दूँ?",
    },
    "claim": {
        "en": "I can't promise that, but our team can share the exact details with you.",
        "te": "దాని గురించి నేను ప్రామిస్ చేయలేను అండి, మా టీమ్ పూర్తి వివరాలు చెప్తారు.",
        "hi": "इसका वादा मैं नहीं कर सकती, पर हमारी टीम आपको पूरी जानकारी देगी।",
    },
}


def safe_line(violation: Violation, lang: CallerLanguage) -> str:
    return _SAFE_LINE[violation][base_language(lang)]


@dataclass
class PostCheck:
    """Checks the LLM's reply against the pack, sentence by sentence (or clause by clause)."""

    pack: EmployeePack
    caller_texts: list[str] = field(default_factory=list)

    def violation(self, sentence: str, *, medical_turn: bool = False) -> Violation | None:
        allowed = allowed_amounts(self.pack, self.caller_texts)
        if any(a not in allowed for a in money_amounts(sentence)):
            return "amount"
        if self.pack.industry == "clinic":
            if _CLINIC_ALWAYS.search(sentence):
                return "medical"
            if medical_turn and _CONDITIONS.search(sentence):
                return "medical"
        claims = _CLAIMS.get(self.pack.industry)
        if claims is not None and claims.search(sentence):
            return "claim"
        return None

    def apply(
        self, reply: str, lang: CallerLanguage, *, medical_turn: bool = False
    ) -> tuple[str, list[Violation]]:
        """Return the reply with offending sentences swapped for one safe line per kind."""
        kept: list[str] = []
        found: list[Violation] = []
        for sentence in split_sentences(reply):
            v = self.violation(sentence, medical_turn=medical_turn)
            if v is None:
                kept.append(sentence)
            elif v not in found:
                found.append(v)
                kept.append(safe_line(v, lang))
        if found and "medical" in found:
            # A medical slip makes the rest of the reply suspect: answer with the refusal only.
            return safe_line("medical", lang), found
        return " ".join(kept), found


__all__ = [
    "GuardHit",
    "PostCheck",
    "allowed_amounts",
    "money_amounts",
    "pre_check",
    "safe_line",
    "split_sentences",
]
