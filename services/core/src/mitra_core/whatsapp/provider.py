"""WhatsApp providers: the simulator (default) and Meta WhatsApp Cloud API.

A provider only transports; the 24-hour window, template choice, storage, recipients and
dedupe live in ``outbox.py`` / ``service.py``. Both providers build the request body with the
same functions (``template_body``, ``buttons_body``), so the simulator rejects exactly what Meta
would reject for shape (unknown template, missing parameter, button mismatch) and the tests
cover the real payloads.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from mitra_core.config import Settings, get_settings
from mitra_core.logging import get_logger
from mitra_core.whatsapp.templates import Lang, TemplateError, spec

log = get_logger(__name__)

GRAPH_URL = "https://graph.facebook.com/v21.0"
MAX_BUTTONS = 3  # WhatsApp reply-button limit
MAX_BUTTON_TITLE = 20
MAX_INTERACTIVE_BODY = 1024
MAX_TEXT_BODY = 4096
MAX_PAYLOAD = 256


@dataclass(frozen=True, slots=True)
class Button:
    id: str
    title: str


@dataclass(frozen=True, slots=True)
class Document:
    link: str
    filename: str


@dataclass(frozen=True, slots=True)
class TemplateMessage:
    """One approved template with NAMED parameters (already flattened by ``templates.prepare``).

    ``payloads`` fill the template's quick-reply buttons in order (e.g. approval id + version);
    ``url_suffix`` fills its dynamic URL button; ``document`` its document header.
    """

    name: str
    language: Lang
    params: dict[str, str]
    payloads: list[str] = field(default_factory=list)
    url_suffix: str | None = None
    document: Document | None = None


@dataclass(frozen=True, slots=True)
class SendResult:
    ok: bool
    message_id: str | None = None
    error: str | None = None


def _header(msg: TemplateMessage) -> dict[str, Any]:
    if msg.document is None:
        raise TemplateError(f"{msg.name}: a document is required")
    doc = {"link": msg.document.link, "filename": msg.document.filename}
    return {"type": "header", "parameters": [{"type": "document", "document": doc}]}


def template_body(msg: TemplateMessage) -> dict[str, Any]:
    """The ``template`` object of a Cloud API message (named parameters, buttons, header)."""
    s = spec(msg.name)
    if msg.language not in s.bodies:
        raise TemplateError(f"{msg.name}: no {msg.language} version")
    if list(msg.params) != list(s.params):
        raise TemplateError(f"{msg.name}: parameters must be {', '.join(s.params)}")
    quick_count = len(s.quick_replies)
    if msg.payloads and len(msg.payloads) != quick_count:
        raise TemplateError(f"{msg.name}: {quick_count} quick-reply payloads expected")
    components: list[dict[str, Any]] = [_header(msg)] if s.header == "document" else []
    components.append(
        {
            "type": "body",
            "parameters": [
                {"type": "text", "parameter_name": name, "text": value}
                for name, value in msg.params.items()
            ],
        }
    )
    quick = iter(msg.payloads)
    for index, button in enumerate(s.buttons):
        if button.kind == "quick_reply" and msg.payloads:
            components.append(
                {
                    "type": "button",
                    "sub_type": "quick_reply",
                    "index": str(index),
                    "parameters": [{"type": "payload", "payload": next(quick)[:MAX_PAYLOAD]}],
                }
            )
        elif button.kind == "url" and button.dynamic:
            if not msg.url_suffix:
                raise TemplateError(f"{msg.name}: the {button.title!r} link needs a url_suffix")
            components.append(
                {
                    "type": "button",
                    "sub_type": "url",
                    "index": str(index),
                    "parameters": [{"type": "text", "text": msg.url_suffix}],
                }
            )
    return {
        "name": msg.name,
        "language": {"code": msg.language},
        "parameter_format": "NAMED",
        "components": components,
    }


def buttons_body(text: str, buttons: list[Button]) -> dict[str, Any]:
    """Interactive reply buttons (free-form, inside the 24-hour window only)."""
    if not 1 <= len(buttons) <= MAX_BUTTONS:
        raise ValueError(f"1 to {MAX_BUTTONS} reply buttons")
    return {
        "type": "button",
        "body": {"text": text[:MAX_INTERACTIVE_BODY]},
        "action": {
            "buttons": [
                {
                    "type": "reply",
                    "reply": {"id": b.id[:MAX_PAYLOAD], "title": b.title[:MAX_BUTTON_TITLE]},
                }
                for b in buttons
            ]
        },
    }


class WhatsAppProvider(Protocol):
    name: str

    async def send_text(self, to: str, text: str) -> SendResult: ...

    async def send_template(self, to: str, message: TemplateMessage) -> SendResult: ...

    async def send_buttons(self, to: str, text: str, buttons: list[Button]) -> SendResult: ...


class SimulatorProvider:
    """Sends nothing; validates shapes like Meta would, then accepts. Rows are the 'phone'."""

    name = "sim"

    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []  # recent request bodies, for tests

    def _ok(self, body: dict[str, Any]) -> SendResult:
        self.sent = [*self.sent[-49:], body]
        return SendResult(ok=True, message_id=f"sim-{uuid.uuid4().hex}")

    async def send_text(self, to: str, text: str) -> SendResult:
        return self._ok({"type": "text", "text": {"body": text[:MAX_TEXT_BODY]}})

    async def send_template(self, to: str, message: TemplateMessage) -> SendResult:
        return self._ok({"type": "template", "template": template_body(message)})

    async def send_buttons(self, to: str, text: str, buttons: list[Button]) -> SendResult:
        return self._ok({"type": "interactive", "interactive": buttons_body(text, buttons)})


class CloudApiProvider:
    """Meta WhatsApp Cloud API (``POST /{phone_number_id}/messages``).

    Mitra talks to Meta directly (no BSP; founder decision, 3 Nov 2026). Templates are listed in
    ``templates.py`` (submitted per language in WhatsApp Manager); the 24-hour window is decided
    in ``outbox.py``. TODO(whatsapp): media download for voice notes (GET /{media_id}) and
    delivery-status webhooks into ``wa_message.status``.
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

    async def send_template(self, to: str, message: TemplateMessage) -> SendResult:
        return await self._post(to, {"type": "template", "template": template_body(message)})

    async def send_buttons(self, to: str, text: str, buttons: list[Button]) -> SendResult:
        return await self._post(
            to, {"type": "interactive", "interactive": buttons_body(text, buttons)}
        )


_override: WhatsAppProvider | None = None
_simulator = SimulatorProvider()


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
    return _simulator
