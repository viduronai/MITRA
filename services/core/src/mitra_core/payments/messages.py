"""Customer WhatsApp texts for payment links, in the customer's language (en / hi / te).

Collection wording stays polite (ACT-11, 08-COMPLIANCE-SECURITY): no pressure, no threats, an
"already paid? ignore this" line on every reminder.
"""

from __future__ import annotations

from datetime import date
from urllib.parse import quote

Lang = str

TEXTS: dict[str, dict[str, str]] = {
    "link": {
        "en": "Hi {name}, {business} here. Please pay {amount} for {purpose}{due}.\n{pay}",
        "hi": "नमस्ते {name}, {business} से। कृपया {purpose} के लिए {amount} का भुगतान करें{due}।\n{pay}",
        "te": "నమస్కారం {name}, {business} నుండి. దయచేసి {purpose} కోసం {amount} చెల్లించండి{due}.\n{pay}",
    },
    "due": {"en": " by {date}", "hi": " ({date} तक)", "te": " ({date} లోపు)"},
    "pay_link": {
        "en": "Pay here: {link}",
        "hi": "यहाँ भुगतान करें: {link}",
        "te": "ఇక్కడ చెల్లించండి: {link}",
    },
    "pay_upi": {
        "en": "Pay by UPI to {vpa}: {link}",
        "hi": "UPI से {vpa} पर भुगतान करें: {link}",
        "te": "UPI ద్వారా {vpa}కి చెల్లించండి: {link}",
    },
    "thanks": {
        "en": "Thank you {name}! We received {amount} for {purpose}. - {business}",
        "hi": "धन्यवाद {name}! {purpose} के लिए {amount} मिल गए। - {business}",
        "te": "ధన్యవాదాలు {name}! {purpose} కోసం {amount} అందింది. - {business}",
    },
    "expiry": {
        "en": "Hi {name}, a reminder from {business}: please pay {amount} for {purpose}{due}, "
        "after that this link stops working.\n{pay}\nAlready paid? Please ignore this message.",
        "hi": "नमस्ते {name}, {business} की ओर से याद: कृपया {purpose} के {amount}{due} चुका दें, "
        "उसके बाद यह लिंक काम नहीं करेगा।\n{pay}\n"
        "अगर भुगतान कर दिया है तो इस संदेश को अनदेखा करें।",
        "te": "నమస్కారం {name}, {business} నుండి గుర్తు: {purpose} కోసం {amount}{due} చెల్లించండి, "
        "తర్వాత ఈ లింక్ పనిచేయదు.\n{pay}\n"
        "ఇప్పటికే చెల్లించి ఉంటే, ఈ సందేశాన్ని పట్టించుకోకండి.",
    },
    "reminder": {
        "en": "Hi {name}, a gentle reminder from {business}: {amount} for {purpose} is pending.\n"
        "{pay}\nAlready paid? Please ignore this message.",
        "hi": "नमस्ते {name}, {business} की ओर से एक याद: {purpose} के {amount} बाकी हैं।\n"
        "{pay}\nअगर भुगतान कर दिया है तो कृपया इस संदेश को अनदेखा करें।",
        "te": "నమస్కారం {name}, {business} నుండి చిన్న గుర్తు: {purpose} కోసం {amount} ఇంకా పెండింగ్‌లో ఉంది.\n"
        "{pay}\nఇప్పటికే చెల్లించి ఉంటే, దయచేసి ఈ సందేశాన్ని పట్టించుకోకండి.",
    },
}
NAME_FALLBACK = {"en": "there", "hi": "जी", "te": "గారు"}


def lang_of(value: object) -> Lang:
    text = getattr(value, "value", value)
    return str(text) if text in {"en", "hi", "te"} else "en"


def rupees(paise: int) -> str:
    """Indian grouping: 150000000 -> '₹15,00,000'; paise shown only when present."""
    whole, frac = divmod(abs(paise), 100)
    digits = str(whole)
    head, tail = digits[:-3], digits[-3:]
    groups: list[str] = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    body = ",".join([*groups, tail]) if groups else tail
    return f"₹{body}" + (f".{frac:02d}" if frac else "")


def upi_uri(*, vpa: str, payee: str, amount_paise: int, note: str, ref: str) -> str:
    """UPI deep link (NPCI linking spec): opens any UPI app with the amount filled in."""
    whole, frac = divmod(amount_paise, 100)
    params = {
        "pa": vpa,
        "pn": payee[:50],
        "am": f"{whole}.{frac:02d}",
        "cu": "INR",
        "tn": note[:50],
        "tr": ref[:35],
    }
    return "upi://pay?" + "&".join(f"{k}={quote(v, safe='@.')}" for k, v in params.items())


def _t(key: str, lang: Lang) -> str:
    return TEXTS[key].get(lang) or TEXTS[key]["en"]


def pay_line(lang: Lang, *, link: str, vpa: str | None) -> str:
    if vpa:
        return _t("pay_upi", lang).format(vpa=vpa, link=link)
    return _t("pay_link", lang).format(link=link)


def render(
    key: str,
    lang: Lang,
    *,
    name: str | None,
    business: str,
    amount_paise: int,
    purpose: str,
    link: str = "",
    vpa: str | None = None,
    due: date | None = None,
) -> str:
    due_text = _t("due", lang).format(date=f"{due:%d %b %Y}") if due else ""
    return _t(key, lang).format(
        name=(name or "").strip()[:60] or NAME_FALLBACK.get(lang, "there"),
        business=business,
        amount=rupees(amount_paise),
        purpose=purpose,
        due=due_text,
        pay=pay_line(lang, link=link, vpa=vpa) if link else "",
    )
