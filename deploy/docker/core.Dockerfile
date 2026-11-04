# Mitra core API + scheduler + migrations (one image, three commands; see deploy/compose.yml).
# Build from the repo root:  docker build -f deploy/docker/core.Dockerfile -t mitra-core .
FROM python:3.13-slim-bookworm AS build
COPY --from=ghcr.io/astral-sh/uv:0.11.28 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
# Dependencies first (cached until the lockfile changes), then the project itself.
COPY services/core/pyproject.toml services/core/uv.lock services/core/README.md ./
RUN uv sync --frozen --no-dev --extra aws --no-install-project
COPY services/core/src ./src
COPY services/core/alembic ./alembic
COPY services/core/alembic.ini ./
RUN uv sync --frozen --no-dev --extra aws --no-editable

FROM python:3.13-slim-bookworm
RUN useradd --system --uid 10001 --home /app mitra
WORKDIR /app
COPY --from=build --chown=mitra:mitra /app /app
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
USER mitra
EXPOSE 8000
# Behind Caddy on a private network: trust its X-Forwarded-For so rate limits see the visitor.
CMD ["uvicorn", "mitra_core.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]
