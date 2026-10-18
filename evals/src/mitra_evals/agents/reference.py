"""``reference``: replays the golden reference replies. Not a real agent; it is the upper bound
that proves every scenario's assertions are satisfiable (and that patterns aren't over-broad)."""

from __future__ import annotations

from mitra_evals.agents.base import Action, AgentReply, CallContext, ConversationSession
from mitra_evals.schema import EmployeePack, Scenario, base_language


class _Session:
    def __init__(self, pack: EmployeePack, context: CallContext, scenario: Scenario) -> None:
        self._pack, self._context, self._scenario = pack, context, scenario
        self._next = 0

    async def start(self) -> AgentReply:
        table = getattr(self._pack.greeting, self._context.direction)
        return AgentReply(text=table[base_language(self._context.language)])

    async def send(self, caller_text: str, *, interrupt: bool = False) -> AgentReply:
        turn = self._scenario.turns[self._next]
        self._next += 1
        return AgentReply(
            text=turn.reference,
            actions=tuple(Action(name=a) for a in turn.reference_actions),
            end_call="end_call" in turn.reference_actions,
        )

    async def close(self) -> None:
        return None


class ReferenceAgent:
    name = "reference"

    def __init__(self, scenarios: dict[str, Scenario]) -> None:
        self._scenarios = scenarios

    async def open(self, pack: EmployeePack, context: CallContext) -> ConversationSession:
        return _Session(pack, context, self._scenarios[context.scenario_id])
