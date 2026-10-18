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

Log in with a dev OTP (env=local returns the code as `dev_code`; nothing is sent by SMS yet):

```bash
curl -X POST localhost:8000/v1/auth/otp/request -H 'Content-Type: application/json'      -d '{"phone":"+919876543210"}'                 # -> {request_id, dev_code, ...}
curl -X POST localhost:8000/v1/auth/otp/verify -H 'Content-Type: application/json'      -d '{"request_id":"<id>","code":"<dev_code>","name":"Ravi"}'   # -> {access_token, ...}
curl -X POST localhost:8000/v1/businesses -H "Authorization: Bearer $TOKEN"      -H 'Content-Type: application/json' -d '{"name":"Sunrise Clinic","industry":"clinic"}'
# the response's access_token is scoped to the new business; use it for everything below
```

Limits: 6-digit code, valid 5 min, 5 attempts per code, 3 requests per phone per 10 min.
Tokens are HS256 signed by this API for now (Better Auth / JWKS later, TRD §3).
`scripts/dev_token.py` still mints tokens directly for quick experiments.

## Endpoints (Step 2 onboarding; contract: `docs/api/step2-onboarding-contract.md`)

| Area | Endpoints |
|---|---|
| Auth | `POST /v1/auth/otp/request`, `POST /v1/auth/otp/verify`, `POST /v1/auth/switch-business` |
| Catalog (public) | `GET /v1/catalog/role-templates`, `GET /v1/catalog/voices?language=te`, `GET /v1/catalog/rates` |
| Knowledge | `POST/GET /v1/knowledge/sources`, `GET/POST /v1/knowledge/facts`, `PATCH/DELETE /v1/knowledge/facts/{id}`, `GET /v1/knowledge/gaps` |
| Employees | `PATCH /v1/employees/{id}` also takes `voice_id`, `greeting`, `behaviour` |
| Test calls (simulated) | `POST /v1/test-calls`, `GET /v1/test-calls/{id}`, `POST /v1/test-calls/{id}/corrections` |
| Onboarding | `GET /v1/onboarding/progress` |

URL sources are fetched in a background task through an SSRF guard
(`src/mitra_core/knowledge/fetch.py`: public IPs only, re-checked on each of max 3 redirects,
connection pinned to the vetted IP, 10 s, 2 MB). Fact extraction is deterministic for now
(`knowledge/extract.py`, replaced by LLM extraction in Step 3). Test calls dial nothing: status
advances about every 2 s and the transcript is scripted from confirmed facts. CORS allows
`localhost:3000` / `localhost:3100` in env=local only.

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

`otp_request` is the exception: it is pre-auth (no business or user yet), so the app role has
no privileges on it at all. It is reached only via the `auth_otp_issue` / `auth_otp_verify`
SECURITY DEFINER functions (EXECUTE granted to the app role only, `search_path` pinned); RLS is
still forced, with policies scoped to the owning role only. See migration `0002_onboarding`.
