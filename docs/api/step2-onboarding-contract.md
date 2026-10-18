# Step 2 API contract: auth + onboarding

Shared contract between `services/core` (API, port **8000**) and `apps/web` (app, port **3000**). Both sides build against this file. If either side needs a change, update this file first and tell the other agent.

Conventions (already in Step 1): base path `/v1`; JSON; error shape `{"error": {"code", "message", "details"}}`; `Authorization: Bearer <jwt>`; UUIDs as strings; timestamps ISO-8601 UTC; `Idempotency-Key` header supported on create endpoints.

## 1. Auth (dev OTP; real SMS/WhatsApp OTP provider comes later)

| Method & path | Body | Response |
|---|---|---|
| `POST /v1/auth/otp/request` | `{ "phone": "+919876543210" }` (E.164, India `+91` only for now) | `202 { "request_id", "expires_in": 300, "resend_in": 30, "dev_code"? }`. `dev_code` is present **only when env=local**. |
| `POST /v1/auth/otp/verify` | `{ "request_id", "code": "123456", "name"? }` | `200 { "access_token", "token_type": "bearer", "expires_in", "user": {id, phone_last4, name, preferred_locale}, "memberships": [{business_id, business_name, role}] }`. The token is scoped to the first membership's business if one exists, otherwise unscoped. |
| `POST /v1/auth/switch-business` | `{ "business_id" }` | `200 { "access_token", ... }` scoped to that business (caller must be a member) |
| `POST /v1/businesses` (existing) | existing body | **Add** `access_token` (scoped to the new business) to the response |

Rules: 6-digit code; max 5 attempts per request; max 3 requests per phone per 10 min (429 `rate_limited`); codes stored hashed; never log codes.

## 2. Catalog (static data in code for now)

| Method & path | Response |
|---|---|
| `GET /v1/catalog/role-templates` | `[{ "id": "receptionist", "name", "description", "default_for": ["clinic"], "sample_audio_url": null }]`, covering the 4 roles in docs/02 ONB-03 |
| `GET /v1/catalog/voices?language=te` | `[{ "id": "priya-te-hyd", "name": "Priya", "personality": "Friendly, warm", "languages": ["te","en"], "dialect": "Hyderabadi", "gender": "female", "tier": "natural", "sample_text": "…", "sample_audio_url": null }]`. Provide at least 6 voices across te/hi/en and all 3 tiers. |
| `GET /v1/catalog/rates` | `[{ "tier": "smart", "inr_per_min": 3.0 }, { "tier": "natural", "inr_per_min": 4.5 }, { "tier": "signature", "inr_per_min": 6.0 }]` |

## 3. Knowledge ("What they know")

| Method & path | Body | Response |
|---|---|---|
| `POST /v1/knowledge/sources` | `{ "type": "url", "url" }` or `{ "type": "text", "text" }` | `201 { id, type, status: "processing" \| "ready" \| "failed", title, created_at, error? }` |
| `GET /v1/knowledge/sources` | – | list |
| `GET /v1/knowledge/facts` | – | `[{ id, category: "services"\|"prices"\|"timings"\|"location"\|"contact"\|"faq"\|"policy", key, value, source_id, status: "suggested"\|"confirmed" }]` |
| `POST /v1/knowledge/facts` | `{ category, key, value }` | `201` fact (status confirmed) |
| `PATCH /v1/knowledge/facts/{id}` | `{ value?, status? }` | fact |
| `DELETE /v1/knowledge/facts/{id}` | – | `204` |
| `GET /v1/knowledge/gaps` | – | `[{ category, key, question: "What is your consultation fee?" }]`, i.e. important facts still missing for this industry |

Step 2 extraction is **deterministic, with no LLM**:
- **URL:** fetch with a 10 s timeout and 2 MB cap. Allow only http(s) and block private/loopback IPs (SSRF guard). Extract the title, meta description, phone numbers, email, address-like lines and opening-hours patterns as `suggested` facts.
- **Text:** each `Key: value` line becomes a fact, with the category guessed from keywords.
- Mark the extractor as replaceable (LLM extraction arrives in Step 3).

## 4. Employees (extend existing)

`PATCH /v1/employees/{id}` also accepts:
- `voice_id` (must exist in the catalog)
- `greeting` (≤ 300 chars)
- `behaviour`: `{ ask_for: string[], never_say: string[], transfer_when: string[] }`, each list ≤ 20 items of ≤ 200 chars

`GET` returns these fields.

## 5. Test calls (simulated until the voice pipeline exists)

| Method & path | Body | Response |
|---|---|---|
| `POST /v1/test-calls` | `{ "employee_id", "phone"? }`. Defaults to the owner's phone. | `201 { id, status: "queued", simulated: true }` |
| `GET /v1/test-calls/{id}` | – | `{ id, status: "queued"\|"ringing"\|"connected"\|"completed", simulated: true, transcript: [{ speaker: "employee"\|"caller", text, at_ms }], summary? }`. Status advances with elapsed time (≈2 s per state). The transcript uses the business's name, the employee's greeting and confirmed facts. |
| `POST /v1/test-calls/{id}/corrections` | `{ "text": "Say the consultation fee is ₹500" }` | `201 { id, applied_to: "knowledge"\|"behaviour", change_summary }`. Step 2 uses a simple rule: text that mentions ₹/price/fee/time/hours becomes a confirmed knowledge fact; anything else is appended to `behaviour.never_say`/`ask_for` as a note. |

## 6. Onboarding progress

`GET /v1/onboarding/progress` → `{ "steps": [{ "key": "business"|"role"|"teach"|"voice"|"test_call"|"go_live", "done": bool }], "percent": 0-100, "next": "teach" }`

## 7. Cross-cutting
- CORS: allow `http://localhost:3000` and `http://localhost:3100` in local env only.
- Every new table carries `business_id`, has ENABLE + FORCE RLS with a policy, and has explicit grants to `mitra_app`. This follows the Step 1 pattern.
- Tests are required for every endpoint, including the RLS isolation test for each new table.
