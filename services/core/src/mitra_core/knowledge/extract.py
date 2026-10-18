"""Deterministic fact extraction (Step 2, no LLM).

REPLACEABLE: Step 3 swaps this for LLM extraction (TRD §7). Callers depend only on
``extract_from_html`` / ``extract_from_text`` returning ``ExtractedFact``s, so the replacement
can keep those signatures.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser

from mitra_core.models.enums import FactCategory, FactStatus

MAX_FACTS_PER_SOURCE = 50
_MAX_KEY = 120
_MAX_VALUE = 500


@dataclass(frozen=True, slots=True)
class ExtractedFact:
    category: FactCategory
    key: str
    value: str
    status: FactStatus = FactStatus.SUGGESTED


@dataclass(frozen=True, slots=True)
class Extraction:
    title: str | None
    facts: list[ExtractedFact]


# --- category guessing ------------------------------------------------------------------------

# Checked in order; the first category whose pattern matches wins (key first, then key+value).
_CATEGORY_PATTERNS: tuple[tuple[FactCategory, re.Pattern[str]], ...] = tuple(
    (category, re.compile(pattern, re.IGNORECASE))
    for category, pattern in (
        (FactCategory.CONTACT, r"\b(phone|mobile|whats ?app|e-?mail|contact|call us|tel)\b"),
        (
            FactCategory.PRICES,
            r"₹|\b(fees?|prices?|pricing|costs?|charges?|rates?|rs|inr|rupees?|emi|budget|"
            r"packages?)\b",
        ),
        (
            FactCategory.TIMINGS,
            r"\b(timings?|times?|hours?|open(ing)?|clos(e|ed|ing)|schedule|slots?|days?|"
            r"weekdays?|visit(ing)?)\b",
        ),
        (
            FactCategory.LOCATION,
            r"\b(address|location|located|landmark|near(by)?|parking|directions?|map|"
            r"branch(es)?|area|pincode)\b",
        ),
        (FactCategory.POLICY, r"\b(polic(y|ies)|cancel\w*|refunds?|insurance|payments?|rules?)\b"),
        (
            FactCategory.SERVICES,
            r"\b(services?|treatments?|doctors?|dr|speciali[sz]\w*|projects?|courses?|"
            r"facilit\w*|amenit\w*|offer\w*)\b",
        ),
    )
)


def guess_category(key: str, value: str = "") -> FactCategory:
    for text in (key, f"{key} {value}"):
        for category, pattern in _CATEGORY_PATTERNS:
            if pattern.search(text):
                return category
    return FactCategory.FAQ


# --- pattern extractors -----------------------------------------------------------------------

_MOBILE_RE = re.compile(r"(?<!\d)(?:\+?91[\s-]?|0)?([6-9]\d{4})[\s-]?(\d{5})(?!\d)")
_LANDLINE_RE = re.compile(r"(?<!\d)(0\d{2,4})[\s-](\d{6,8})(?!\d)")
_TOLL_FREE_RE = re.compile(r"(?<!\d)(1800)[\s-]?(\d{3})[\s-]?(\d{4})(?!\d)")
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PINCODE_RE = re.compile(r"(?<!\d)[1-9]\d{2}\s?\d{3}(?!\d)")
_ADDRESS_WORDS = re.compile(
    r"\b(address|road|rd\.|street|st\.|nagar|colony|marg|lane|layout|sector|"
    r"near|opp\.?|opposite|beside|floor|plot|hyderabad|bengaluru|bangalore|vijayawada|"
    r"visakhapatnam|chennai|mumbai|pune|delhi|telangana|andhra pradesh)\b",
    re.IGNORECASE,
)
_DASHES = "-–—"  # noqa: RUF001  (hyphen, en dash, em dash)
_TIME = r"\d{1,2}(?:[:.]\d{2})?\s*(?:am|pm|a\.m\.|p\.m\.)?"
_TIME_RANGE_RE = re.compile(rf"({_TIME})\s*(?:[{_DASHES}]|to)\s*({_TIME})", re.IGNORECASE)
_HAS_CLOCK = re.compile(r"(am|pm|a\.m\.|p\.m\.|\d[:.]\d{2})", re.IGNORECASE)
_DAYS_RE = re.compile(
    r"\b(mon|tue|wed|thu|fri|sat|sun)[a-z]*\b|\b(daily|weekdays|all days|24\s?x\s?7|24/7)\b",
    re.IGNORECASE,
)
_PRICE_RE = re.compile(
    r"(₹|\brs\.?|\binr)\s?\d[\d,]*(?:\.\d+)?(?:\s?(?:lakhs?|l|cr|crores?)\b)?", re.IGNORECASE
)


def _clip(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def phones_in(text: str) -> list[str]:
    found: list[str] = []
    for m in _TOLL_FREE_RE.finditer(text):
        found.append(f"{m.group(1)}-{m.group(2)}-{m.group(3)}")
    stripped = _TOLL_FREE_RE.sub(" ", text)
    for m in _MOBILE_RE.finditer(stripped):
        found.append(f"+91{m.group(1)}{m.group(2)}")
    for m in _LANDLINE_RE.finditer(_MOBILE_RE.sub(" ", stripped)):
        found.append(f"{m.group(1)}-{m.group(2)}")
    return found


def _hours_in(line: str) -> bool:
    m = _TIME_RANGE_RE.search(line)
    if m and _HAS_CLOCK.search(m.group(0)):
        return True
    return bool(re.search(r"\b(open|closed|timings?|hours)\b", line, re.IGNORECASE)) and bool(
        _DAYS_RE.search(line) or _HAS_CLOCK.search(line)
    )


_KEY_TRIM = f" :={_DASHES}|"


def _price_fact(line: str) -> ExtractedFact | None:
    m = _PRICE_RE.search(line)
    if not m:
        return None
    before = line[: m.start()].strip(_KEY_TRIM)
    before = re.sub(r"\b(is|are|of|at|for|starts?|starting|from)\s*$", "", before, flags=re.I)
    key = _clip(before.strip(_KEY_TRIM), 60) or "Price"
    value = _clip(line if key == "Price" else line[m.start() :], _MAX_VALUE)
    return ExtractedFact(FactCategory.PRICES, key[:1].upper() + key[1:], value)


def extract_patterns(lines: list[str]) -> list[ExtractedFact]:
    """Phones, emails, address-like lines, opening hours and prices from free text."""
    facts: list[ExtractedFact] = []
    for line in lines:
        if len(line) > 300:
            continue
        for phone in phones_in(line):
            facts.append(ExtractedFact(FactCategory.CONTACT, "Phone", phone))
        for email in _EMAIL_RE.findall(line):
            facts.append(ExtractedFact(FactCategory.CONTACT, "Email", email.lower()))
        if _hours_in(line):
            facts.append(ExtractedFact(FactCategory.TIMINGS, "Opening hours", _clip(line, 200)))
        elif (
            (_PINCODE_RE.search(line) or len(_ADDRESS_WORDS.findall(line)) >= 2)
            and not _EMAIL_RE.search(line)
            and len(line) >= 15
        ):
            facts.append(ExtractedFact(FactCategory.LOCATION, "Address", _clip(line, 200)))
        price = _price_fact(line)
        if price is not None:
            facts.append(price)
    return facts


def _dedupe(facts: list[ExtractedFact]) -> list[ExtractedFact]:
    seen: set[tuple[str, str]] = set()
    out: list[ExtractedFact] = []
    for fact in facts:
        ident = (fact.key.lower(), fact.value.lower())
        if ident in seen:
            continue
        seen.add(ident)
        out.append(fact)
    return out[:MAX_FACTS_PER_SOURCE]


# --- HTML -------------------------------------------------------------------------------------

_BLOCK_TAGS = frozenset(
    {
        *("address", "article", "aside", "blockquote", "br", "dd", "div", "dl", "dt"),
        *("footer", "form", "h1", "h2", "h3", "h4", "h5", "h6", "header", "hr", "li"),
        *("main", "nav", "ol", "p", "pre", "section", "table", "td", "th", "tr", "ul"),
    }
)
_SKIP_TAGS = frozenset({"script", "style", "noscript", "template", "svg", "iframe", "head"})


class _PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title: str | None = None
        self.description: str | None = None
        self.links: list[str] = []
        self._lines: list[str] = [""]
        self._skip = 0
        self._in_title = False
        self._title_parts: list[str] = []

    @property
    def lines(self) -> list[str]:
        return [ln for ln in (" ".join(x.split()) for x in self._lines) if ln]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "title":
            self._in_title = True
        elif tag == "meta":
            name = (a.get("name") or a.get("property") or "").lower()
            if name in {"description", "og:description"} and a.get("content"):
                self.description = self.description or a["content"]
        elif tag == "a" and a.get("href", "").lower().startswith(("tel:", "mailto:")):
            self.links.append(a["href"].split(":", 1)[1].split("?", 1)[0])
        if tag in _SKIP_TAGS and tag != "head":
            self._skip += 1
        if tag in _BLOCK_TAGS:
            self._lines.append("")

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
            self.title = self.title or " ".join("".join(self._title_parts).split()) or None
        if tag in _SKIP_TAGS and tag != "head" and self._skip:
            self._skip -= 1
        if tag in _BLOCK_TAGS:
            self._lines.append("")

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._title_parts.append(data)
        elif not self._skip:
            self._lines[-1] += data


def extract_from_html(html: str) -> Extraction:
    parser = _PageParser()
    parser.feed(html)
    parser.close()
    facts: list[ExtractedFact] = []
    title = _clip(parser.title, 200) if parser.title else None
    if title:
        facts.append(ExtractedFact(FactCategory.FAQ, "Website title", title))
    if parser.description:
        facts.append(
            ExtractedFact(FactCategory.SERVICES, "About", _clip(parser.description, _MAX_VALUE))
        )
    link_text = [link for link in parser.links if link]
    facts.extend(extract_patterns(link_text))
    facts.extend(extract_patterns(parser.lines))
    return Extraction(title=title, facts=_dedupe(facts))


# --- pasted text ------------------------------------------------------------------------------

_KV_RE = re.compile(r"^\s*[-*•]?\s*([^:]{1,120}?)\s*:\s*(.+?)\s*$")


def extract_from_text(text: str) -> Extraction:
    """Each ``Key: value`` line is an owner-authored fact (confirmed); other lines are scanned
    with the pattern extractors (suggested)."""
    facts: list[ExtractedFact] = []
    loose: list[str] = []
    for raw in text.splitlines():
        m = _KV_RE.match(raw)
        if m and not m.group(1).lower().startswith(("http", "https")):
            key, value = _clip(m.group(1), _MAX_KEY), _clip(m.group(2), _MAX_VALUE)
            facts.append(
                ExtractedFact(guess_category(key, value), key, value, FactStatus.CONFIRMED)
            )
        elif raw.strip():
            loose.append(" ".join(raw.split()))
    facts.extend(extract_patterns(loose))
    first = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
    title = "Pasted text" if _KV_RE.match(first) else _clip(first, 80)
    return Extraction(title=title, facts=_dedupe(facts))
