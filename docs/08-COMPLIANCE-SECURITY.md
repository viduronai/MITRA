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

### 5.1 Payment collection (ACT-05 / ACT-11)

- The money is the **business's**: links are created in the business's own Razorpay account (keys sealed per business, never shown again) or point at its own UPI ID. Nothing flows through Mitra, and it is kept separate from Mitra's wallet billing.
- An AI employee may only quote an amount written in the business's facts or the call's brief (the voice service refuses any other amount). Discounts and amounts above the owner's threshold wait for "Ask me first".
- Reminders stay polite and limited: one WhatsApp the morning after the due date ("already paid? ignore this"), then at most one call through the normal dialer, so calling hours, frequency caps and "don't call me" apply unchanged. No threats, no shaming, no calls to third parties (family, employer), no repeated calls. Everything stops the moment the link is paid or cancelled; an opted-out customer gets no reminders.
- **Lenders (NBFCs, microfinance, gold loans, any lending / BFSI business; founder decision, 3 Nov 2026):** the RBI Fair Practices Code and its recovery-agent rules apply to the business. The owner marks the business as a lender in Payments → How you collect; from then on the **compliance gate** (not just the UI) allows payment-collection calls only **8 am–7 pm** local time (RBI recovery conduct), combined with our general service window, so in practice 9 am–7 pm. Calls outside it are deferred to the next allowed time. Collection calls are the dialer jobs for routine goal "collect the payment" or carrying a payment amount. Mitra never uses recovery language, and the business remains responsible as the lender. TODO(legal): confirm whether an AI reminder caller counts as a "recovery agent" under RBI directions.
- **Link expiry:** links expire 15 days after sending (1–180, per business). One WhatsApp goes out 2 days before expiry if unpaid; at expiry the link is marked expired and any queued reminder call is cancelled.
- **"Already paid":** a customer's "Already paid" tap or "PAID" reply only flags the link for the owner, who confirms with "Mark paid". It is never marked paid automatically; pending reminder calls are withdrawn while the owner checks.
- TODO(razorpay): `payment.failed` events are matched to a link through the `mitra_request_id` note; confirm with real Razorpay test keys that the note is copied onto the payment.
- Webhooks are verified with the business's own secret (HMAC-SHA256 over the raw body) and applied once per event id. Outgoing `payment.paid` / `payment.failed` events carry ids, amounts and last-4 digits only.

## 6. Data protection & security controls

| Control | Implementation |
|---|---|
| Residency | All PII, recordings, transcripts, embeddings in AWS Mumbai/Hyderabad. Model providers: prefer India-hosted or zero-retention API agreements; PII redaction before any non-India processing where feasible |
| Encryption | TLS 1.2+ everywhere; AES-256 at rest (RDS, S3, backups); phone numbers stored encrypted (AES-256-GCM, per-business keys from one master key held as a KMS-encrypted data key, decrypted only in memory; staging/prod refuse to start without it) + HMAC-hashed index; OAuth tokens envelope-encrypted (KMS) |
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

### 8.5 Lead consent policy (founder decision, 3 Nov 2026)

> **Needs a legal check before launch.** This is the founder's product policy, built into the code (`services/core/src/mitra_core/leads/consent.py`), not a legal opinion.

How each lead source proves the person asked to be contacted. Every consent record is **service** scope only; promotional contact still needs explicit promotional consent plus the DND scrub (§3), and the AI disclosure and "don't call me" handling are unchanged (§4).

| Source | Rule | Record kept |
|---|---|---|
| **Forms Mitra controls**: website form snippet, Google Forms script | Unticked, required checkbox: "I agree to get a call or WhatsApp from <Business>, possibly from an AI assistant, about my enquiry." (en / hi / te). No tick: no call, no message | Source = the form, exact text + version (`lead-v1`) + time |
| **Third-party lead forms**: Meta Lead Ads, Google Ads lead forms, IndiaMART, JustDial | The enquiry counts as consent to answer that enquiry only (`enquiry_response`), for 30 days (configurable: `MITRA_LEAD_PORTAL_CONSENT_DAYS`). After that the compliance gate treats it as no consent. An explicit "no" in the payload: no call, no message. Setup screens recommend adding the consent line to the portal form | Source = the portal, purpose, expiry |
| **Generic sources**: lead API, Google Sheets, Zapier / Make / Pabbly / n8n | The owner must tick "These people asked to be contacted about their enquiry" for the source. Without it, leads are stored but not called ("Not called: no consent confirmed") | Who ticked it, when, the exact words and version (`attest-v1`); unticking is logged too |
| **Campaign lists** (CSV upload / pasted rows, CALL-15) | Service lists: the owner ticks "These people are my customers or asked to be contacted about this" (en / hi / te). No tick: the campaign cannot start. Adding people to a live list needs the tick again. Each person queued gets a **service** consent record, source `owner_attested_list`, purpose = the campaign, expiring when the campaign ends (finished, cancelled or its last calling day), after 30 days at most | On the campaign: who ticked, when, exact words, version (`list-attest-v1`); per person: the consent record |
| **Promotional campaign lists** | **Legal check before launch.** The owner must additionally tick "I have explicit consent from every person on this list to get promotional calls from my business"; records are **promotional** scope. The DND scrub, the 140-series caller ID and DLT rules (§3, §8.1) still apply at dial time, and promotional calling stays off by default | Same as above, both statements stored together |

## 9. Compliance checklist before outbound GA

- [ ] Legal opinion on TCCCPR/DLT obligations for our model (platform vs telemarketer)
- [ ] Carrier agreements for local business numbers + SIP trunks; 1600/1601/140 partners for mandated or promotional cases
- [ ] Truecaller Verified Business + CNAP name registration process tested end-to-end
- [ ] Legal confirmation that consented lead follow-ups are "service" for each launch vertical
- [ ] DND scrubbing provider integrated & tested
- [ ] Consent capture verified for each lead source (lawyer reviews §8.5 lead consent policy)
- [ ] DPA + privacy policy + terms reviewed
- [ ] Disclosure wording reviewed in TE/HI/EN
- [ ] Erasure workflow end-to-end tested
- [ ] Payment reminders reviewed for lenders (RBI Fair Practices Code / recovery-agent rules, §5.1)
- [ ] Healthcare guardrail eval set ≥ 200 cases passing
