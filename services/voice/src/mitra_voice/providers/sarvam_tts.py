"""Sarvam streaming TTS: stock Bulbul speakers and team-member clones, both metered.

Team clones do not go through Bulbul's ``speaker`` field: Sarvam serves them on a separate beta
websocket, ``wss://api.sarvam.ai/voices/clone/ws``
(https://docs.sarvam.ai/api-reference/voice-cloning/clone-ws.md). It uses the same message
protocol as the Bulbul websocket (``config`` once, then ``text``/``flush``/``ping``; ``audio``
chunks and a ``final`` event back), but its config takes ``voice_id`` (``svc-…``) and no
``speaker``/``model``. Billing is per character, like Bulbul (₹30 per 10K).
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from typing import Any

from pipecat.frames.frames import Frame
from pipecat.services.sarvam.tts import SarvamTTSService

from mitra_voice.usage import UsageMeter

CLONE_WS_URL = "wss://api.sarvam.ai/voices/clone/ws"


class MeteredSarvamTTSService(SarvamTTSService):
    """Bulbul streaming TTS that counts the characters it sends (billed)."""

    def __init__(self, *, usage: UsageMeter | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._usage = usage

    async def run_tts(self, text: str, context_id: str) -> AsyncGenerator[Frame | None]:
        if self._usage is not None:
            self._usage.add_tts_live(len(text))
        async for frame in super().run_tts(text, context_id):
            yield frame


class SarvamCloneTTSService(MeteredSarvamTTSService):
    """Streaming TTS in a consented team-member clone (Instant Voice Cloning websocket)."""

    def __init__(self, *, voice_id: str, **kwargs: Any) -> None:
        if not voice_id.startswith("svc-"):
            raise ValueError("a clone voice id starts with 'svc-'")
        super().__init__(url=CLONE_WS_URL, **kwargs)
        # No model query parameter on the clone endpoint.
        self._websocket_url = f"{CLONE_WS_URL}?send_completion_event=true"
        self._clone_voice_id = voice_id

    def clone_config(self) -> dict[str, Any]:
        settings: Any = self._settings
        max_chunk = settings.max_chunk_length
        return {
            "target_language_code": settings.language,
            "voice_id": self._clone_voice_id,
            "speech_sample_rate": self._speech_sample_rate,
            "min_buffer_size": settings.min_buffer_size,
            # Clone endpoint range is 50-500 (Bulbul's default 150 fits).
            "max_chunk_length": max(50, int(max_chunk)) if isinstance(max_chunk, int) else 100,
            "output_audio_codec": "linear16",  # the endpoint defaults to mp3
            "pace": settings.pace,
        }

    async def _send_config(self) -> None:
        if not self._websocket:
            raise RuntimeError("WebSocket not connected")
        await self._websocket.send(json.dumps({"type": "config", "data": self.clone_config()}))
