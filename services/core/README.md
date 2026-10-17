# mitra-core

Core API (FastAPI): businesses, users, memberships, AI employees, contacts. Multi-tenant with
Postgres Row-Level Security. See `docs/05-TRD.md` §4, §10, §11.

## Setup

```bash
# from the repo root: start Postgres (5433), Valkey, NATS, Temporal
docker compose -f infra/docker-compose.yml up -d

cd services/core
uv sync                      # Python 3.13 + deps
cp .env.example .env         # optional; defaults already target local docker
uv run alembic upgrade head  # runs as `mitra`; also creates the `mitra_app` role
```

## Run

```bash
uv run uvicorn mitra_core.main:app --reload --port 8000
# http://localhost:8000/docs  (OpenAPI UI)   ·   /health   ·   /health/ready
```

Get a dev token (temporary HS256 auth until Better Auth, TRD §3):

```bash
uv run python scripts/dev_token.py --phone +919876543210 --name Ravi    # prints sub + token
curl -X POST localhost:8000/v1/businesses -H "Authorization: Bearer $TOKEN" \
     -H 'Content-Type: application/json' -d '{"name":"Sunrise Clinic","industry":"clinic"}'
# then mint a token scoped to the new business to use /v1/businesses/current, /v1/employees:
uv run python scripts/dev_token.py --sub <sub> --phone +919876543210 --business-id <id>
```

## Test & check

```bash
uv run pytest -q            # uses the mitra_test DB; drops & recreates its public schema
uv run ruff check . && uv run ruff format --check .
uv run mypy src
```

## Tenancy (RLS) in one paragraph

The API connects as `mitra_app` (non-superuser, `NOBYPASSRLS`). Every table has RLS enabled and
forced; policies compare `business_id` with `app_current_business_id()`, which reads the
transaction-local setting `app.business_id`. A SQLAlchemy `after_begin` hook
(`src/mitra_core/tenancy.py`) sets it at the start of every transaction from the authenticated
request, so nothing leaks across pooled connections and an unbound session sees no rows.
`POST /v1/businesses` is the only bootstrap path: it reserves a new id, switches the
transaction's tenant to it, then inserts the business and owner membership.

New tables with `business_id` must enable + force RLS, add a policy, and grant to the app role
in their migration (`tests/test_rls.py` enforces this).
