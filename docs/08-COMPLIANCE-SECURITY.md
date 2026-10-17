# 08 · Compliance, Security & Trust

> ⚠️ This is a product-design summary based on public sources (mostly vendor guides) as of Oct 2026. **It is not legal advice.** Before launching outbound calling, have an Indian telecom/data-protection lawyer confirm against the current TCCCPR (as amended), DoT 140/160 series orders, and the DPDP Act 2023 + DPDP Rules 2025 on MeitY's site.

---

## 1. Regulatory landscape (what we design for)

| Area | What applies (as understood) | Product response |
|---|---|---|
| **TRAI TCCCPR (telemarketing)** | **Promotional** calls must come from registered telemarketers on **140-series**. **Service/transactional** calls: **1600** for BFSI & government; **1601** for other sectors, rolled out in phases (TRAI direction of 10 Aug 2026 — Phase I: utilities, logistics/courier). Sectors not yet in a 1601 phase (clinics, real estate, education today) can still make consented service calls from regular verified business numbers. Commercial calls from **unregistered personal mobile numbers** risk complaints and disconnection. Senders and templates registered on **DLT**. Respect DND/NCPR. | Caller-ID strategy in §8; purpose-based routing (NUM-03); CMP-04 DND scrub; CMP-07 DLT mapping |
| **CNAP (Calling Name Presentation)** | Telcos directed to show the caller's registered name from **1 Nov 2026** on 4G/5G; businesses can register a preferred/verified name | Register each business's display name (NUM-06) |
| **Robocall / AI calls** | AI calls treated like automated calls: consent + traceability expected; AI disclosure increasingly expected | CMP-01 disclosure at call start (always on); consent ledger |
| **Calling hours** | Promotional calling limited to permitted hours | CMP-05 hard guard in Compliance service |
| **DPDP Act 2023 + Rules 2025** | Consent must be free, specific, informed, unambiguous, revocable; purpose limitation; erasure rights; breach notification; phased obligations through 2026–2027; penalties up to ₹250 crore | Purpose-tagged consent, erasure workflow, data minimisation, breach runbook, DPO contact |
| **Sector rules** | Healthcare (patient data sensitivity), BFSI (RBI/IRDAI conduct), real estate (RERA claims accuracy) | Industry guardrail packs |
| **Recording** | Inform callers that calls are recorded | CMP-02 recording notice |

## 2. Roles under DPDP

- **Business customer (clinic, builder)** = *Data Fiduciary* for their customers' data.
- **Mitra** = *Data Processor* acting on their instructions (DPA in our Terms).
- For our own users (owners, agency staff) Mitra = Data Fiduciary.

## 3. Compliance service — hard rules (code, not prompts)

Every outbound attempt passes `compliance.check(contact, purpose, time, number)`:

1. **Consent present** for this purpose (lead form consent, existing customer relationship for service calls, explicit opt-in) — else block.
2. **Not opted out** (global per business + per purpose).
3. **DND/NCPR status** checked (cached ≤ 24 h) for promotional purpose — block if registered.
4. **Allowed hours** in contact's timezone (default IST) — else defer to next window.
5. **Correct caller ID for purpose** (see §8): service → business's verified local number (or 1601/1600 where the sector is mandated); promotional → 140 series or blocked.
6. **Frequency cap** (e.g. ≤ 3 attempts/day, ≤ 7/week per contact by default).
7. **Template mapping** present for promotional scripts (DLT) once enabled.

Result logged with reason → visible to owner in plain language ("18 people skipped: on Do-Not-Disturb list").

## 4. In-call disclosures (default wording, localised, editable but not removable)

- EN: "Hi, this is Priya, an AI assistant from Sunrise Clinic. This call may be recorded to help serve you better."
- TE: "Namaskaram, nenu Priya, Sunrise Clinic nunchi AI assistant ni. Mee seva kosam ee call record avvachu."
- HI: "Namaste, main Priya, Sunrise Clinic ki AI assistant hoon. Behtar seva ke liye yeh call record ho sakti hai."

Opt-out phrases ("don't call me", "call cheyakandi", "mat karo call") → acknowledged politely → contact suppressed immediately.

## 5. Healthcare & sensitive-domain guardrails

- Never diagnose, prescribe, interpret reports, or give dosage advice → "I'll have the doctor/nurse call you" + staff alert.
- Emergency keywords (chest pain, bleeding, unconscious, suicide) → immediate guidance to call **112**/nearest emergency + transfer to staff + owner alert.
- Lab reports shared only via secure link after identity check (DOB / OTP).
- BFSI: no guarantees of approval/returns; read only approved disclosures.
- Real estate: prices/availability only from facts pack/live sheet; no legal claims.

## 6. Data protection & security controls

| Control | Implementation |
|---|---|
| Residency | All PII, recordings, transcripts, embeddings in AWS Mumbai/Hyderabad. Model providers: prefer India-hosted or zero-retention API agreements; PII redaction before any non-India processing where feasible |
| Encryption | TLS 1.2+ everywhere; AES-256 at rest (RDS, S3, backups); phone numbers stored encrypted + HMAC-hashed index; OAuth tokens envelope-encrypted (KMS) |
| Tenancy isolation | Postgres RLS on every tenant table; per-tenant S3 prefixes + IAM conditions; automated cross-tenant access tests in CI |
| Access control | RBAC (Owner, Manager, Staff, Agency admin, Mitra support with just-in-time, logged, customer-approved access) |
| Secrets | AWS Secrets Manager; no secrets in repo; pre-commit secret scanning |
| Retention | Recordings default 90 days (configurable 30–365); transcripts 1 year; usage/billing 8 years (tax); auto-deletion jobs |
| Erasure | "Forget this customer" + caller voice request → erasure across DB, recordings, embeddings, memory, backups (on rotation) with confirmation |
| Logging | Immutable audit log for config changes, approvals, data exports, support access |
| AppSec | OWASP ASVS L2 target; dependency scanning; SAST; annual pentest from P2 |
| AI-specific | Prompt-injection defences (caller can't change instructions; tool permissions scoped per employee; writes need policy checks); output checks on prices/medical; no training on customer data without explicit opt-in |
| Voice cloning (P3) | Written consent from voice owner, liveness check, revocation, watermarking where supported, never clone public figures |
| Incident response | Runbook, 24×7 on-call (P2), breach notification per DPDP timelines, status page |

## 7. Trust features shown to customers

- `/safety` public page in plain language.
- In-app "How Mitra protects your customers" card.
- Monthly WhatsApp trust summary (P2): "All 1,204 calls introduced Priya as AI · 23 opt-outs honoured · 0 data requests pending."

## 8. Caller ID & answer-rate strategy ("Trusted Caller ID")

**Problem:** calls from 140/160-style numbers or unknown numbers are often labelled spam, so people don't pick up. A voice agent nobody answers is worthless.

**Principle:** make Mitra's calls look like they come **from the business itself**: a real local number, the business's verified name and logo, and only to people who expect the call. We do **not** use number rotation, personal SIMs, or SIM-box gateways. Those are spam tactics, can be illegal, and get numbers blocked within days.

### 8.1 Which number each call uses

| Call purpose | Caller ID shown | Example |
|---|---|---|
| Inbound (customer calls the business) | Business's own number (forwarded to Mitra) | Patient calls clinic's usual number |
| **Callback / missed-call rescue** | Same business number the customer called | "You called Sunrise Clinic" → we call back from that number |
| **Service to a consenting customer** (lead who just enquired, appointment reminder, report ready, payment due) | **Dedicated local 10-digit business number** in the business's name, Truecaller-verified + CNAP name | `040-4xxx-xxxx · Sunrise Clinic ✓` |
| Service, sector mandated to 1600/1601 (BFSI, utilities, logistics…) | Business's own 1600/1601 number + verified name | NBFC EMI reminder |
| **Promotional / cold** (no prior relationship) | 140-series via registered telemarketer only — **off by default** and discouraged | — |

The Compliance service classifies purpose from the routine/campaign type and blocks mismatches.

### 8.2 Number options for a business (owner chooses in "Connect")

1. **Bring my existing business number** *(recommended where possible)*: landline/PRI/SIP numbers ported or connected via SIP trunk, so customers see the number they already know. *(Personal mobile SIMs are not supported for outbound AI calling.)*
2. **Get a new local number from Mitra**: a city-code number (e.g. 040 Hyderabad, 0866 Vijayawada) or mobile-series virtual number from our carriers (Exotel/Plivo/Tata), KYC in the business's name.
3. **Use my 1600/1601 number**: for mandated sectors; we connect to it over SIP.

### 8.3 Trust boosters (built into setup)

| Booster | What the customer sees | Feature |
|---|---|---|
| **CNAP name registration** (live from 1 Nov 2026) | Business name shown by the network on 4G/5G phones | NUM-06 |
| **Truecaller Verified Business** | Green badge, business name + logo, call reason | NUM-04 |
| **WhatsApp heads-up** | "Hi Ravi, Sunrise Homes will call you in 2 min from 040-4xxx-xxxx about your enquiry" | NUM-07 |
| **Same number, every time** | One stable number per business/branch so customers save it | NUM-01 |
| **WhatsApp voice call fallback** | Verified business profile name on WhatsApp | CALL-10 |
| **Spam-label monitoring** | We track answer rate & spam labels per number; alert + remediation (pause, reputation appeal, re-verify) | NUM-08 |
| **Healthy calling patterns** | Pacing, frequency caps, no repeated calls to non-answering numbers | CMP-05 / CALL-04 |

Vendor-reported benchmark (unverified): answer rates of ~20–35% unverified vs ~45–65% with verified caller ID. We measure our own per number.

### 8.4 Legal note
Rules for 1601 phases and CNAP business names are still being rolled out. Before outbound launch, legal counsel confirms (a) that consented lead follow-ups count as service, not promotional, for each vertical, and (b) the obligations for virtual numbers used by clients. Product defaults stay conservative: **outbound only to people with a consent record or an existing relationship.**

## 9. Compliance checklist before outbound GA

- [ ] Legal opinion on TCCCPR/DLT obligations for our model (platform vs telemarketer)
- [ ] Carrier agreements for local business numbers + SIP trunks; 1600/1601/140 partners for mandated or promotional cases
- [ ] Truecaller Verified Business + CNAP name registration process tested end-to-end
- [ ] Legal confirmation that consented lead follow-ups are "service" for each launch vertical
- [ ] DND scrubbing provider integrated & tested
- [ ] Consent capture verified for each lead source
- [ ] DPA + privacy policy + terms reviewed
- [ ] Disclosure wording reviewed in TE/HI/EN
- [ ] Erasure workflow end-to-end tested
- [ ] Healthcare guardrail eval set ≥ 200 cases passing
