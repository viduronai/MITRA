"""Who is this phone call for? Carrier metadata -> business, employee, direction, pack.

Order: (1) a call we placed (OutboundRegistry, by carrier call id) -> outbound; (2) an
``employee_id`` custom parameter (a flow pinned to one employee); (3) core's number routing
(dialled number -> business -> employee) -> inbound; (4) env=local only: the scenario fixture,
so the simulator works without core. Outside local an unroutable call is refused.
"""

from __future__ import annotations

import base64
import hmac
import re
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal
from urllib.parse import parse_qsl

import structlog

from mitra_voice.carriers.base import OutboundIntent, OutboundRegistry
from mitra_voice.carriers.core_api import CoreTelephony, CoreTelephonyError
from mitra_voice.config import Settings
from mitra_voice.pack import Scenario

log = structlog.get_logger(__name__)

E164 = re.compile(r"^\+[1-9][0-9]{7,14}$")
SCENARIOS: tuple[Scenario, ...] = ("clinic", "real_estate")


def to_e164(raw: object) -> str | None:
    """Carrier number formats -> E.164 (India default): 09876543210, 9876543210, 919876543210."""
    if not isinstance(raw, str):
        return None
    digits = re.sub(r"[\s()-]", "", raw)
    if digits.startswith("+"):
        pass
    elif digits.startswith("0") and len(digits) == 11:
        digits = "+91" + digits[1:]
    elif len(digits) == 10:
        digits = "+91" + digits
    elif digits.startswith("91") and len(digits) == 12:
        digits = "+" + digits
    return digits if E164.fullmatch(digits) else None


def custom_params(raw: object) -> dict[str, str]:
    """Exotel sends custom parameters as a dict or a query string (max 3, 256 chars)."""
    if isinstance(raw, dict):
        return {str(k): str(v) for k, v in raw.items()}
    if isinstance(raw, str) and raw:
        return dict(parse_qsl(raw.lstrip("?")))
    return {}


def _uuid(value: str | None) -> str | None:
    try:
        return str(uuid.UUID(value or ""))
    except ValueError:
        return None


@dataclass(frozen=True, slots=True)
class CallMeta:
    carrier: Literal["exotel", "plivo"]
    call_sid: str
    stream_sid: str
    from_: str | None
    to: str | None
    custom: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class Route:
    direction: Literal["inbound", "outbound"]
    employee_id: str | None  # None = local fixture pack
    scenario: Scenario
    caller_phone: str | None  # the customer's number (E.164), for memory/reporting only
    business_id: str | None = None
    intent: OutboundIntent | None = None
    phone_number_id: str | None = None  # inbound: the business number that was dialled
    missed_call: bool = False  # CALL-20 number: hang up at once, core calls back


class RouteError(RuntimeError):
    pass


async def route_call(
    meta: CallMeta,
    *,
    settings: Settings,
    registry: OutboundRegistry,
    core: CoreTelephony | None,
) -> Route:
    scenario: Scenario = "clinic"
    if meta.custom.get("scenario") in SCENARIOS:
        scenario = meta.custom["scenario"]  # type: ignore[assignment]

    intent = registry.pop(meta.call_sid)
    if intent is not None:
        return Route(
            direction="outbound",
            employee_id=intent.employee_id,
            scenario=scenario,
            caller_phone=intent.contact_phone,
            business_id=intent.business_id,
            intent=intent,
        )

    pinned = _uuid(meta.custom.get("employee_id"))
    if pinned:
        return Route("inbound", pinned, scenario, meta.from_)

    if core is not None and meta.to:
        try:
            resolved = await core.resolve(meta.to, meta.from_)
        except CoreTelephonyError as e:
            if not settings.is_local:
                raise RouteError(str(e)) from e
            log.warning("telephony.core_unavailable", error=str(e))
            resolved = None
        if resolved is not None:
            return Route(
                "inbound",
                resolved.employee_id,
                scenario,
                meta.from_,
                resolved.business_id,
                phone_number_id=resolved.phone_number_id,
                missed_call=resolved.missed_call,
            )
        if not settings.is_local:
            raise RouteError("dialled number is not a Mitra number")

    if settings.is_local:
        return Route("inbound", None, scenario, meta.from_)
    raise RouteError("no route: core is not configured")


# ---- carrier authentication ----------------------------------------------------------------------


def exotel_authorized(headers: Mapping[str, str], settings: Settings) -> bool:
    """Exotel Voicebot basic auth: ``wss://<API_KEY>:<API_TOKEN>@host/...`` arrives as
    ``Authorization: Basic base64(key:token)``. Without configured credentials only env=local
    accepts streams (the simulator); production also allow-lists Exotel's IPs (docs)."""
    key, token = settings.exotel_api_key, settings.exotel_api_token
    if not key or token is None:
        return settings.is_local
    expected = base64.b64encode(f"{key}:{token.get_secret_value()}".encode()).decode()
    supplied = headers.get("authorization", "")
    return hmac.compare_digest(f"Basic {expected}".encode(), supplied.encode())


def plivo_stream_secret(settings: Settings) -> str | None:
    """Secret for per-call stream tokens; a fixed dev value in env=local only."""
    if settings.plivo_auth_token is not None:
        return settings.plivo_auth_token.get_secret_value()
    return "local-dev-plivo-stream-secret" if settings.is_local else None
