"""honorific, spell_phone, spell_email, spell_digits."""

from __future__ import annotations

import pytest

from mitra_human import (
    Formality,
    HonorificGender,
    Lang,
    honorific,
    spell_digits,
    spell_email,
    spell_phone,
)

HONORIFICS: list[tuple[str, Lang, Formality, HonorificGender, str]] = [
    ("Ravi", "en", "friendly", "male", "Ravi"),
    ("Ravi", "en", "respectful", "male", "Ravi sir"),
    ("Priya", "en", "respectful", "female", "Priya ma'am"),
    ("Ravi", "en", "formal", "male", "Mr. Ravi"),
    ("Priya", "en", "formal", "female", "Ms. Priya"),
    ("Ravi", "en", "formal", "unknown", "Ravi"),
    ("Ravi", "hi", "friendly", "unknown", "Ravi"),
    ("Ravi", "hi", "respectful", "unknown", "Ravi ji"),
    ("Ravi", "hi", "formal", "male", "Ravi sir"),
    ("Priya", "hi", "formal", "female", "Priya madam"),
    ("Ravi", "hi", "formal", "unknown", "Ravi ji"),
    ("रवि", "hi", "respectful", "unknown", "रवि जी"),
    ("रवि", "hi", "formal", "male", "रवि सर"),
    ("Ravi", "te", "friendly", "male", "Ravi"),
    ("Ravi", "te", "respectful", "male", "Ravi garu"),
    ("Ravi", "te", "formal", "unknown", "Ravi garu"),
    ("రవి", "te", "respectful", "unknown", "రవి గారు"),
    ("  Ravi   Kumar ", "te", "respectful", "unknown", "Ravi Kumar garu"),
]


@pytest.mark.parametrize(("name", "lang", "formality", "gender", "expected"), HONORIFICS)
def test_honorific(
    name: str, lang: Lang, formality: Formality, gender: HonorificGender, expected: str
) -> None:
    assert honorific(name, lang, formality, gender=gender) == expected


def test_honorific_default_is_respectful() -> None:
    assert honorific("Ravi", "te") == "Ravi garu"


def test_honorific_rejects_bad_input() -> None:
    with pytest.raises(ValueError, match="empty"):
        honorific("  ", "en")
    with pytest.raises(ValueError, match="formality"):
        honorific("Ravi", "en", "casual")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("number", "lang", "expected"),
    [
        ("+91 98765 43210", "en", "nine eight seven six five, four three two one zero"),
        ("(040) 2345 6789", "en", "zero four zero, two three four five, six seven eight nine"),
        ("9876543210", "hi", "नौ आठ सात छह पाँच, चार तीन दो एक ज़ीरो"),
        ("12345", "te", "ఒకటి రెండు మూడు, నాలుగు ఐదు"),
    ],
)
def test_spell_phone(number: str, lang: str, expected: str) -> None:
    assert spell_phone(number, lang) == expected


def test_spell_phone_rejects_text() -> None:
    with pytest.raises(ValueError, match="not a phone number"):
        spell_phone("call me", "en")


@pytest.mark.parametrize(
    ("email", "lang", "expected"),
    [
        ("ravi.k@gmail.com", "en", "ravi dot k at gmail dot com"),
        ("ravi_99@mitra.in", "en", "ravi underscore nine nine at mitra dot in"),
        ("ravi.k@gmail.com", "hi", "ravi डॉट k एट gmail डॉट com"),
        ("ravi.k@gmail.com", "te", "ravi డాట్ k ఎట్ gmail డాట్ com"),
    ],
)
def test_spell_email(email: str, lang: str, expected: str) -> None:
    assert spell_email(email, lang) == expected


def test_spell_email_rejects_non_email() -> None:
    with pytest.raises(ValueError, match="not an email"):
        spell_email("ravi at gmail", "en")


@pytest.mark.parametrize(
    ("digits", "lang", "expected"),
    [
        ("4821", "en", "four eight two one"),
        ("0042", "hi", "शून्य शून्य चार दो"),
        ("४८", "hi", "चार आठ"),
        ("907", "te", "తొమ్మిది సున్నా ఏడు"),
    ],
)
def test_spell_digits(digits: str, lang: str, expected: str) -> None:
    assert spell_digits(digits, lang) == expected


def test_spell_digits_rejects_non_digits() -> None:
    with pytest.raises(ValueError, match="only digits"):
        spell_digits("12a", "en")
