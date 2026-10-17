# MITRA — Product Documentation

> **Mitra** (मित्र / మిత్ర — "friend") — AI voice employees that talk like your best staff member, work 24/7, and finish the follow-up work too.

Status: **Draft v1.0 — awaiting founder approval** · Last updated: 2026-10-18

---

## 1. One-line pitch

**A ready-made AI calling team that any Indian business owner can hire in 10 minutes, run from WhatsApp, and that agencies can resell under their own brand.**

## 2. Document map

| # | Document | What it answers | Primary reader |
|---|---|---|---|
| 00 | [README](00-README.md) | What is Mitra, where is everything | Everyone |
| 01 | [PRD — Product Requirements](01-PRD.md) | Why, for whom, what, success metrics | Founders, product, investors |
| 02 | [Complete Feature List](02-FEATURES.md) | Every feature, ID, priority, phase | Product, engineering |
| 03 | [User Flows](03-USER-FLOWS.md) | How each persona moves through the product | Design, product, engineering |
| 04 | [System Workflows](04-WORKFLOWS.md) | What happens behind the scenes (calls, handoffs, routines, approvals) | Engineering |
| 05 | [TRD — Technical Requirements](05-TRD.md) | Architecture, stack, voice pipeline, RAG, data, APIs, NFRs | Engineering |
| 06 | [Design System](06-DESIGN-SYSTEM.md) | Principles, tokens, typography, components, motion, UI sources | Design, frontend |
| 07 | [Screens & Information Architecture](07-SCREENS.md) | Every screen, landing page sections, copy rules | Design, frontend |
| 08 | [Compliance, Security & Trust](08-COMPLIANCE-SECURITY.md) | TRAI, DLT, DPDP, consent, safety guardrails | Founders, engineering, legal |
| 09 | [Roadmap, Pricing & Metrics](09-ROADMAP-PRICING-METRICS.md) | Phases, milestones, pricing, KPIs, risks | Founders |

## 3. The product in 30 seconds

1. **Hire** — the owner picks a ready-made role (Receptionist, Lead Caller, Reminder Caller, Payment Caller) or a whole **AI Team** for their industry.
2. **Teach** — paste a website / Google Business link, upload a brochure or price-list photo, or record a 2-minute voice note. Mitra learns the business.
3. **Pick a voice** — "Priya · friendly Hyderabadi Telugu-English", "Ravi · polite formal Hindi". Hear it before choosing.
4. **Test call** — Mitra calls the owner's phone. The owner plays customer, corrects anything by speaking.
5. **Go live** — forward missed calls, or connect Meta ads / website forms / Google Sheets.
6. **Run it from WhatsApp** — daily report, approvals, "call everyone who said maybe", corrections by voice note.

## 4. What makes Mitra different (the moat)

| # | Differentiator | Competitors today |
|---|---|---|
| 1 | **Human-grade Indian conversation** — fast replies, "haan ji / hmm / sari" back-channels, interruption handling, code-mixing, dialect & respect levels | Most sound robotic or slow; few tune for dialects |
| 2 | **Hire, don't build** — no flows, no prompts, no jargon; setup by talking | Developer tools (Bolna, Vapi) need engineers |
| 3 | **AI Team with handoffs + shared memory** — Lead Caller → Visit Coordinator → Sales Assistant → Payment Caller, one customer timeline | Single-bot tools (Outpero-style) |
| 4 | **WhatsApp AI Manager** — owner commands the team with a voice note, no dashboard needed | Not offered by SMB voice tools |
| 5 | **Autopilot done simply** — plain-language routines, approvals for risky actions | Decibyl has it, but technical & invite-only |
| 6 | **Compliance on autopilot** — AI disclosure, DND scrub, consent log, DLT/140-160 handling, India data residency | Rarely disclosed by vendors |
| 7 | **Two floors** — Simple Mode for owners, Studio Mode + white-label for agencies | Rare in India |
| 8 | **Trusted Caller ID** — calls come from the business's own local number with its verified name & logo (Truecaller, CNAP), plus a WhatsApp heads-up — not spam-flagged 140/160 numbers | Most tools call from generic or series numbers |
| 9 | **Simple per-minute pricing** — ₹3 / ₹4.5 / ₹6 per minute, no monthly fee, every feature included | Competitors gate features or add platform fees |

## 5. Glossary (internal term → what the customer sees)

We **never** show technical words to business users. This table is binding for all UI copy.

| Internal / technical | Customer-facing word |
|---|---|
| Agent / bot | **AI employee** |
| Multi-agent system | **AI team** |
| Agent handoff | **Passes to** |
| System prompt / instructions | **How they should behave** |
| Knowledge base / RAG | **What they know** |
| Memory | **What they remember about customers** |
| Workflow / trigger / cron | **Routine** ("Every day at 6pm…", "When a new lead comes…") |
| Human-in-the-loop approval | **Ask me first** |
| Integration / webhook / API | **Connect** (apps shown by logo) |
| Campaign / bulk dial | **Call a list** |
| Transcript | **What was said** |
| Outcome / disposition | **Result** (Booked, Interested, Not interested, Call back) |
| Tenant / workspace | **Business** |
| Sub-account (agency) | **Client** |
| Latency / ASR / TTS | *(never shown)* |

## 6. Working assumptions (change if wrong)

- Launch region: **Telangana & Andhra Pradesh**, then South India, then Hindi belt.
- Launch languages: **Telugu, Hindi, English + code-mixed (Tenglish, Hinglish)**.
- Launch verticals: **Clinics/diagnostics** and **Real estate**; then coaching/education.
- Team: small founding team (2–5) building with AI-assisted development.
- "Clean and neat" design direction = calm, premium, minimal, zero clutter.

## 7. How to use these docs while building

- Every feature has an **ID** (e.g. `F-CALL-03`) in [02-FEATURES.md](02-FEATURES.md). Reference IDs in tickets, branches, and commits.
- Architecture decisions are recorded as **ADRs** in [05-TRD.md §15](05-TRD.md). Change an ADR before changing the code that depends on it.
- UI must pass the **"Grandmother test"** in [06-DESIGN-SYSTEM.md §1](06-DESIGN-SYSTEM.md): a non-technical owner completes the task without help.
