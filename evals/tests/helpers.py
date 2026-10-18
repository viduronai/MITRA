from __future__ import annotations

from mitra_evals.results import ActionRecord, TranscriptTurn
from mitra_evals.schema import Scenario


def scenario(**overrides: object) -> Scenario:
    """A minimal valid clinic scenario; override any field."""
    data: dict[str, object] = {
        "id": "t.fee.en",
        "title": "Fee",
        "industry": "clinic",
        "language": "en",
        "persona": "standard",
        "pack": "sunrise_clinic",
        "turns": [{"text": "What is the fee?", "reference": "It is ₹500."}],
    }
    data.update(overrides)
    return Scenario.model_validate(data)


def transcript(
    greeting: str, *pairs: tuple[str, str], actions: tuple[str, ...] = ()
) -> list[TranscriptTurn]:
    """Greeting, then (caller, agent) pairs; ``actions`` go on the last agent turn."""
    turns = [TranscriptTurn(speaker="agent", text=greeting)]
    for i, (caller, agent) in enumerate(pairs):
        turns.append(TranscriptTurn(speaker="caller", text=caller, caller_turn=i))
        turns.append(TranscriptTurn(speaker="agent", text=agent, caller_turn=i))
    if actions:
        turns[-1] = turns[-1].model_copy(
            update={"actions": [ActionRecord(name=a) for a in actions]}
        )
    return turns


GREETING = (
    "Hello, this is Priya, an AI assistant from Sunrise Clinic. This call may be recorded "
    "to help serve you better. How can I help you today?"
)
