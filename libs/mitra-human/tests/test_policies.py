"""Seeded timing tests for BackchannelPolicy and FillerPolicy."""

from __future__ import annotations

from itertools import pairwise

import pytest

from mitra_human import BackchannelPolicy, FillerPolicy, Lang
from mitra_human.backchannel import TOKENS, looks_mid_explanation
from mitra_human.filler import fillers

EXPLAINING: dict[Lang, str] = {
    "en": "so I booked the slot last week and then my brother called me,",
    "hi": "मैंने पिछले हफ़्ते स्लॉट बुक किया था और फिर मेरे भाई का फ़ोन आया,",
    "te": "నేను గత వారం స్లాట్ బుక్ చేశాను ఆ తర్వాత మా అన్నయ్య ఫోన్ చేశాడు,",
}
QUESTIONS: list[tuple[Lang, str]] = [
    ("en", "and I wanted to know what time you open?"),
    ("en", "I booked last week but can you move it to Monday"),
    ("en", "my order was placed on Monday last week, right"),
    ("hi", "मैंने पिछले हफ़्ते बुक किया था लेकिन क्या आप इसे बदल सकते हैं"),
    ("hi", "mera order pichle hafte aaya tha lekin kab deliver hoga"),
    ("te", "నేను గత వారం బుక్ చేశాను కానీ ఎప్పుడు వస్తుంది"),
    ("te", "నేను గత వారం బుక్ చేశాను ఇప్పుడు మార్చగలరా"),
]


def policy(lang: Lang = "en", seed: int = 7) -> BackchannelPolicy:
    return BackchannelPolicy(lang, seed=seed)


class TestBackchannelTiming:
    def test_needs_3500_ms_of_speech(self) -> None:
        p = policy()
        assert p.on_user_speech(3499, EXPLAINING["en"], 400) is None
        assert p.on_user_speech(3500, EXPLAINING["en"], 400) is not None

    @pytest.mark.parametrize(("pause", "fires"), [(0, False), (249, False), (250, True),
                                                  (500, True), (700, True), (701, False),
                                                  (1500, False)])  # fmt: skip
    def test_clause_boundary_pause_window(self, pause: int, fires: bool) -> None:
        assert (policy().on_user_speech(5000, EXPLAINING["en"], pause) is not None) is fires

    def test_min_gap_4000_ms(self) -> None:
        p = policy()
        assert p.on_user_speech(4000, EXPLAINING["en"], 300) is not None
        assert p.on_user_speech(7000, EXPLAINING["en"], 300) is None  # window 1, gap 3000
        assert p.on_user_speech(7999, EXPLAINING["en"], 300) is None
        assert p.on_user_speech(8000, EXPLAINING["en"], 300) is not None

    def test_at_most_one_per_6_second_block(self) -> None:
        p = policy()
        assert p.on_user_speech(6000, EXPLAINING["en"], 300) is not None  # block 1
        assert p.on_user_speech(10000, EXPLAINING["en"], 300) is None  # gap ok, block 1 used
        assert p.on_user_speech(11999, EXPLAINING["en"], 300) is None
        assert p.on_user_speech(12000, EXPLAINING["en"], 300) is not None  # block 2

    def test_long_monologue_rate(self) -> None:
        p = policy()
        fired = [t for t in range(0, 60_000, 100) if p.on_user_speech(t, EXPLAINING["en"], 400)]
        assert len(fired) <= 10
        assert all(b - a >= 4000 for a, b in pairwise(fired))
        assert len({t // 6000 for t in fired}) == len(fired)

    def test_new_turn_resets_when_elapsed_goes_back(self) -> None:
        p = policy()
        assert p.on_user_speech(5000, EXPLAINING["en"], 300) is not None
        assert p.on_user_speech(5500, EXPLAINING["en"], 300) is None
        assert p.on_user_speech(4000, EXPLAINING["en"], 300) is not None  # new turn

    def test_explicit_new_turn(self) -> None:
        p = policy()
        assert p.on_user_speech(5000, EXPLAINING["en"], 300) is not None
        p.new_turn()
        assert p.on_user_speech(5000, EXPLAINING["en"], 300) is not None

    def test_rejects_negative_inputs(self) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            policy().on_user_speech(-1, "x", 300)


class TestBackchannelContent:
    @pytest.mark.parametrize(("lang", "text"), QUESTIONS)
    def test_never_during_a_question(self, lang: Lang, text: str) -> None:
        assert policy(lang).on_user_speech(5000, text, 400) is None

    @pytest.mark.parametrize("text", ["", "hello", "yes I think so"])
    def test_needs_enough_words(self, text: str) -> None:
        assert policy().on_user_speech(5000, text, 400) is None

    @pytest.mark.parametrize("lang", ["en", "hi", "te"])
    def test_tokens_are_per_language(self, lang: Lang) -> None:
        token = policy(lang).on_user_speech(5000, EXPLAINING[lang], 400)
        assert token in TOKENS[lang]

    @pytest.mark.parametrize("lang", ["en", "hi", "te"])
    def test_mid_explanation_detected(self, lang: Lang) -> None:
        assert looks_mid_explanation(EXPLAINING[lang], lang)

    def test_telugu_common_aa_words_are_not_questions(self) -> None:
        assert looks_mid_explanation("నేను గత వారం బుక్ చేశాను అది చాలా", "te")

    @pytest.mark.parametrize("seed", range(5))
    def test_no_immediate_repeats(self, seed: int) -> None:
        p = policy(seed=seed)
        tokens = []
        for _ in range(30):
            p.new_turn()
            token = p.on_user_speech(4000, EXPLAINING["en"], 300)
            assert token is not None
            tokens.append(token)
        assert all(a != b for a, b in pairwise(tokens))
        assert set(tokens) == set(TOKENS["en"])

    def test_deterministic_with_seed(self) -> None:
        def run(seed: int) -> list[str | None]:
            p = policy("hi", seed)
            out = []
            for _ in range(10):
                p.new_turn()
                out.append(p.on_user_speech(4000, EXPLAINING["hi"], 300))
            return out

        assert run(42) == run(42)
        assert any(run(42) != run(s) for s in range(1, 6))

    def test_rejects_unknown_language(self) -> None:
        with pytest.raises(ValueError, match="unsupported language"):
            BackchannelPolicy("ta")  # type: ignore[arg-type]


class TestFillerPolicy:
    @pytest.mark.parametrize(("latency", "fires"), [(0, False), (700, False), (701, True),
                                                    (2500, True)])  # fmt: skip
    def test_latency_threshold(self, latency: int, fires: bool) -> None:
        assert (FillerPolicy("en", seed=1).filler_for(latency, 0) is not None) is fires

    def test_at_most_once_every_two_turns(self) -> None:
        p = FillerPolicy("en", seed=1)
        assert p.filler_for(1200, 0) is not None
        assert p.filler_for(1200, 1) is None
        assert p.filler_for(1200, 2) is not None
        assert p.filler_for(1200, 2) is None  # never twice in one turn
        assert p.filler_for(1200, 3) is None
        assert p.filler_for(1200, 4) is not None

    def test_low_latency_turn_does_not_consume_quota(self) -> None:
        p = FillerPolicy("en", seed=1)
        assert p.filler_for(300, 0) is None
        assert p.filler_for(1200, 1) is not None

    @pytest.mark.parametrize("lang", ["en", "hi", "te"])
    @pytest.mark.parametrize("seed", range(4))
    def test_never_same_as_last_time(self, lang: Lang, seed: int) -> None:
        p = FillerPolicy(lang, seed=seed)
        said = [p.filler_for(1500, turn) for turn in range(0, 60, 2)]
        assert None not in said
        assert all(a != b for a, b in pairwise(said))
        assert set(said) <= set(fillers(lang))

    def test_deterministic_with_seed(self) -> None:
        def run(seed: int) -> list[str | None]:
            p = FillerPolicy("te", seed=seed)
            return [p.filler_for(1500, t) for t in range(0, 20, 2)]

        assert run(3) == run(3)

    def test_hindi_gendered_verbs(self) -> None:
        female = " ".join(fillers("hi", "female"))
        male = " ".join(fillers("hi", "male"))
        assert "देखती" in female
        assert "देखता" not in female
        assert "देखता" in male
        assert "देखती" not in male
        p = FillerPolicy("hi", seed=0, gender="male")
        assert p.filler_for(1500, 0) in fillers("hi", "male")

    def test_turn_counter_restart_is_a_new_call(self) -> None:
        p = FillerPolicy("en", seed=1)
        assert p.filler_for(1500, 5) is not None
        assert p.filler_for(1500, 0) is not None

    def test_rejects_bad_arguments(self) -> None:
        with pytest.raises(ValueError, match="unsupported language"):
            FillerPolicy("xx")  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="gender"):
            FillerPolicy("hi", gender="other")  # type: ignore[arg-type]
