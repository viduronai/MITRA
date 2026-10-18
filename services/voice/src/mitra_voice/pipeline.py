"""The per-call Pipecat pipeline (TRD §5, WORKFLOWS §1):

    transport.input
      -> STT -> LanguageTracker (caller language -> CallContext) -> UserSpeechTap
      -> user aggregator (Silero VAD + Smart Turn v3, or VAD silence timeout)
      -> FillerProcessor (instant ack if expected latency > 700 ms)
      -> LLM -> SpeakableProcessor (sentence chunks -> speakable())
      -> TTS -> BackchannelPlayer
    transport.output
      -> HeardTracker (words actually played) -> assistant aggregator

Barge-in: the user aggregator interrupts the bot when the caller starts talking (Pipecat stops
TTS and flushes queued audio); when the interrupted assistant turn stops, its context message is
rewritten with ``truncate_to_heard`` so the LLM knows exactly what the caller heard.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADAnalyzer, VADParams
from pipecat.frames.frames import TTSSpeakFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    AssistantTurnStoppedMessage,
    LLMAssistantAggregator,
    LLMContextAggregatorPair,
    LLMUserAggregator,
    LLMUserAggregatorParams,
    UserTurnStoppedMessage,
)
from pipecat.processors.frame_processor import FrameProcessor
from pipecat.turns.user_stop import (
    BaseUserTurnStopStrategy,
    SpeechTimeoutUserTurnStopStrategy,
    TurnAnalyzerUserTurnStopStrategy,
)
from pipecat.turns.user_turn_strategies import UserTurnStrategies

from mitra_voice.config import Settings, TurnStrategy
from mitra_voice.pack import Lang
from mitra_voice.processors.backchannel import BackchannelPlayer, UserSpeechState, UserSpeechTap
from mitra_voice.processors.filler import FillerProcessor, LatencyPredictor
from mitra_voice.processors.language import LanguageTracker
from mitra_voice.processors.recorder import ReplyRecorder
from mitra_voice.processors.reply import HeardTracker, ReplyLog, apply_heard_to_context
from mitra_voice.processors.speakable import SpeakableProcessor
from mitra_voice.prompt import build_prompt, greeting_for
from mitra_voice.providers import make_clips, make_llm, make_stt, make_tts
from mitra_voice.providers.clips import ClipSource, PrerenderedClips
from mitra_voice.session import CallSession
from mitra_voice.turn_tuning import TunableSmartTurn

AUDIO_IN_SAMPLE_RATE = 16000
AUDIO_OUT_SAMPLE_RATE = 24000
GREETING_START_TIMEOUT_S = 10.0


@dataclass
class CallPipeline:
    worker: PipelineWorker
    context: LLMContext
    user: LLMUserAggregator
    assistant: LLMAssistantAggregator
    reply: ReplyLog
    clips: ClipSource
    started: asyncio.Event = field(default_factory=asyncio.Event)
    tasks: set[asyncio.Task[int]] = field(default_factory=set)


def _stop_strategies(
    turn: TurnStrategy, smart_turn: TunableSmartTurn
) -> list[BaseUserTurnStopStrategy]:
    if turn == "smart":
        return [TurnAnalyzerUserTurnStopStrategy(turn_analyzer=smart_turn)]
    return [SpeechTimeoutUserTurnStopStrategy(user_speech_timeout=0.6)]


@dataclass
class TurnAnalyzers:
    vad: VADAnalyzer
    smart_turn: TunableSmartTurn


def make_turn_analyzers(settings: Settings) -> TurnAnalyzers:
    """Load the ONNX models (Silero, Smart Turn). Blocking: call it via ``asyncio.to_thread``."""
    override = settings.mitra_smart_turn_max_silence_ms
    return TurnAnalyzers(
        vad=SileroVADAnalyzer(params=VADParams(stop_secs=settings.mitra_vad_stop_ms / 1000)),
        smart_turn=TunableSmartTurn(override_s=override / 1000 if override else None),
    )


def build_call_pipeline(
    session: CallSession,
    settings: Settings,
    *,
    transport_input: FrameProcessor,
    transport_output: FrameProcessor,
    analyzers: TurnAnalyzers | None = None,
    vad: VADAnalyzer | None = None,
    turn: TurnStrategy | None = None,
) -> CallPipeline:
    pack, call = session.pack, session.call
    analyzers = analyzers or make_turn_analyzers(settings)
    smart_turn = analyzers.smart_turn
    smart_turn.tune_for(call.language)

    async def retune(lang: Lang) -> None:
        smart_turn.tune_for(lang)

    call.on_language_change.append(retune)
    context = LLMContext(
        messages=[{"role": "system", "content": build_prompt(pack).system_prompt()}]
    )
    aggregators = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            vad_analyzer=vad or analyzers.vad,
            user_turn_strategies=UserTurnStrategies(
                stop=_stop_strategies(turn or settings.mitra_turn, smart_turn)
            ),
        ),
    )
    user, assistant = aggregators.user(), aggregators.assistant()
    reply = ReplyLog()
    speech = UserSpeechState()

    async def on_filler(text: str) -> None:
        session.human_layer("filler", text)

    async def on_backchannel(token: str) -> None:
        session.human_layer("backchannel", token)

    async def on_sentence(text: str) -> None:
        session.assistant_delta(text)

    tool_latency = settings.mock_tool_latency_ms if session.providers.llm == "mock" else 0
    clips = make_clips(session.providers, settings, pack, AUDIO_OUT_SAMPLE_RATE)
    recorder = [ReplyRecorder(settings.mitra_record_dir, call)] if settings.mitra_record_dir else []
    pipeline = Pipeline(
        [
            transport_input,
            make_stt(session.providers, settings, pack, session.scenario),
            LanguageTracker(call),
            UserSpeechTap(speech),
            user,
            FillerProcessor(
                LatencyPredictor(session.tracker, tool_latency_ms=tool_latency),
                call=call,
                gender=pack.voice_gender,
                on_filler=on_filler,
            ),
            make_llm(session.providers, settings, pack, call),
            SpeakableProcessor(
                reply,
                call=call,
                tts_language=pack.default_language,
                first_chunk_words=settings.mitra_tts_first_chunk_words,
                on_sentence=on_sentence,
            ),
            make_tts(session.providers, settings, pack),
            *recorder,
            BackchannelPlayer(speech, call, clips, on_token=on_backchannel),
            transport_output,
            HeardTracker(reply),
            assistant,
        ]
    )

    @user.event_handler("on_user_turn_stopped")
    async def _on_user_turn_stopped(
        _: LLMUserAggregator, __: object, message: UserTurnStoppedMessage
    ) -> None:
        if message.content:
            session.add_user(message.content)

    @assistant.event_handler("on_assistant_turn_stopped")
    async def _on_assistant_turn_stopped(
        _: LLMAssistantAggregator, message: AssistantTurnStoppedMessage
    ) -> None:
        if not reply.active:
            return  # greeting / filler: not an LLM reply
        reply.finish()
        if message.interrupted and reply.words_played < len(reply.words):
            heard = reply.heard()
            apply_heard_to_context(context, heard)
            session.tracker.mark_reply_interrupted()
            session.add_assistant(heard, interrupted=True)
        else:
            session.add_assistant(reply.text or message.content)

    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(
            audio_in_sample_rate=AUDIO_IN_SAMPLE_RATE,
            audio_out_sample_rate=AUDIO_OUT_SAMPLE_RATE,
            enable_metrics=True,
        ),
        observers=[session.tracker.observer()],
        enable_rtvi=False,
    )
    call_pipeline = CallPipeline(worker, context, user, assistant, reply, clips)

    @worker.event_handler("on_pipeline_started")
    async def _on_started(*_: object) -> None:
        call_pipeline.started.set()

    return call_pipeline


async def greet(call: CallPipeline, session: CallSession) -> None:
    """AI + recording disclosure at call start (WORKFLOWS §2), kept in the LLM context.

    Back-channel clips for the pack's languages render in the background meanwhile; the
    first ones are needed only after the caller has talked for 3.5 s.
    """
    if isinstance(call.clips, PrerenderedClips):
        task = asyncio.create_task(call.clips.prerender(session.pack.languages))
        call.tasks.add(task)
        task.add_done_callback(call.tasks.discard)
    greeting = greeting_for(session.pack, session.call.language)
    # The client can connect before every processor has started (Sarvam sockets, Smart Turn
    # model); frames queued before StartFrame reaches them are dropped, so wait for it.
    await asyncio.wait_for(call.started.wait(), timeout=GREETING_START_TIMEOUT_S)
    await call.worker.queue_frames([TTSSpeakFrame(greeting)])
    session.add_assistant(greeting)
