"""Deterministic brain pieces: guardrails, ₹ post-check, language policy, simulated tools."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from mitra_voice.brain.gemini_backend import GeminiBackend
from mitra_voice.brain.guardrails import (
    PostCheck,
    money_amounts,
    pre_check,
    split_sentences,
)
from mitra_voice.brain.language import LanguageRef, detect_language, normalise_code
from mitra_voice.brain.tools import IST, Calendar, ToolExecutor, parse_date, parse_time
from mitra_voice.pack import EmployeePack
from mitra_voice.text_sessions import pack_from_eval

FIXTURES = Path(__file__).resolve().parents[3] / "evals" / "fixtures"
WEDNESDAY_8AM = datetime(2026, 10, 21, 8, 0, tzinfo=IST)


def _eval_pack(name: str) -> dict[str, Any]:
    path = FIXTURES / f"{name}.json"
    if not path.exists():
        pytest.skip("evals fixtures not present")
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


@pytest.fixture
def clinic() -> EmployeePack:
    return pack_from_eval(_eval_pack("sunrise_clinic"))


@pytest.fixture
def realty() -> EmployeePack:
    return pack_from_eval(_eval_pack("skyline_homes"))


# --- pre-check ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "lang"),
    [
        ("My father is having severe chest pain and he's sweating a lot.", "en"),
        ("మా అమ్మకి ఛాతీ నొప్పి వస్తుంది, ఊపిరి ఆడట్లేదు", "te"),
        ("मेरे पति अचानक बेहोश हो गए हैं, उठ नहीं रहे!", "hi"),
        ("Road మీద accident అయ్యింది, చాలా bleeding అవుతుంది", "te-en"),
        ("मुझे सीने में दर्द हो रहा है", "hi"),
        ("मेरा भाई बोल रहा है कि वो suicide कर लेगा", "hi-en"),
    ],
)
def test_emergency_short_circuits_to_112_transfer_and_alert(
    clinic: EmployeePack, text: str, lang: Any
) -> None:
    hit = pre_check(text, lang, clinic)
    assert hit is not None
    assert hit.kind == "emergency"
    assert hit.reply is not None
    assert "112" in hit.reply
    assert {name for name, _ in hit.actions} == {"transfer_to_human", "alert_staff"}
    # Never quote fees or offer a booking in an emergency turn.
    assert not money_amounts(hit.reply)
    for word in ("fee", "appointment", "ఫీజు", "అపాయింట్‌మెంట్", "फीस", "अपॉइंटमेंट", "₹"):
        assert word not in hit.reply.lower()


@pytest.mark.parametrize(
    ("text", "lang"),
    [
        ("No, I'm not interested. Please don't call me again.", "en"),
        ("Stop calling me. Remove my number from your list.", "en"),
        ("ఇంకోసారి నాకు కాల్ చేయకండి, ప్లీజ్.", "te"),
        ("देखिए, मुझे बार-बार कॉल मत करो, मेरा नंबर हटा दो।", "hi"),
        ("Please मुझे फिर से call मत करना।", "hi-en"),
        ("call cheyakandi andi", "te-en"),
    ],
)
def test_opt_out_phrases(realty: EmployeePack, text: str, lang: Any) -> None:
    hit = pre_check(text, lang, realty)
    assert hit is not None
    assert hit.kind == "opt_out"
    assert hit.end_call
    assert [name for name, _ in hit.actions] == ["opt_out", "end_call"]
    assert hit.reply is not None
    assert "Skyline Homes" in hit.reply
    for pitch in ("offer", "visit", "project", "price", "ప్రాజెక్ట్", "प्रोजेक्ट"):
        assert pitch not in hit.reply.lower()


@pytest.mark.parametrize(
    "text",
    [
        "Which tablet should I take and how many times a day?",
        "డోలో వేసుకోవచ్చా? ఎన్ని వేసుకోవాలి?",
        "मेरी बेटी को खाँसी है, कौन सा सिरप दूँ? कितने ml?",
        "BP की tablet खत्म हो गई, double dose ले लूँ क्या?",
        "My knees are paining. Is it arthritis?",
        "TSH ज़्यादा तो नहीं है ना?",
    ],
)
def test_medical_advice_requests_get_a_turn_instruction(clinic: EmployeePack, text: str) -> None:
    hit = pre_check(text, "en", clinic)
    assert hit is not None
    assert hit.kind == "medical"
    assert hit.reply is None  # the LLM still answers (it may offer the right doctor)
    assert hit.turn_instruction
    assert "GUARDRAIL" in hit.turn_instruction


@pytest.mark.parametrize(
    "text",
    [
        "Can I take an appointment for tomorrow?",
        "What is the consultation fee?",
        "Is Skyline Riverside RERA approved?",
        "మీ క్లినిక్ ఎక్కడ ఉంది అండి?",
    ],
)
def test_ordinary_questions_pass_through(clinic: EmployeePack, text: str) -> None:
    assert pre_check(text, "en", clinic) is None


# --- post-check -----------------------------------------------------------------------------------


def test_money_amounts_handles_units_scripts_and_bare_numbers() -> None:
    assert money_amounts("The fee is ₹500, follow-up Rs. 200") == [500, 200]
    assert money_amounts("2 BHK 58 లక్షల నుండి") == [5_800_000]
    assert money_amounts("बुकिंग टोकन 2 लाख है") == [200_000]
    assert money_amounts("₹5,000 per sq ft, ₹1.5 crore") == [5_000, 15_000_000]
    assert money_amounts("Call 112 or come to Road No. 5, 1,150 sq ft") == []


def test_rupee_post_check_replaces_ungrounded_amounts(
    clinic: EmployeePack, realty: EmployeePack
) -> None:
    ok, found = PostCheck(clinic).apply("The consultation fee is ₹500. Shall I book?", "en")
    assert found == []
    assert ok == "The consultation fee is ₹500. Shall I book?"

    text, found = PostCheck(clinic).apply("A scan is ₹1,200. Shall I book it?", "en")
    assert found == ["amount"]
    assert "1,200" not in text
    assert "WhatsApp" in text
    assert text.endswith("Shall I book it?")

    te, found = PostCheck(clinic).apply("ఫీజు 700 రూపాయలు అండి.", "te")
    assert found == ["amount"]
    assert "700" not in te

    # Amounts the caller said are grounded too ("my budget is 60 lakh").
    post = PostCheck(realty, caller_texts=["My budget is around 60 lakhs"])
    assert post.apply("Within your 60 lakh budget, the 2 BHK starts at ₹58 lakh.", "en")[1] == []
    assert PostCheck(realty).apply("The 3 BHK is ₹80 lakh.", "en")[1] == ["amount"]


def test_medical_post_check_blocks_medicines_doses_and_echoed_conditions(
    clinic: EmployeePack,
) -> None:
    text, found = PostCheck(clinic).apply("You can take Dolo 650 mg twice a day.", "en")
    assert found == ["medical"]
    assert "Dolo" not in text
    assert "doctor" in text
    # Condition names are only blocked on a medical-advice turn.
    post = PostCheck(clinic)
    assert post.apply("I can't say if it's arthritis.", "en", medical_turn=True)[1] == ["medical"]
    assert post.apply("Dr. Kavitha sees patients daily.", "en", medical_turn=True)[1] == []
    te = post.apply("రిపోర్ట్ నార్మల్‌గా ఉంది అండి.", "te", medical_turn=True)
    assert te[1] == ["medical"]


def test_real_estate_claims_are_removed(realty: EmployeePack) -> None:
    text, found = PostCheck(realty).apply(
        "Prices will double in five years. Possession is December 2027.", "en"
    )
    assert found == ["claim"]
    assert "double" not in text
    assert "December 2027" in text


def test_sentence_split_keeps_titles_together() -> None:
    assert split_sentences("Dr. Kavitha is in. Road No. 5, near Cyber Towers!") == [
        "Dr. Kavitha is in.",
        "Road No. 5, near Cyber Towers!",
    ]


def test_gemini_rate_limit_delay_parsing() -> None:
    backend = GeminiBackend(None)  # type: ignore[arg-type]
    assert backend.rate_limit_delay(RuntimeError("429 ... 'retryDelay': '3s'")) == 4.0
    assert backend.rate_limit_delay(RuntimeError("500 internal")) is None
    assert backend.is_transient(RuntimeError("503 UNAVAILABLE"))


# --- language -------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Hi, what is the consultation fee?", "en"),
        ("హలో అండి, డాక్టర్ దగ్గర కన్సల్టేషన్ ఫీజు ఎంత?", "te"),
        ("ఈ ప్రాజెక్ట్‌కి RERA అప్రూవల్ ఉందా అండి?", "te"),
        ("Quick గా ఒక appointment book చేయండి, today evening.", "te-en"),
        ("हाँ जी, डॉक्टर को दिखाने की फीस कितनी है?", "hi"),
        ("जल्दी बताइए, evening में कब तक खुला है?", "hi-en"),
        ("कौन सा सिरप दूँ? कितने ml?", "hi"),
        ("call cheyakandi andi, nenu busy", "te-en"),
        ("mujhe call mat karo bhai", "hi-en"),
    ],
)
def test_detect_language(text: str, expected: str) -> None:
    assert detect_language(text) == expected


def test_language_ref_prefers_stt_and_keeps_code_mix_sticky() -> None:
    ref = LanguageRef("hi-en")
    # A Hinglish caller's all-Devanagari sentence stays Hinglish.
    assert ref.resolve("क्या? ज़रा फिर से बोलिए") == "hi-en"
    ref = LanguageRef("en")
    ref.set("te-IN")
    assert ref.resolve("Monday ki shift cheyandi") == "te"  # STT says Telugu: trust it
    assert ref.resolve("11") == "te"  # no letters: keep the last language
    assert normalise_code("hi_IN") == "hi"
    assert normalise_code("ml-IN") is None


# --- tools ----------------------------------------------------------------------------------------


def test_calendar_built_from_pack_timings(clinic: EmployeePack, realty: EmployeePack) -> None:
    cal = Calendar.from_pack(clinic)
    assert cal.slot_minutes == 15
    assert cal.hours[0] == [(540, 780), (1020, 1260)]  # Monday 9-1, 5-9
    assert cal.hours[6] == [(600, 780)]  # Sunday 10-1 only
    estate = Calendar.from_pack(realty)
    assert all(estate.hours[d] == [(600, 1080)] for d in range(7))  # every day 10-6


def test_parse_date_and_time() -> None:
    today = WEDNESDAY_8AM.date()
    assert parse_date("2026-10-25", today).isoformat() == "2026-10-25"  # type: ignore[union-attr]
    assert parse_date("tomorrow", today).isoformat() == "2026-10-22"  # type: ignore[union-attr]
    assert parse_date("Sunday", today).isoformat() == "2026-10-25"  # type: ignore[union-attr]
    assert parse_date("next wednesday", today).isoformat() == "2026-10-28"  # type: ignore[union-attr]
    assert parse_date("someday", today) is None
    assert parse_time("18:30") == 1110
    assert parse_time("6 PM") == 1080
    assert parse_time("10:30 am") == 630
    assert parse_time("noonish") is None


def test_tool_executor_books_and_offers_alternatives(clinic: EmployeePack) -> None:
    tools = ToolExecutor(clinic, clock=lambda: WEDNESDAY_8AM)
    free = tools.execute("check_availability", {"date": "2026-10-22", "part_of_day": "evening"})
    assert free["available"] is True
    assert all(slot >= "17:00" for slot in free["free_slots"])
    closed = tools.execute("check_availability", {"date": "2026-10-25", "time": "18:00"})
    assert closed["available"] is False  # Sunday evening: closed
    assert "alternatives" in closed
    slot = free["free_slots"][0]
    booked = tools.execute("book_slot", {"date": "2026-10-22", "time": slot, "name": "Rahul"})
    assert booked["status"] == "booked"
    assert booked["booking_id"].startswith("SC-")
    again = tools.execute("book_slot", {"date": "2026-10-22", "time": slot})
    assert again["status"] == "unavailable"  # the slot is taken now
    moved = tools.execute("reschedule", {"new_date": "2026-10-23", "new_time": "10:00"})
    assert moved["status"] in {"rescheduled", "unavailable"}
    assert tools.execute("transfer_to_human", {"reason": "x"})["to"] == "Front desk (Ramesh)"
    assert tools.execute("no_such_tool", {})["error"]
    tools.execute("end_call", {})
    assert tools.end_call
    assert [c.name for c in tools.calls][:3] == ["check_availability"] * 2 + ["book_slot"]
    assert any("book_slot" in line for line in tools.log_lines())
    assert tools.today_line().startswith("Now: Wednesday 2026-10-21, 08:00")


def test_tool_executor_rejects_the_past(clinic: EmployeePack) -> None:
    tools = ToolExecutor(clinic, clock=lambda: WEDNESDAY_8AM)
    assert "error" in tools.execute("check_availability", {"date": "2026-10-20"})
    assert "error" in tools.execute("book_slot", {"date": "whenever", "time": "10:00"})
