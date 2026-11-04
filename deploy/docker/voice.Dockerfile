# Mitra voice service (Pipecat). Build from the repo root:
#   docker build -f deploy/docker/voice.Dockerfile -t mitra-voice .
FROM python:3.13-slim-bookworm AS build
COPY --from=ghcr.io/astral-sh/uv:0.11.28 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app/services/voice
# The voice service depends on libs/mitra-human by path, so keep the repo layout.
COPY libs/mitra-human /app/libs/mitra-human
COPY services/voice/pyproject.toml services/voice/uv.lock services/voice/README.md ./
RUN uv sync --frozen --no-dev --no-install-project --no-editable
COPY services/voice/src ./src
RUN uv sync --frozen --no-dev --no-editable

FROM python:3.13-slim-bookworm
RUN useradd --system --uid 10001 --home /app mitra
WORKDIR /app
COPY --from=build --chown=mitra:mitra /app/services/voice/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 HOST=0.0.0.0
USER mitra
EXPOSE 8200
CMD ["mitra-voice"]
