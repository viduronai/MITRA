"""WhatsApp providers: the simulator (default) and a Meta WhatsApp Cloud API implementation.

A provider only transports; storing messages, picking recipients and dedupe live in
``service.py``. The simulator accepts everything and returns a fake id, so the rest of the
system (alerts, approvals, reports) runs end to end without a WhatsApp Business account.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from mitra_core.config import Settings, get_settings
from mitra_core.logging import get_logger

log = get_logger(__name__)

GRAPH_URL = "https://graph.facebook.com/v21.0"
MAX_BUTTONS = 3  # WhatsApp reply-button limit
MAX_BUTTON_TITLE = 20
MAX_INTERACTIVE_BODY = 1024
MAX_TEXT_BODY = 4096


@dataclass(frozen=True, slots=True)
class Button:
    id: str
    title: str


@dataclass(frozen=True, slots=True)
class SendResult:
    ok: bool
    message_id: str | None = None
    error: str | None = None


class WhatsAppProvider(Protocol):
    name: str

    async def send_text(self, to: str, text: str) -> SendResult: ...

    async def send_template(
        self, to: str, template: str, language: str, params: list[str]
    ) -> SendResult: ...

    async def send_buttons(self, to: str, text: str, buttons: list[Button]) -> SendResult: ...


class SimulatorProvider:
    """Sends nothing; every message is accepted. The stored rows are the 'phone'."""

    name = "sim"

    async def send_text(self, to: str, text: str) -> SendResult:
        return SendResult(ok=True, message_id=f"sim-{uuid.uuid4().hex}")

    async def send_template(
        self, to: str, template: str, language: str, params: list[str]
    ) -> SendResult:
        return SendResult(ok=True, message_id=f"sim-{uuid.uuid4().hex}")

    async def send_buttons(self, to: str, text: str, buttons: list[Button]) -> SendResult:
        return SendResult(ok=True, message_id=f"sim-{uuid.uuid4().hex}")


class CloudApiProvider:
    """Meta WhatsApp Cloud API (``POST /{phone_number_id}/messages``).

    TODO(whatsapp): BSP choice (TRD open question 4), template registration per language, the
    24-hour customer-service window (free-form text only inside it; templates outside it), and
    media download for voice notes.
    """

    name = "cloud"

    def __init__(
        self,
        token: str,
        phone_number_id: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout_s: float = 10.0,
    ) -> None:
        self._url = f"{GRAPH_URL}/{phone_number_id}/messages"
        self._token = token
        self._transport = transport
        self._timeout = timeout_s

    async def _post(self, to: str, body: dict[str, Any]) -> SendResult:
        payload = {"messaging_product": "whatsapp", "to": to.lstrip("+"), **body}
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout, transport=self._transport
            ) as client:
                res = await client.post(
                    self._url, json=payload, headers={"Authorization": f"Bearer {self._token}"}
                )
            res.raise_for_status()
            messages = res.json().get("messages") or [{}]
            return SendResult(ok=True, message_id=str(messages[0].get("id") or "") or None)
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("whatsapp.send_failed", error=type(exc).__name__)
            return SendResult(ok=False, error=type(exc).__name__)

    async def send_text(self, to: str, text: str) -> SendResult:
        return await self._post(to, {"type": "text", "text": {"body": text[:MAX_TEXT_BODY]}})

    async def send_template(
        self, to: str, template: str, language: str, params: list[str]
    ) -> SendResult:
        components = (
            [{"type": "body", "parameters": [{"type": "text", "text": p} for p in params]}]
            if params
            else []
        )
        return await self._post(
            to,
            {
                "type": "template",
                "template": {
                    "name": template,
                    "language": {"code": language},
                    "components": components,
                },
            },
        )

    async def send_buttons(self, to: str, text: str, buttons: list[Button]) -> SendResult:
        return await self._post(
            to,
            {
                "type": "interactive",
                "interactive": {
                    "type": "button",
                    "body": {"text": text[:MAX_INTERACTIVE_BODY]},
                    "action": {
                        "buttons": [
                            {
                                "type": "reply",
                                "reply": {"id": b.id, "title": b.title[:MAX_BUTTON_TITLE]},
                            }
                            for b in buttons[:MAX_BUTTONS]
                        ]
                    },
                },
            },
        )


_override: WhatsAppProvider | None = None


def set_provider(provider: WhatsAppProvider | None) -> None:
    """Tests (and scripts) can swap the provider; ``None`` restores the configured one."""
    global _override
    _override = provider


def get_provider(settings: Settings | None = None) -> WhatsAppProvider:
    if _override is not None:
        return _override
    settings = settings or get_settings()
    if settings.whatsapp_provider == "cloud":
        token = settings.whatsapp_token.get_secret_value()
        if token and settings.whatsapp_phone_number_id:
            return CloudApiProvider(token, settings.whatsapp_phone_number_id)
        log.warning("whatsapp.cloud_not_configured")
    return SimulatorProvider()
