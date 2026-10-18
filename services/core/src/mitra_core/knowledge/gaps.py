"""Industry-aware "what's still missing" questions for the Teach step."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from mitra_core.models.enums import FactCategory, Industry


@dataclass(frozen=True, slots=True)
class Gap:
    category: FactCategory
    key: str
    question: str
    # Filled when a fact (of ``match_category``, if set) mentions any keyword in key or value;
    # with no keywords, any fact of ``match_category`` fills it.
    keywords: tuple[str, ...] = ()
    match_category: FactCategory | None = None

    def filled_by(self, category: FactCategory, key: str, value: str) -> bool:
        if self.match_category is not None and category != self.match_category:
            return False
        text = f"{key} {value}".lower()
        return not self.keywords or any(k in text for k in self.keywords)


_LOCATION_WORDS = (
    "address",
    "location",
    "located",
    "landmark",
    "near",
    "road",
    "street",
    "nagar",
    "colony",
    "area",
    "pincode",
    "map",
)

_LOCATION = Gap(
    FactCategory.LOCATION,
    "Address",
    "Where are you located? Share the full address.",
    keywords=_LOCATION_WORDS,
)

GAPS: dict[Industry | None, tuple[Gap, ...]] = {
    Industry.CLINIC: (
        Gap(
            FactCategory.PRICES,
            "Consultation fee",
            "What is your consultation fee?",
            keywords=("consult", "fee"),
            match_category=FactCategory.PRICES,
        ),
        Gap(
            FactCategory.TIMINGS,
            "Timings",
            "What are your clinic timings?",
            match_category=FactCategory.TIMINGS,
        ),
        Gap(
            FactCategory.SERVICES,
            "Doctors",
            "Which doctors consult here, and their specialities?",
            keywords=("doctor", "dr.", "dr "),
        ),
        _LOCATION,
        Gap(
            FactCategory.LOCATION,
            "Parking",
            "Is parking available for patients?",
            keywords=("parking",),
        ),
    ),
    Industry.REAL_ESTATE: (
        Gap(
            FactCategory.SERVICES,
            "Projects",
            "Which projects are you selling right now?",
            keywords=("project", "villa", "apartment", "flat", "plot", "bhk"),
        ),
        Gap(
            FactCategory.PRICES,
            "Price range",
            "What is the price range of your projects?",
            match_category=FactCategory.PRICES,
        ),
        _LOCATION,
        Gap(
            FactCategory.TIMINGS,
            "Site-visit timings",
            "When can customers come for a site visit?",
            keywords=("visit",),
        ),
    ),
    None: (
        Gap(
            FactCategory.SERVICES,
            "Services",
            "What services or products do you offer?",
            match_category=FactCategory.SERVICES,
        ),
        Gap(
            FactCategory.PRICES,
            "Prices",
            "What are your main prices or fees?",
            match_category=FactCategory.PRICES,
        ),
        Gap(
            FactCategory.TIMINGS,
            "Timings",
            "What are your working hours?",
            match_category=FactCategory.TIMINGS,
        ),
        _LOCATION,
        Gap(
            FactCategory.CONTACT,
            "Phone",
            "Which phone number should customers call or WhatsApp?",
            match_category=FactCategory.CONTACT,
        ),
    ),
}


def missing_gaps(industry: Industry, facts: Iterable[tuple[FactCategory, str, str]]) -> list[Gap]:
    known = list(facts)
    gaps = GAPS.get(industry, GAPS[None])
    return [g for g in gaps if not any(g.filled_by(c, k, v) for c, k, v in known)]
