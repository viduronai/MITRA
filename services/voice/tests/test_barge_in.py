"""Barge-in wiring: words played -> truncate_to_heard -> LLM context rewrite."""

from __future__ import annotations

from pipecat.frames.frames import TTSTextFrame
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.tests.utils import run_test
from pipecat.utils.text.base_text_aggregator import AggregationType

from mitra_voice.processors.reply import HeardTracker, ReplyLog, apply_heard_to_context

REPLY = "The consultation fee is five hundred rupees. Shall I book it?"


def _reply(words_played: int = 0) -> ReplyLog:
    log = ReplyLog()
    log.start()
    log.add("The consultation fee is five hundred rupees.")
    log.add("Shall I book it?")
    for word in REPLY.split()[:words_played]:
        log.on_word_played(word)
    return log


def test_heard_is_the_played_prefix() -> None:
    assert _reply(0).heard() == ""
    assert _reply(4).heard() == "The consultation fee is…"
    assert _reply(7).heard() == "The consultation fee is five hundred rupees."
    assert _reply(len(REPLY.split())).heard() == REPLY


def test_only_the_replys_own_words_advance_the_count() -> None:
    log = _reply()
    for word in ["Sure,", "one", "second."]:  # a filler played before the answer
        log.on_word_played(word)
    assert log.words_played == 0
    for word in ["The", "consultation", "fee"]:
        log.on_word_played(word)
    assert log.words_played == 3
    log.finish()
    log.on_word_played("is")
    assert log.words_played == 3


def test_context_is_rewritten_to_what_was_heard() -> None:
    context = LLMContext(
        messages=[
            {"role": "system", "content": "rules"},
            {"role": "user", "content": "fee?"},
            {"role": "assistant", "content": REPLY},
        ]
    )
    assert apply_heard_to_context(context, "The consultation fee is…")
    assert context.get_messages()[-1] == {
        "role": "assistant",
        "content": "The consultation fee is…",
    }
    assert not apply_heard_to_context(context, "The consultation fee is…")  # idempotent


def test_nothing_heard_drops_the_assistant_message() -> None:
    context = LLMContext(
        messages=[{"role": "user", "content": "fee?"}, {"role": "assistant", "content": REPLY}]
    )
    assert apply_heard_to_context(context, "")
    assert context.get_messages() == [{"role": "user", "content": "fee?"}]


async def test_heard_tracker_counts_words_leaving_the_output() -> None:
    log = _reply()
    frames = [
        TTSTextFrame(word, aggregated_by=AggregationType.WORD)
        for word in ["The", "consultation", "fee"]
    ]
    await run_test(HeardTracker(log), frames_to_send=frames)
    assert log.words_played == 3
    assert log.heard() == "The consultation fee…"
