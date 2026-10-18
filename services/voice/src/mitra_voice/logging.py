"""Structured JSON logging (structlog) plus Pipecat's loguru output routed to stderr.

Never log phone numbers, tokens or keys. Transcript text must pass through ``redact_phones``
before it reaches a log line; a processor also masks well-known sensitive keys as a safety net.
"""

from __future__ import annotations

import logging
import re
import sys
from collections.abc import MutableMapping
from typing import Any

import structlog
from loguru import logger as loguru_logger

_SENSITIVE_KEYS = frozenset(
    {"authorization", "token", "api_key", "key", "secret", "phone", "phone_e164", "password"}
)

# Digit runs that look like phone numbers: +91 98765 43210, 098765-43210, 9876543210, 040 2345 6789.
# Seven or more digits, optionally separated by single spaces, dots or dashes.
_PHONE_RE = re.compile(r"(?<![\w])\+?\d(?:[\s.\-]?\d){6,}(?![\w])")


def redact_phones(text: str) -> str:
    """Mask anything that looks like a phone number: ``call 98765 43210`` -> ``call [phone]``."""
    return _PHONE_RE.sub("[phone]", text)


def _redact(_: Any, __: str, event_dict: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
    for key in event_dict.keys() & _SENSITIVE_KEYS:
        event_dict[key] = "[REDACTED]"
    for key in ("text", "transcript", "heard"):
        value = event_dict.get(key)
        if isinstance(value, str):
            event_dict[key] = redact_phones(value)
    return event_dict


def configure_logging(level: str = "INFO", pipecat_level: str = "WARNING") -> None:
    shared: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        _redact,
    ]
    structlog.configure(
        processors=[
            *shared,
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(ensure_ascii=False),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level.upper())),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared,
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                structlog.processors.JSONRenderer(ensure_ascii=False),
            ],
        )
    )
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())

    # Pipecat logs via loguru; keep it, but quieter, and never with message bodies at DEBUG
    # in non-local envs (it logs LLM contexts and TTS text at DEBUG).
    loguru_logger.remove()
    loguru_logger.add(sys.stderr, level=pipecat_level.upper(), backtrace=False, diagnose=False)
