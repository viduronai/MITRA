"""Dialer settings (env prefix ``MITRA_DIALER_``), kept apart from the shared ``config.py``."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class DialerSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MITRA_DIALER_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # "sim": calls are simulated in-process (no carrier, no voice service): outcomes are
    # deterministic per number. "voice": calls go to the voice service's carrier path.
    mode: Literal["sim", "voice"] = "sim"
    voice_url: str = "http://localhost:8001"
    # Seconds between worker ticks (``python -m mitra_core.dialer.run``).
    interval_s: float = 5.0
    default_channels: int = 5
    # A placed call with no outcome after this many minutes is treated as unanswered.
    dial_timeout_min: int = 20
    # Consecutive carrier rejections / spam flags before a campaign auto-pauses (CALL-16).
    strike_limit: int = 3
    max_contacts: int = 5000


@lru_cache
def get_dialer_settings() -> DialerSettings:
    return DialerSettings()
