"""Mitra's conversational brain on Gemini (Step 3b): prompt, guardrails, tools, language policy.

- ``engine.Brain``: one caller turn -> checked, streamed reply + tool actions (shared by live
  calls and text-mode evals).
- ``llm.make_brain_llm``: the Pipecat LLM service for ``MITRA_LLM=gemini``.

Everything heavy (``google.genai``, Pipecat's Google service) is imported here at module level,
so the startup warm-up (``import mitra_voice.brain``) keeps it off the first call's event loop.
"""

from __future__ import annotations

from mitra_voice.brain.llm import MitraBrainLLMService, make_brain_llm

__all__ = ["MitraBrainLLMService", "make_brain_llm"]
