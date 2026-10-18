"""Agent-under-test adapters, built by name."""

from __future__ import annotations

from mitra_evals.agents.base import (
    Action,
    AgentReply,
    AgentUnavailableError,
    AgentUnderTest,
    CallContext,
    ConversationSession,
    TurnTimings,
)
from mitra_evals.schema import Scenario

AGENT_NAMES = ("scripted", "reference", "core-sim", "voice-text")


def build_agent(name: str, scenarios: dict[str, Scenario]) -> AgentUnderTest:
    if name == "scripted":
        from mitra_evals.agents.scripted import ScriptedAgent

        return ScriptedAgent()
    if name == "reference":
        from mitra_evals.agents.reference import ReferenceAgent

        return ReferenceAgent(scenarios)
    if name == "core-sim":
        from mitra_evals.agents.core_sim import CoreSimAgent

        return CoreSimAgent()
    if name == "voice-text":
        from mitra_evals.agents.voice_text import voice_text_agent

        return voice_text_agent()
    raise ValueError(f"unknown agent {name!r}; choose from {', '.join(AGENT_NAMES)}")


__all__ = [
    "AGENT_NAMES",
    "Action",
    "AgentReply",
    "AgentUnavailableError",
    "AgentUnderTest",
    "CallContext",
    "ConversationSession",
    "TurnTimings",
    "build_agent",
]
