"""The opening line must always disclose that the caller is talking to an AI (docs/08 §4)."""

from mitra_core.simulation import opening_line


def test_default_greeting_discloses_ai_and_recording() -> None:
    line = opening_line("Sunrise Clinic", "Priya", None)
    assert "AI assistant" in line
    assert "recorded" in line
    assert "Sunrise Clinic" in line
    assert "Priya" in line


def test_custom_greeting_without_ai_mention_gets_disclosure_prefixed() -> None:
    line = opening_line("Sunrise Clinic", "Priya", "Hello! How may I help?")
    assert line.startswith("Namaste! This is Priya, an AI assistant from Sunrise Clinic.")
    assert line.endswith("Hello! How may I help?")


def test_custom_greeting_with_ai_mention_is_kept_as_is() -> None:
    custom = "Hi, Priya here, Sunrise Clinic's AI assistant. How can I help?"
    assert opening_line("Sunrise Clinic", "Priya", custom) == custom


def test_ai_must_be_a_whole_word() -> None:
    line = opening_line("Sunrise Clinic", "Priya", "Welcome to SAIL clinic, how can I help?")
    assert "an AI assistant" in line
