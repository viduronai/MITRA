"""Carrier simulator: a phone caller speaking Exotel's (or Plivo's) media-stream protocol.

It connects to ``/telephony/<carrier>/ws`` exactly like the carrier would (Exotel: ``connected``
then ``start`` with call/stream sids, from/to and custom parameters, then 8 kHz 16-bit PCM
``media`` chunks; Plivo: ``start`` then mu-law ``media``), streams silence until the greeting has
played, speaks a WAV, then listens until the reply has played. Everything the service sends back
is recorded: the reply audio (saved as WAV) and control events (``clear`` on barge-in, ``mark``).
With ``barge_in=True`` the caller talks over the greeting, which must make the service ``clear``.

CLI (the service must be running)::

    uv run python -m mitra_voice.carriers.simulator --url ws://127.0.0.1:8213/telephony/exotel/ws \
        --wav caller.wav --out reply.wav --from +919812345678 --to +914041234567
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import contextlib
import json
import time
import uuid
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import numpy as np
import websockets

Protocol = Literal["exotel", "plivo"]
RATE = 8000


def load_wav_8k(path: Path) -> bytes:
    """Any mono/stereo 16-bit WAV -> mono 16-bit PCM at 8 kHz (linear resampling)."""
    with wave.open(str(path), "rb") as w:
        if w.getsampwidth() != 2:
            raise ValueError("caller WAV must be 16-bit PCM")
        rate, channels = w.getframerate(), w.getnchannels()
        samples = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float64)
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)
    if rate != RATE:
        n = int(len(samples) * RATE / rate)
        samples = np.interp(np.linspace(0, len(samples) - 1, n), np.arange(len(samples)), samples)
    return bytes(np.clip(samples, -32768, 32767).astype("<i2").tobytes())


def save_wav(path: Path, pcm: bytes, rate: int = RATE) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)


async def simulate_missed_call(
    base_url: str,
    *,
    from_: str,
    to: str,
    carrier: Protocol = "exotel",
    headers: dict[str, str] | None = None,
) -> int:
    """A caller rings a missed-call number and the carrier never answers (CALL-20).

    Exotel: the flow's Passthru applet GETs ``/telephony/exotel/missed-call``. Plivo: the answer
    URL is asked first and must reply ``<Hangup reason="rejected"/>`` (no stream is opened).
    Returns the HTTP status; for Plivo, 200 only if the call was rejected.
    """
    import httpx

    sid = "SIMMISS" + uuid.uuid4().hex[:24]
    async with httpx.AsyncClient(base_url=base_url, headers=headers or {}) as client:
        if carrier == "exotel":
            res = await client.get(
                "/telephony/exotel/missed-call",
                params={"CallSid": sid, "CallFrom": from_, "CallTo": to},
            )
            return res.status_code
        res = await client.post(
            "/telephony/plivo/answer", data={"CallUUID": sid, "From": from_, "To": to}
        )
        rejected = res.status_code == 200 and 'Hangup reason="rejected"' in res.text
        return 200 if rejected else 409


# ---- G.711 mu-law (Plivo) ------------------------------------------------------------------------

_BIAS, _CLIP = 0x84, 32635


def pcm_to_ulaw(pcm: bytes) -> bytes:
    x = np.frombuffer(pcm, dtype="<i2").astype(np.int32)
    sign = np.where(x < 0, 0x80, 0)
    x = np.minimum(np.abs(x), _CLIP) + _BIAS
    exponent = np.floor(np.log2(x)).astype(np.int32) - 7
    exponent = np.clip(exponent, 0, 7)
    mantissa = (x >> (exponent + 3)) & 0x0F
    return bytes((~(sign | (exponent << 4) | mantissa) & 0xFF).astype(np.uint8).tobytes())


def ulaw_to_pcm(data: bytes) -> bytes:
    u = ~np.frombuffer(data, dtype=np.uint8).astype(np.int32) & 0xFF
    sign, exponent, mantissa = u & 0x80, (u >> 4) & 0x07, u & 0x0F
    x = (((mantissa << 3) + _BIAS) << exponent) - _BIAS
    return bytes(np.where(sign != 0, -x, x).astype("<i2").tobytes())


# ---- the caller ---------------------------------------------------------------------------------


@dataclass
class SimulatedCall:
    call_sid: str
    stream_sid: str
    reply_pcm: bytearray = field(default_factory=bytearray)  # everything played to the caller
    events: list[dict[str, Any]] = field(default_factory=list)  # non-media messages received
    greeting_bytes: int = 0  # audio received before the caller spoke
    first_audio_s: float | None = None  # connect -> first audio from the service
    closed_by_service: bool = False

    @property
    def clears(self) -> int:
        return sum(1 for e in self.events if e.get("event") in ("clear", "clearAudio"))

    @property
    def reply_bytes(self) -> int:
        return len(self.reply_pcm) - self.greeting_bytes

    def seconds(self, nbytes: int | None = None) -> float:
        return (len(self.reply_pcm) if nbytes is None else nbytes) / 2 / RATE


class _Listener:
    def __init__(self, call: SimulatedCall, protocol: Protocol, started: float) -> None:
        self.call, self.protocol, self.started = call, protocol, started
        self.last_audio = 0.0

    def quiet_for(self, seconds: float) -> bool:
        return bool(self.call.reply_pcm) and time.monotonic() - self.last_audio >= seconds

    async def run(self, ws: Any) -> None:
        try:
            async for raw in ws:
                msg = json.loads(raw)
                event = msg.get("event")
                if event in ("media", "playAudio"):
                    payload = base64.b64decode(msg["media"]["payload"])
                    pcm = ulaw_to_pcm(payload) if self.protocol == "plivo" else payload
                    self.call.reply_pcm.extend(pcm)
                    self.last_audio = time.monotonic()
                    if self.call.first_audio_s is None:
                        self.call.first_audio_s = self.last_audio - self.started
                else:
                    self.call.events.append(msg)
                    if event == "mark":  # Exotel echoes a mark once the audio before it played
                        await ws.send(json.dumps(msg))
        except websockets.ConnectionClosed:
            pass
        self.call.closed_by_service = True


def _start_messages(
    protocol: Protocol,
    call: SimulatedCall,
    from_: str,
    to: str,
    account_sid: str,
    custom: dict[str, str] | None,
) -> list[dict[str, Any]]:
    if protocol == "plivo":
        return [
            {
                "event": "start",
                "sequenceNumber": 0,
                "start": {
                    "callId": call.call_sid,
                    "streamId": call.stream_sid,
                    "accountId": account_sid,
                    "tracks": ["inbound"],
                    "mediaFormat": {"encoding": "audio/x-mulaw", "sampleRate": RATE},
                },
            }
        ]
    return [
        {"event": "connected"},
        {
            "event": "start",
            "sequence_number": 1,
            "stream_sid": call.stream_sid,
            "start": {
                "stream_sid": call.stream_sid,
                "call_sid": call.call_sid,
                "account_sid": account_sid,
                "from": from_,
                "to": to,
                "custom_parameters": custom or {},
                "media_format": {
                    "encoding": "base64",
                    "sample_rate": str(RATE),
                    "bit_rate": "128kbps",
                },
            },
        },
    ]


def _media(protocol: Protocol, call: SimulatedCall, seq: int, chunk: int, pcm: bytes) -> str:
    if protocol == "plivo":
        payload = base64.b64encode(pcm_to_ulaw(pcm)).decode()
        return json.dumps(
            {
                "event": "media",
                "sequenceNumber": seq,
                "streamId": call.stream_sid,
                "media": {"track": "inbound", "timestamp": str(chunk * 20), "payload": payload},
            }
        )
    return json.dumps(
        {
            "event": "media",
            "sequence_number": seq,
            "stream_sid": call.stream_sid,
            "media": {
                "chunk": chunk,
                "timestamp": str(chunk * 20),
                "payload": base64.b64encode(pcm).decode(),
            },
        }
    )


async def simulate_call(
    url: str,
    caller_pcm: bytes,
    *,
    protocol: Protocol = "exotel",
    from_: str = "+919812345678",
    to: str = "+914041234567",
    call_sid: str | None = None,
    account_sid: str = "ACsimulator",
    custom_parameters: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
    barge_in: bool = False,
    quiet_s: float = 1.0,
    greeting_timeout_s: float = 20.0,
    reply_timeout_s: float = 20.0,
    chunk_ms: int = 20,
) -> SimulatedCall:
    """One call: wait for the greeting, say ``caller_pcm`` (8 kHz PCM), wait for the reply."""
    call = SimulatedCall(
        call_sid=call_sid or uuid.uuid4().hex, stream_sid="ST" + uuid.uuid4().hex[:30]
    )
    step = RATE * chunk_ms // 1000 * 2
    silence = bytes(step)
    seq = chunk = 0
    async with websockets.connect(url, additional_headers=headers or {}, max_size=2**22) as ws:
        listener = _Listener(call, protocol, time.monotonic())
        listen = asyncio.create_task(listener.run(ws))

        async def send(pcm: bytes) -> None:
            nonlocal seq, chunk
            seq, chunk = seq + 1, chunk + 1
            await ws.send(_media(protocol, call, seq, chunk, pcm))
            await asyncio.sleep(chunk_ms / 1000)

        async def until(done: Any, timeout_s: float) -> None:
            deadline = time.monotonic() + timeout_s
            while not done() and time.monotonic() < deadline and not call.closed_by_service:
                await send(silence)

        try:
            for msg in _start_messages(protocol, call, from_, to, account_sid, custom_parameters):
                await ws.send(json.dumps(msg))
            if barge_in:  # talk over the greeting once ~0.6 s of it has arrived
                await until(lambda: call.seconds() > 0.6, greeting_timeout_s)
            else:
                await until(lambda: listener.quiet_for(quiet_s), greeting_timeout_s)
            call.greeting_bytes = len(call.reply_pcm)
            for i in range(0, len(caller_pcm), step):
                await send(caller_pcm[i : i + step].ljust(step, b"\0"))
            spoke_at = len(call.reply_pcm)
            await until(
                lambda: len(call.reply_pcm) > spoke_at and listener.quiet_for(quiet_s),
                reply_timeout_s,
            )
            if not call.closed_by_service:
                stop = {
                    "event": "stop",
                    "stream_sid": call.stream_sid,
                    "stop": {"reason": "hangup"},
                }
                with contextlib.suppress(websockets.ConnectionClosed):
                    await ws.send(json.dumps(stop))
        finally:
            await ws.close()
            listen.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await listen
    return call


def basic_auth(user: str, password: str) -> dict[str, str]:
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def main() -> None:  # pragma: no cover - manual tool
    parser = argparse.ArgumentParser(description="Call the voice service like a carrier would.")
    parser.add_argument("--url", required=True)
    parser.add_argument("--wav", type=Path, required=True, help="what the caller says")
    parser.add_argument("--out", type=Path, default=Path("reply.wav"))
    parser.add_argument("--protocol", choices=["exotel", "plivo"], default="exotel")
    parser.add_argument("--from", dest="from_", default="+919812345678")
    parser.add_argument("--to", default="+914041234567")
    parser.add_argument("--user", help="Exotel basic-auth user (EXOTEL_API_KEY)")
    parser.add_argument("--password", help="Exotel basic-auth password (EXOTEL_API_TOKEN)")
    parser.add_argument("--barge-in", action="store_true")
    args = parser.parse_args()
    headers = basic_auth(args.user, args.password) if args.user and args.password else None
    call = asyncio.run(
        simulate_call(
            args.url,
            load_wav_8k(args.wav),
            protocol=args.protocol,
            from_=args.from_,
            to=args.to,
            headers=headers,
            barge_in=args.barge_in,
        )
    )
    save_wav(args.out, bytes(call.reply_pcm))
    summary = {
        "call_sid": call.call_sid,
        "first_audio_s": round(call.first_audio_s or 0, 2),
        "greeting_s": round(call.seconds(call.greeting_bytes), 2),
        "reply_s": round(call.seconds(call.reply_bytes), 2),
        "clears": call.clears,
        "events": [e.get("event") for e in call.events],
        "out": str(args.out),
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":  # pragma: no cover
    main()
