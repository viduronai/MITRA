"""Carrier adapters (``sim``, ``exotel``, ``plivo``) for outbound calls. See docs/telephony.md."""

from __future__ import annotations

from mitra_voice.carriers.base import (
    Carrier,
    CarrierError,
    CarrierName,
    OutboundIntent,
    OutboundRegistry,
    PlacedCall,
)
from mitra_voice.carriers.exotel import ExotelCarrier
from mitra_voice.carriers.plivo import PlivoCarrier
from mitra_voice.carriers.sim import SimCarrier
from mitra_voice.config import Settings

__all__ = [
    "Carrier",
    "CarrierError",
    "CarrierName",
    "ExotelCarrier",
    "OutboundIntent",
    "OutboundRegistry",
    "PlacedCall",
    "PlivoCarrier",
    "SimCarrier",
    "make_carrier",
    "make_fallback",
]


def _public(settings: Settings, path: str) -> str | None:
    base = settings.mitra_public_base_url
    return f"{base.rstrip('/')}{path}" if base else None


def make_carrier(settings: Settings, name: CarrierName | None = None) -> Carrier:
    """The configured carrier; raises ``ValueError`` naming the missing setting (never values)."""
    name = name or settings.mitra_telephony_carrier
    if name == "sim":
        return SimCarrier()
    if name == "exotel":
        missing = [
            k
            for k in ("exotel_account_sid", "exotel_api_key", "exotel_api_token", "exotel_app_id")
            if not getattr(settings, k)
        ]
        if missing:
            raise ValueError(f"exotel needs {', '.join(m.upper() for m in missing)}")
        assert settings.exotel_api_token is not None  # noqa: S101 (checked above)
        return ExotelCarrier(
            account_sid=settings.exotel_account_sid or "",
            api_key=settings.exotel_api_key or "",
            api_token=settings.exotel_api_token.get_secret_value(),
            app_id=settings.exotel_app_id or "",
            subdomain=settings.exotel_subdomain,
            status_callback=_public(settings, "/telephony/exotel/status"),
        )
    answer_url = _public(settings, "/telephony/plivo/answer")
    if not (settings.plivo_auth_id and settings.plivo_auth_token and answer_url):
        raise ValueError("plivo needs PLIVO_AUTH_ID, PLIVO_AUTH_TOKEN and MITRA_PUBLIC_BASE_URL")
    return PlivoCarrier(
        auth_id=settings.plivo_auth_id,
        auth_token=settings.plivo_auth_token.get_secret_value(),
        answer_url=answer_url,
    )


def make_fallback(settings: Settings) -> Carrier | None:
    """Secondary carrier for outages (WORKFLOWS section 12): Plivo behind Exotel, if configured."""
    if settings.mitra_telephony_carrier == "exotel" and settings.plivo_auth_id:
        try:
            return make_carrier(settings, "plivo")
        except ValueError:
            return None
    return None
