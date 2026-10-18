from __future__ import annotations

from pipecat.frames.frames import (
    LLMContextFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
)
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.tests.utils import run_test

from mitra_voice.pack import FIXTURES_DIR, load_fixture, pack_from_dict
from mitra_voice.providers.mock_llm import MockLLMService, mock_answer

CLINIC = load_fixture(FIXTURES_DIR / "sunrise-clinic.json")
REALTY = load_fixture(FIXTURES_DIR / "greenfield-realty.json")


def test_answers_fee_from_facts() -> None:
    answer = mock_answer(CLINIC, "Hi, what is the consultation fee?")
    assert answer.text == "The consultation fee is ₹500."
    assert answer.intent == "price"
    assert not answer.uses_tool


def test_picks_the_best_matching_fact() -> None:
    assert "₹250" in mock_answer(CLINIC, "How much is the follow-up visit fee?").text
    assert mock_answer(REALTY, "What is the price range for a 2 BHK?").text == (
        "The 2 BHK price range is ₹65 lakh to ₹80 lakh."
    )
    assert "₹1.1 crore" in mock_answer(REALTY, "And the 3 BHK price?").text


def test_answers_timings_and_location() -> None:
    timings = mock_answer(CLINIC, "What are your timings?").text
    assert timings.startswith("Our clinic timings are Monday to Saturday")
    assert "Banjara Hills" in mock_answer(CLINIC, "Where exactly are you located?").text
    assert "Greenfield Meadows" in mock_answer(REALTY, "Which projects do you have?").text


def test_defers_politely_when_a_fact_is_missing() -> None:
    no_facts = pack_from_dict(
        {
            "business_id": "b",
            "business_name": "Empty Clinic",
            "industry": "clinic",
            "employee_id": "e",
            "employee_name": "Priya",
            "role_template": "receptionist",
            "languages": ["en"],
        }
    )
    answer = mock_answer(no_facts, "What is the consultation fee?")
    assert "₹" not in answer.text
    assert "confirm the exact price" in answer.text
    unknown = mock_answer(CLINIC, "Do you have parking near the clinic?")
    assert unknown.intent == "unknown"
    assert "confirm with the team" in unknown.text


def test_booking_is_a_tool_turn_and_asks_for_required_details() -> None:
    answer = mock_answer(CLINIC, "Book me for tomorrow evening.")
    assert answer.uses_tool
    assert "tomorrow at 6 PM is free" in answer.text
    assert "the patient's name" in answer.text
    assert "Saturday at 11 AM" in mock_answer(REALTY, "Can I book a site visit this weekend?").text


async def test_streams_tokens_from_a_context_frame() -> None:
    context = LLMContext(
        messages=[
            {"role": "system", "content": "rules"},
            {"role": "user", "content": "Hi, what is the consultation fee?"},
        ]
    )
    llm = MockLLMService(CLINIC, ttft_ms=10, token_ms=0)
    down, _ = await run_test(llm, frames_to_send=[LLMContextFrame(context)])
    response = (LLMFullResponseStartFrame, LLMTextFrame, LLMFullResponseEndFrame)
    types = [type(f) for f in down if isinstance(f, response)]
    assert types[0] is LLMFullResponseStartFrame
    assert types[-1] is LLMFullResponseEndFrame
    text = "".join(f.text for f in down if isinstance(f, LLMTextFrame))
    assert text == "The consultation fee is ₹500."
    assert sum(isinstance(f, LLMTextFrame) for f in down) == len(text.split())
