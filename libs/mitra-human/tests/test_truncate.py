"""truncate_to_heard: examples plus property tests."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from mitra_human import truncate_to_heard
from mitra_human.truncate import ELLIPSIS


@pytest.mark.parametrize(
    ("text", "n", "expected"),
    [
        ("Your slot is at six. See you then.", 0, ""),
        ("Your slot is at six. See you then.", 2, "Your slot…"),
        ("Your slot is at six. See you then.", 5, "Your slot is at six."),
        ("Your slot is at six. See you then.", 7, "Your slot is at six. See you…"),
        ("Your slot is at six. See you then.", 8, "Your slot is at six. See you then."),
        ("Your slot is at six. See you then.", 99, "Your slot is at six. See you then."),
        ("Okay, let me check that", 1, "Okay…"),
        ("Wait — one second", 2, "Wait —…"),
        ("आपका स्लॉट शाम छह बजे है। धन्यवाद", 5, "आपका स्लॉट शाम छह बजे…"),
        ("आपका स्लॉट शाम छह बजे है। धन्यवाद", 6, "आपका स्लॉट शाम छह बजे है।"),
        ("మీ స్లాట్ సాయంత్రం ఆరు గంటలకి ఉంది", 3, "మీ స్లాట్ సాయంత్రం…"),
        ("  leading   and\ttabs\nnewline  ", 3, "leading   and\ttabs…"),
        ("Really? Yes", 1, "Really?"),
        ("", 0, ""),
        ("", 3, ""),
    ],
)
def test_examples(text: str, n: int, expected: str) -> None:
    assert truncate_to_heard(text, n) == expected


def test_negative_rejected() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        truncate_to_heard("a b", -1)


_WORDS = st.text(
    alphabet=st.sampled_from(list("abcXYZ019.,!?-—…।") + list("नमस्तेआप") + list("మీరుసరే")),
    min_size=1,
    max_size=8,
)
_SPACES = st.sampled_from([" ", "  ", "\t", "\n", "  "])


@st.composite
def sentences(draw: st.DrawFn) -> str:
    words = draw(st.lists(_WORDS, max_size=25))
    out = draw(st.sampled_from(["", " ", "\n"]))
    for word in words:
        out += word + draw(_SPACES)
    return out


@given(sentences(), st.integers(min_value=0, max_value=40))
def test_property_prefix_and_exact_word_count(text: str, n: int) -> None:
    result = truncate_to_heard(text, n)
    total = len(text.split())
    if n >= total:
        assert result == text
        return
    if n == 0:
        assert result == ""
        return
    body = result.removesuffix(ELLIPSIS) if not text.split()[n - 1].endswith(ELLIPSIS) else result
    assert text.lstrip().startswith(body)
    assert len(body.split()) == n
    assert body.split()[:-1] == text.split()[: n - 1]


@given(sentences(), st.integers(min_value=1, max_value=40))
def test_property_ellipsis_only_mid_sentence(text: str, n: int) -> None:
    words = text.split()
    if n >= len(words):
        return
    result = truncate_to_heard(text, n)
    if words[n - 1].endswith((".", "!", "?", "।", "…")):
        assert result.split() == words[:n]
    else:
        assert result.endswith(ELLIPSIS)


@given(sentences())
def test_property_monotonic(text: str) -> None:
    lengths = [len(truncate_to_heard(text, n).removesuffix(ELLIPSIS)) for n in range(30)]
    assert lengths == sorted(lengths)
