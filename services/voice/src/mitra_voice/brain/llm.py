"""The live-call LLM for ``MITRA_LLM=gemini|groq``: Pipecat's ``GoogleLLMService`` /
``GroqLLMService`` driving the brain.

Each service keeps Pipecat's provider plumbing (client, settings, metrics, interruption
handling) but replaces the inference step: each ``LLMContextFrame`` becomes one
:class:`Brain` turn, so a live call and a text-mode eval run exactly the same guardrails,
prompt, tools and post-check.
Tools run inside the brain (no function-call frames reach the pipeline); only checked reply
sentences are pushed downstream as LLM text, which ``SpeakableProcessor`` then normalises.
"""

from __future__ import annotations

from typing import Any

import structlog
from pipecat.frames.frames import LLMFullResponseEndFrame, LLMFullResponseStartFrame, TTSSpeakFrame
from pipecat.metrics.metrics import LLMTokenUsage
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.frame_processor import FrameProcessor
from pipecat.services.google.llm import GoogleLLMService
from pipecat.services.groq.llm import GroqLLMService
from pipecat.services.llm_service import LLMService

from mitra_voice.brain.backend import ChatBackend
from mitra_voice.brain.client import brain_clock, brain_config
from mitra_voice.brain.engine import Brain, BrainConfig, Message, TurnResult, filler_for
from mitra_voice.brain.gemini_backend import GeminiBackend
from mitra_voice.brain.language import CallerLanguage, LanguageRef
from mitra_voice.brain.openai_backend import OpenAICompatBackend
from mitra_voice.call_context import CallContext
from mitra_voice.config import Settings
from mitra_voice.pack import EmployeePack

log = structlog.get_logger(__name__)


def _text_of(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(
            str(p.get("text", "")) for p in content if isinstance(p, dict) and p.get("text")
        )
    return ""


def history_from_context(context: LLMContext) -> tuple[list[Message], str]:
    """(earlier turns, the caller's current utterance) from Pipecat's context messages.

    System messages are skipped (the brain owns the system prompt); consecutive caller messages
    since the last assistant reply form the current utterance.
    """
    turns: list[Message] = []
    for raw in context.get_messages():
        if not isinstance(raw, dict):
            continue
        role, text = raw.get("role"), _text_of(raw.get("content")).strip()
        if not text or role not in {"user", "assistant"}:
            continue
        if turns and turns[-1].role == role:
            turns[-1] = Message(role, f"{turns[-1].text} {text}")
        else:
            turns.append(Message("user" if role == "user" else "assistant", text))
    if turns and turns[-1].role == "user":
        return turns[:-1], turns[-1].text
    return turns, ""


class BrainTurns:
    """The per-call brain plus the language state; runs one turn on behalf of a service."""

    def __init__(
        self,
        backend: ChatBackend,
        config: BrainConfig,
        pack: EmployeePack,
        settings: Settings,
        call: CallContext,
    ) -> None:
        self.brain = Brain(backend, config, pack, clock=brain_clock(settings))
        self.call = call
        self._language = LanguageRef(call.language)

    def caller_language(self, text: str) -> CallerLanguage:
        """The pipeline's call language (script + STT tag) refined with code-mix from the text."""
        self._language.set(self.call.language)
        return self._language.resolve(text)

    async def run(self, service: LLMService[Any], context: LLMContext) -> None:
        history, caller_text = history_from_context(context)
        if not caller_text:
            return
        lang = self.caller_language(caller_text)
        result = TurnResult()
        brain, call = self.brain, self.call
        out: FrameProcessor = service

        async def on_retry() -> None:
            # The first token is late: say a short filler (kept out of the context) while the
            # brain retries. At most one filler per turn (TRD §5): skip it if the pipeline's
            # FillerProcessor already spoke one.
            if call.filler_spoken:
                return
            call.filler_spoken = True
            await out.push_frame(TTSSpeakFrame(filler_for(lang)))

        before = brain.usage.prompt_tokens, brain.usage.output_tokens, brain.usage.cached_tokens
        await service.push_frame(LLMFullResponseStartFrame())
        await service.start_ttfb_metrics()
        first = True
        try:
            async for sentence in brain.stream_turn(
                history, caller_text, lang, result, on_retry=on_retry
            ):
                if first:
                    await service.stop_ttfb_metrics()
                    first = False
                await service._push_llm_text(f"{sentence} ")
        finally:
            u = brain.usage
            prompt, output = u.prompt_tokens - before[0], u.output_tokens - before[1]
            await service.start_llm_usage_metrics(
                LLMTokenUsage(
                    prompt_tokens=prompt,
                    completion_tokens=output,
                    total_tokens=prompt + output,
                    cache_read_input_tokens=u.cached_tokens - before[2],
                )
            )
            await service.push_frame(LLMFullResponseEndFrame())
            log.info(
                "brain.turn",
                provider=brain.backend.provider,
                lang=lang,
                guard=result.guard,
                actions=[a.name for a in result.actions],
                violations=result.violations,
                retried=result.retried,
                failed=result.failed,
                first_token_ms=round(result.first_token_ms or 0),
            )


def _key(secret: Any, name: str) -> str:
    if secret is None or not secret.get_secret_value().strip():
        raise ValueError(f"{name} is not set")
    value: str = secret.get_secret_value()
    return value


class MitraBrainLLMService(GoogleLLMService):
    """GoogleLLMService whose inference is a guarded, tool-using brain turn (Gemini)."""

    def __init__(
        self, *, pack: EmployeePack, settings: Settings, call: CallContext, **kwargs: Any
    ) -> None:
        config = brain_config(settings)
        super().__init__(
            api_key=_key(settings.gemini_api_key, "GEMINI_API_KEY"),
            settings=GoogleLLMService.Settings(
                model=config.model,
                temperature=config.temperature,
                max_tokens=config.max_output_tokens,
            ),
            **kwargs,
        )
        if self._client is None:  # created by GoogleLLMService.__init__
            raise RuntimeError("Gemini client was not created")
        backend = GeminiBackend(self._client.aio.models)
        self.turns = BrainTurns(backend, config, pack, settings, call)

    @property
    def brain(self) -> Brain:
        return self.turns.brain

    async def _process_context(self, context: LLMContext) -> None:
        await self.turns.run(self, context)


class MitraGroqBrainLLMService(GroqLLMService):
    """GroqLLMService whose inference is a guarded, tool-using brain turn (Groq, free tier)."""

    def __init__(
        self, *, pack: EmployeePack, settings: Settings, call: CallContext, **kwargs: Any
    ) -> None:
        config = brain_config(settings)
        super().__init__(
            api_key=_key(settings.groq_api_key, "GROQ_API_KEY"),
            settings=GroqLLMService.Settings(
                model=config.model,
                temperature=config.temperature,
                max_tokens=config.max_output_tokens,
            ),
            **kwargs,
        )
        backend = OpenAICompatBackend(self._client, provider="groq")
        self.turns = BrainTurns(backend, config, pack, settings, call)

    @property
    def brain(self) -> Brain:
        return self.turns.brain

    async def _process_context(self, context: LLMContext) -> None:
        await self.turns.run(self, context)


def make_brain_llm(
    *, pack: EmployeePack, settings: Settings, call: CallContext
) -> MitraBrainLLMService | MitraGroqBrainLLMService:
    """Factory for ``providers.make_llm`` when ``MITRA_LLM`` is ``gemini`` or ``groq``."""
    if settings.mitra_llm == "groq":
        return MitraGroqBrainLLMService(pack=pack, settings=settings, call=call)
    return MitraBrainLLMService(pack=pack, settings=settings, call=call)


make_gemini_llm = make_brain_llm

__all__ = [
    "BrainTurns",
    "MitraBrainLLMService",
    "MitraGroqBrainLLMService",
    "history_from_context",
    "make_brain_llm",
    "make_gemini_llm",
]
