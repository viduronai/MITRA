from __future__ import annotations

import pytest

from mitra_evals.text import mentions, money_amounts, normalise, script_shares, sentence_count


def test_normalise() -> None:
    assert normalise("  ₹1,50,000  ONLY ") == "₹150000 only"
    assert normalise("౫౦౦ రూపాయలు") == "500 రూపాయలు"
    assert normalise("५००") == "500"
    assert normalise("బేస్‌మెంట్") == "బేస్మెంట్"


@pytest.mark.parametrize(
    ("text", "form", "expected"),
    [
        ("The fee is ₹500.", "500", True),
        ("The fee is ₹1500.", "500", False),
        ("Cyber Towers దగ్గర", "cyber towers", True),
        ("బేస్‌మెంట్‌లో పార్కింగ్", "బేస్‌మెంట్", True),
        ("no fee", "", False),
    ],
)
def test_mentions(text: str, form: str, expected: bool) -> None:
    assert mentions(text, form) is expected


@pytest.mark.parametrize(
    ("text", "amounts"),
    [
        ("The fee is ₹500.", [500]),
        ("Rs. 200 for follow-up", [200]),
        ("2 BHK 58 లక్షల నుండి", [5_800_000]),
        ("58 लाख से शुरू", [5_800_000]),
        ("₹1.5 crore villa", [15_000_000]),
        ("5,000 రూపాయలు per sq ft", [5000]),
        ("500 रुपये है", [500]),
        ("budget 60 lakhs", [6_000_000]),
        ("Please call 112 now", []),
        ("1,150 sq ft, 2 BHK, 24x7 security, 100% backup", []),
        ("our hours and doctors", []),
    ],
)
def test_money_amounts(text: str, amounts: list[int]) -> None:
    assert money_amounts(text) == amounts


def test_script_shares() -> None:
    assert script_shares("ఫీజు 500 రూపాయలు").telugu == 1.0
    assert script_shares("फीस 500 रुपये").devanagari == 1.0
    mixed = script_shares("Doctor fees ఎంత")
    assert 0 < mixed.telugu < 1
    assert mixed.latin > 0
    assert script_shares("500 !").letters == 0


@pytest.mark.parametrize(
    ("text", "count"),
    [
        ("One. Two? Three!", 3),
        ("Dr. Kavitha Reddy sees patients at 10 a.m. on Sunday.", 1),
        ("Plot 42, Road No. 5, Madhapur.", 1),
        ("डॉ. समीर खान 600 रुपये लेते हैं। आप आएँगे?", 2),
        ("ఫీజు 500 రూపాయలు అండి. బుక్ చేయమంటారా?", 2),
        ("₹1.5 lakh", 1),
        ("", 0),
    ],
)
def test_sentence_count(text: str, count: int) -> None:
    assert sentence_count(text) == count
