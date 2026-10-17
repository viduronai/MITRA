# 01 · PRD — Product Requirements Document

Product: **Mitra** · Version: 1.0 (draft) · Owner: Founders · Status: Awaiting approval

---

## 1. Problem

Indian small and mid-sized businesses run on phone calls, and they lose money on them every day.

| Pain | Evidence (directional — mostly vendor-reported) |
|---|---|
| Missed calls | Service SMBs miss ~25–40% of inbound calls in business hours, ~60% after hours |
| Slow lead response | Ad leads go cold within minutes; telecallers call hours or days later |
| No follow-up discipline | Reminders, confirmations, post-visit calls and payment nudges depend on one overworked person |
| Telecaller churn & cost | Hiring, training and retaining telecallers is expensive; quality is inconsistent |
| Existing AI tools don't fit | Developer tools need engineers; simple tools sound robotic, only make calls, and stop there; enterprise tools cost lakhs and take months |

## 2. Vision

> Every Indian business, however small, gets a team of tireless, polite, multilingual phone staff who sound human, never miss a call, never forget a follow-up — and can be managed with a WhatsApp voice note.

## 3. Goals & non-goals

### Goals (first 12 months)
1. **G1 — Human-grade calls:** ≥ 70% of test listeners cannot reliably tell Mitra from a human telecaller in a blind test of 30-second clips (Telugu, Hindi, English, code-mixed).
2. **G2 — 10-minute setup:** median time from sign-up to first live call ≤ 10 minutes, with no human help.
3. **G3 — Proven outcomes:** customers see more booked appointments / site visits per 100 leads than their pre-Mitra baseline.
4. **G4 — Owner trust:** ≥ 60% of active owners interact with the WhatsApp report or AI Manager weekly.
5. **G5 — Compliant by default:** zero regulatory incidents; 100% of calls disclose AI, 100% outbound numbers DND-checked.

### Non-goals (for now)
- Building our own speech recognition / voice synthesis models (we orchestrate best-in-class providers; revisit in Phase 3+).
- Full CRM, full helpdesk, or full ERP. We integrate; we don't replace.
- Medical, legal, or financial advice by the AI. Mitra books, informs, reminds, and hands over.
- Video avatars, email agents, social DM agents (Phase 3+ consideration).
- Markets outside India (until product–market fit in India).

## 4. Target customers & personas

### 4.1 Segments (priority order)

| Priority | Segment | Size of pain | Main jobs |
|---|---|---|---|
| P1 | **Clinics, diagnostic labs, small hospitals** | High inbound volume, no-shows, follow-ups | Receptionist, reminders, report sharing, post-visit follow-up |
| P1 | **Real estate builders & brokers** | Expensive ad leads go cold | Lead calling < 1 min, qualification, site-visit booking, payment reminders |
| P2 | **Coaching centres, colleges, schools** | Admission season spikes | Enquiries, counselling bookings, fee reminders |
| P2 | **Digital marketing agencies** (channel) | Need to prove ad ROI to clients | Resell Mitra white-label to their clients |
| P3 | Car dealers, loan/insurance agents, restaurants, D2C | Similar call patterns | Lead calls, service reminders, order confirmations |

### 4.2 Personas

**Dr. Lakshmi — clinic owner (Hyderabad), 42**
- Runs a 3-doctor clinic; 1 receptionist who is always on another call.
- Uses WhatsApp all day; hates "software"; reads Telugu and English.
- *Wants:* no missed patient calls, fewer no-shows, patients reminded about reports and follow-ups.
- *Fears:* the AI saying something medically wrong; patients feeling cheated by a "robot".

**Srinivas — real estate builder (Vijayawada), 50**
- Spends ₹3–5 lakh/month on Facebook & Instagram ads; 2 telecallers.
- *Wants:* every lead called in a minute, only serious buyers sent to his sales team, site visits booked.
- *Fears:* wasting money; leads getting annoyed; the AI promising wrong prices.

**Anjali — front-desk manager (multi-specialty hospital), 29**
- Day-to-day operator; comfortable with apps, not with tech setup.
- *Wants:* see today's calls, fix mistakes quickly, transfer tough calls to the right desk.

**Rahul — agency founder (Bengaluru), 31**
- Runs ads for 40 local businesses; technically comfortable.
- *Wants:* a branded AI calling product to sell, client dashboards, templates, margins.
- *Fears:* support burden, unreliable quality damaging his reputation.

**The caller (end customer)** — not a user of the app but the most important judge.
- *Wants:* to be understood in their language, quickly, politely, without repeating themselves.

## 5. Jobs to be done

1. *When a customer calls and nobody picks up,* I want someone to answer and book them, *so I don't lose the business.*
2. *When a new lead fills my ad form,* I want them called immediately and qualified, *so my ad money isn't wasted.*
3. *When an appointment / visit / payment is coming up,* I want the customer reminded politely, *so no-shows and delays drop.*
4. *When something important happens,* I want to know on WhatsApp and decide in one tap, *so I stay in control without a dashboard.*
5. *When the AI gets something wrong,* I want to correct it like I'd correct a staff member, *so it gets better.*
6. *(Agency)* *When I sign a client,* I want to set up a branded AI team in minutes, *so I can sell it profitably.*

## 6. Product scope by phase

Full feature list with IDs: [02-FEATURES.md](02-FEATURES.md). Roadmap detail: [09-ROADMAP-PRICING-METRICS.md](09-ROADMAP-PRICING-METRICS.md).

| Phase | Theme | Headline scope |
|---|---|---|
| **Phase 1 — "One great employee"** | Prove human-grade calls + 10-min setup | Single AI employee (4 role templates), inbound + outbound, lead calling < 60s, human transfer, Telugu/Hindi/English + code-mix, talk-to-setup onboarding, knowledge from website/docs/photos/voice notes, test call with spoken corrections, WhatsApp follow-ups, Google Calendar & Sheets, daily WhatsApp report, **basic WhatsApp AI Manager** (questions + simple commands), compliance basics, prepaid wallet + plans |
| **Phase 2 — "Your AI team"** | Multi-employee teams & autopilot | AI Team templates per industry, handoffs, shared customer memory, customer timeline, plain-language routines, "Ask me first" approvals, staff briefs, call-a-list campaigns, CRM integrations (Zoho, LeadSquared, HubSpot), payment links, WhatsApp voice calling, more languages |
| **Phase 3 — "Studio & partners"** | Agencies & power users | Studio Mode (custom teams, rules, tools), agency white-label (brand, domain, pricing, client billing), multi-client dashboard, template marketplace, "Sounds like my best caller" style training, consented voice cloning, mobile app, advanced analytics |

## 7. Key functional requirements (summary)

| Area | Requirement |
|---|---|
| Conversation | Reply start ≤ 800 ms p95 (target 500–600 ms); handle barge-in within 200 ms; back-channels; mid-call language switch; Indian number/date/price speech norms |
| Setup | No field requires technical knowledge; every step has a sensible default; go-live possible in ≤ 5 steps |
| Knowledge | Learn from URL, PDF, image (OCR incl. Indic scripts), voice note, typed FAQ; show "what they know" in plain cards the owner can edit |
| Memory | Per-customer memory shared by the team; owner can view/correct; inferred vs confirmed facts separated |
| Actions | Book/reschedule/cancel (Calendar), send WhatsApp (templates), update Sheet/CRM, transfer to human, send payment link, schedule callback |
| Teams | Handoff rules in plain language; one customer timeline across employees |
| Owner control | Daily report, approvals, corrections, listen to any call, pause any employee instantly |
| Compliance | AI disclosure at call start, consent capture/log, DND scrub, calling-hour limits, purpose-based caller ID (verified local business number; 1600/1601/140 only where mandated), Truecaller/CNAP verified name, DLT template mapping, India data residency, recording consent |
| Agency | White-label branding, client sub-accounts, usage-based client billing, templates |

## 8. Success metrics

| Type | Metric | Target (12 months) |
|---|---|---|
| North Star | **Successful outcomes per week** (bookings, qualified leads, confirmed reminders, payments promised) | Growing ≥ 10% MoM |
| Activation | Sign-up → first live call within 24h | ≥ 50% |
| Setup | Median time to first live call | ≤ 10 min |
| Quality | Human-likeness blind test pass rate | ≥ 70% |
| Quality | Calls ended early by caller in first 10 s | ≤ 8% |
| Quality | Response latency p95 | ≤ 800 ms |
| Trust | Weekly WhatsApp report/Manager engagement | ≥ 60% of owners |
| Retention | Logo retention at month 3 | ≥ 75% |
| Revenue | Net revenue retention (paid accounts) | ≥ 110% |
| Channel | Revenue from agencies (after Phase 3) | ≥ 30% |

## 9. Pricing (summary)

**Pay only for talk-time, ₹3–6 per minute. No monthly fee, no setup fee, no lock-in.** Indian owners compare per-minute rates directly with a telecaller's cost, and a monthly fee feels like a commitment. Detail in [09](09-ROADMAP-PRICING-METRICS.md).

| Voice tier | Price / connected minute | Best for |
|---|---|---|
| **Smart** | ₹3 | High-volume reminders, confirmations, simple enquiries |
| **Natural** ⭐ (default) | ₹4.5 | Human-grade voice with the full human layer — receptionists, lead calling |
| **Signature** | ₹6 | Premium voices, "sounds like my best caller" style, priority capacity |

- Billed **per second of connected talk-time**; unanswered, busy and blocked calls cost ₹0.
- **All features included at every tier** (teams, routines, approvals, WhatsApp Manager). Only voice quality changes the rate.
- Prepaid wallet via UPI; bonus credits on bigger top-ups; 100 free minutes to start.
- Pass-through extras at cost: dedicated number rental, WhatsApp template fees, verified caller-ID setup.
- Volume (businesses) and wholesale (agencies) rates from ~₹2.5/min.

Benchmarks: Outpero ₹3.5–7/min; Bolna ~₹5.5/min + fees; Whinta (white-label) ~₹3/min.

## 10. Assumptions

1. Best-in-class Indic voice providers (e.g. Sarvam Bulbul for TTS) are good enough for human-grade Telugu/Hindi with our "human layer".
2. Unit cost (STT + LLM + TTS + telephony) lands at ₹2–3.5/min, enabling ~₹4/min retail with healthy margin.
3. SMB owners will manage via WhatsApp more readily than via a dashboard.
4. Agencies will resell if quality and margins are strong.

## 11. Risks & mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Large players (Tata Comms, Sarvam, Bolna) copy simple setup | High | Moat = human layer quality + industry team templates + learning from corrections + agency channel |
| Voice quality inconsistent across dialects | High | Per-language eval suite, human listening panels, provider fallback, dialect tuning |
| Regulatory change (TRAI/DPDP) | High | Compliance module as a first-class service, legal review before outbound GA, conservative defaults |
| AI says something wrong (price, medical) | High | Grounded answers only from "what they know", refusal + handover rules, approvals, healthcare guardrails |
| Latency spikes at scale | Medium | Streaming everywhere, regional hosting (Mumbai/Hyderabad), provider fallbacks, load tests |
| Telephony costs/quality vary | Medium | Multi-carrier (Exotel, Plivo, Tata), quality monitoring |

## 12. Open questions for founders

1. Final brand name & domain (mitra.ai / getmitra.in / heymitra.com availability to check).
2. Team composition & budget → determines Phase 1 timeline.
3. Will founders handle first 20 customers hands-on (recommended) for learning?
4. Legal counsel for TRAI/DPDP sign-off before outbound launch.
