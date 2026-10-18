"""Rupee amounts in the Indian system."""

from __future__ import annotations

import pytest

from mitra_human import Lang, speakable

CASES: list[tuple[str, Lang, str]] = [
    # English
    ("₹500", "en", "five hundred rupees"),
    ("Rs. 500", "en", "five hundred rupees"),
    ("Rs 500", "en", "five hundred rupees"),
    ("INR 500", "en", "five hundred rupees"),
    ("500 Rs", "en", "five hundred rupees"),
    ("₹1,20,000", "en", "one lakh twenty thousand rupees"),
    ("₹1.2 lakh", "en", "one lakh twenty thousand rupees"),
    ("₹2.5 crore", "en", "two and a half crore rupees"),
    ("₹4,200/-", "en", "four thousand two hundred rupees"),
    ("4,200/-", "en", "four thousand two hundred rupees"),
    ("₹1", "en", "one rupee"),
    ("₹10.50", "en", "ten rupees and fifty paise"),
    ("₹0.50", "en", "fifty paise"),
    ("₹50k", "en", "fifty thousand rupees"),
    ("₹2 lakh", "en", "two lakh rupees"),
    ("₹1.25 crore", "en", "one crore twenty-five lakh rupees"),
    ("₹1.5 lakhs", "en", "one and a half lakh rupees"),
    ("₹5L", "en", "five lakh rupees"),
    ("₹3 Cr", "en", "three crore rupees"),
    ("₹500 rupees", "en", "five hundred rupees"),
    ("₹500–800", "en", "five hundred to eight hundred rupees"),
    ("₹500 - ₹800", "en", "five hundred to eight hundred rupees"),
    ("Rs 1-2 lakh", "en", "one lakh to two lakh rupees"),
    ("The fee is ₹1,20,000/- only.", "en", "The fee is one lakh twenty thousand rupees only."),
    # Hindi
    ("₹500", "hi", "पाँच सौ रुपये"),
    ("₹1,20,000", "hi", "एक लाख बीस हज़ार रुपये"),
    ("₹1.2 lakh", "hi", "एक लाख बीस हज़ार रुपये"),
    ("₹2.5 crore", "hi", "ढाई करोड़ रुपये"),
    ("₹1.5 लाख", "hi", "डेढ़ लाख रुपये"),
    ("₹3.5 lakh", "hi", "साढ़े तीन लाख रुपये"),
    ("₹1", "hi", "एक रुपया"),
    ("₹10.50", "hi", "दस रुपये पचास पैसे"),
    ("₹4,200/-", "hi", "चार हज़ार दो सौ रुपये"),
    ("₹500–800", "hi", "पाँच सौ से आठ सौ रुपये"),
    ("फ़ीस ₹२,५००", "hi", "फ़ीस दो हज़ार पाँच सौ रुपये"),
    ("₹2.5 करोड़", "hi", "ढाई करोड़ रुपये"),
    # Telugu
    ("₹500", "te", "ఐదు వందల రూపాయలు"),
    ("₹1,20,000", "te", "ఒక లక్ష ఇరవై వేల రూపాయలు"),
    ("₹1.2 lakh", "te", "ఒక లక్ష ఇరవై వేల రూపాయలు"),
    ("₹2.5 crore", "te", "రెండున్నర కోట్ల రూపాయలు"),
    ("₹1.5 lakh", "te", "ఒకటిన్నర లక్షల రూపాయలు"),
    ("₹1", "te", "ఒక రూపాయి"),
    ("₹21", "te", "ఇరవై ఒక్క రూపాయలు"),
    ("₹100", "te", "వంద రూపాయలు"),
    ("₹1000", "te", "వెయ్యి రూపాయలు"),
    ("₹2 lakh", "te", "రెండు లక్షల రూపాయలు"),
    ("₹1 crore", "te", "ఒక కోటి రూపాయలు"),
    ("₹10.50", "te", "పది రూపాయల యాభై పైసలు"),
    ("₹500 కి", "te", "ఐదు వందల రూపాయలకి"),
    ("₹500–800", "te", "ఐదు వందల నుండి ఎనిమిది వందల రూపాయల వరకు"),
    ("₹౫౦౦", "te", "ఐదు వందల రూపాయలు"),
]


@pytest.mark.parametrize(("text", "lang", "expected"), CASES)
def test_money(text: str, lang: Lang, expected: str) -> None:
    assert speakable(text, lang) == expected


@pytest.mark.parametrize(
    ("text", "lang", "expected"),
    [
        ("1.2 lakh people", "en", "one lakh twenty thousand people"),
        ("2.5 crore", "en", "two and a half crore"),
        ("2.5 करोड़ का फ्लैट", "hi", "ढाई करोड़ का फ्लैट"),
        ("2.5 లక్షలు", "te", "రెండున్నర లక్షలు"),
        ("2 lakh", "te", "రెండు లక్షలు"),
        ("1.2 లక్షల రూపాయలు", "te", "ఒక లక్ష ఇరవై వేల రూపాయలు"),
    ],
)
def test_scaled_numbers_without_currency(text: str, lang: Lang, expected: str) -> None:
    assert speakable(text, lang) == expected
