"""Entry point: ``uv run mitra-voice`` (or ``uv run uvicorn mitra_voice.main:app --port 8200``)."""

from __future__ import annotations

import uvicorn

from mitra_voice.app import create_app
from mitra_voice.config import get_settings

app = create_app()


def run() -> None:
    settings = get_settings()
    uvicorn.run(app, host=settings.host, port=settings.port, log_config=None)


if __name__ == "__main__":
    run()
