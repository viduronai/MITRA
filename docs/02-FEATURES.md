# 02 · Complete Feature List

Every feature has an ID, plain description, priority and phase.
**Priority:** `Must` (phase blocked without it) · `Should` · `Could`.  **Phase:** P1 / P2 / P3.
Customer-facing names follow the glossary in [00-README §5](00-README.md).

---

## 1. Onboarding & setup (`ONB`)

| ID | Feature | Description | Pri | Ph |
|---|---|---|---|---|
| ONB-01 | Sign up with phone OTP / Google | No passwords; WhatsApp OTP fallback | Must | P1 |
| ONB-02 | Business profile in one screen | Name, industry, city, languages, working hours — prefilled from Google Business link if given | Must | P1 |
| ONB-03 | Pick a role | Receptionist · Lead Caller · Reminder Caller · Payment Caller, each with a 1-line explanation and sample call audio | Must | P1 |
| ONB-04 | Talk-to-setup | Owner speaks or types "what my business does"; Mitra drafts the employee's behaviour & FAQs for review | Must | P1 |
| ONB-05 | Learn from link | Paste website / Google Business / Justdial / 99acres listing URL → auto-extract services, prices, timings, address | Must | P1 |
| ONB-06 | Learn from files & photos | PDF, DOCX, XLSX, images of price lists/brochures (OCR incl. Telugu, Hindi scripts) | Must | P1 |
| ONB-07 | Voice picker | Voice cards with name, personality, language, dialect, formality; tap to hear a sample in the business's own context | Must | P1 |
| ONB-08 | Test call to my phone | Mitra calls the owner; owner role-plays a customer | Must | P1 |
| ONB-09 | Correct by speaking | After the test call, owner says/types "Say the consultation fee is ₹500" → applied & re-testable | Must | P1 |
| ONB-10 | Go-live wizard | Choose: forward missed calls (carrier codes shown per operator), get a new number, or connect lead source | Must | P1 |
| ONB-11 | Setup progress checklist | Persistent 5-step checklist with % complete | Should | P1 |
| ONB-12 | Industry starter packs | Pre-filled FAQs, objections, result types per industry (clinic, real estate, coaching…) | Must | P1 |
| ONB-13 | Assisted setup booking | "Set it up for me" — book a 20-min call with our team | Should | P1 |
| ONB-14 | AI Team templates | One-tap hire of a full team per industry (see TEAM) | Must | P2 |

## 2. AI employees (`EMP`)

| ID | Feature | Description | Pri | Ph |
|---|---|---|---|---|
| EMP-01 | Employee profile | Name, role, photo/avatar, voice, languages, working hours, status (Working / Paused / Training) | Must | P1 |
| EMP-02 | "How they should behave" | Plain-language behaviour editor with guided sections (Greeting, What to ask, What never to say, When to transfer) | Must | P1 |
| EMP-03 | Instant pause / resume | One tap (app or WhatsApp "pause Priya") stops all calls within seconds | Must | P1 |
| EMP-04 | Working hours & holidays | Per employee; out-of-hours behaviour (take message, book callback) | Must | P1 |
| EMP-05 | Result types | Configurable outcomes (Booked, Interested, Not interested, Call back, Wrong number…) with industry defaults | Must | P1 |
| EMP-06 | Questions to collect | Fields the employee gathers (budget, location, symptoms category, preferred time) → saved to customer | Must | P1 |
| EMP-07 | Version history | Every behaviour change saved; restore previous version in one tap | Should | P1 |
| EMP-08 | Duplicate employee | Clone for another branch/language | Should | P2 |
| EMP-09 | Performance card | Calls, results, avg call length, customer sentiment, owner rating | Should | P2 |
| EMP-10 | "Sounds like my best caller" | Upload recordings of top human telecaller → learn greeting, pacing, objection handling (style, not voice) | Could | P3 |
| EMP-11 | Consented voice clone | Clone a staff member's voice with signed consent + liveness check | Could | P3 |

## 3. Human-grade conversation (`VOICE`)

| ID | Feature | Description | Pri | Ph |
|---|---|---|---|---|
| VOICE-01 | Fast replies | First audio ≤ 800 ms p95 after caller stops (target 500–600 ms) | Must | P1 |
| VOICE-02 | Instant acknowledgement | Short natural filler ("haan ji", "okay", "one second") while the full answer is generated, when needed | Must | P1 |
| VOICE-03 | Back-channels | "hmm", "achha", "sari", "avunu" while the caller speaks long, at natural pauses | Must | P1 |
| VOICE-04 | Barge-in | Stops speaking within 200 ms when interrupted; resumes context naturally | Must | P1 |
| VOICE-05 | Smart turn-taking | Waits through thinking pauses ("umm…"), doesn't cut people off | Must | P1 |
| VOICE-06 | Code-mixing | Understands and speaks Tenglish, Hinglish, Tanglish naturally in one voice | Must | P1 |
| VOICE-07 | Language mirroring | Switches language mid-call when the caller does | Must | P1 |
| VOICE-08 | Respect & formality | aap/tum, garu/sir/madam, formal vs friendly per business setting | Must | P1 |
| VOICE-09 | Indian speech norms | Prices (₹1.2 lakh, 50 thousand), dates, times, phone numbers, addresses spoken naturally | Must | P1 |
| VOICE-10 | Name use & warmth | Uses caller name, matches energy, apologises naturally, never argues | Must | P1 |
| VOICE-11 | Noise robustness | Handles traffic/market noise, speakerphone, poor network; asks to repeat gracefully | Must | P1 |
| VOICE-12 | Dialect options | e.g. Hyderabadi vs coastal Telugu, Bambaiya vs standard Hindi | Should | P2 |
| VOICE-13 | Office ambience | Optional subtle background ambience | Could | P2 |
| VOICE-14 | Emotion awareness | Detects frustration/urgency → softens tone or escalates | Should | P2 |
| VOICE-15 | Voicemail / IVR detection | Detects voicemail or IVR on outbound; leaves short message or hangs up | Should | P1 |
| VOICE-16 | Keypad input (DTMF) | Accepts digit entry when needed (e.g. booking ID) | Should | P2 |

## 4. Calling (`CALL`)

| ID | Feature | Description | Pri | Ph |
|---|---|---|---|---|
| CALL-01 | Answer inbound calls | 24/7 or by schedule; overflow when staff busy | Must | P1 |
| CALL-02 | Missed-call rescue | Calls back anyone whose call was missed within 2 min | Must | P1 |
| CALL-03 | Instant lead calling | Calls new leads within 60 s of arrival (Meta Lead Ads, website form, Sheet row, webhook) | Must | P1 |
| CALL-04 | Smart retries | Retries unanswered calls at configurable intervals within legal hours | Must | P1 |
| CALL-05 | Callback scheduling | "Call me after 6" → scheduled automatically | Must | P1 |
| CALL-06 | Transfer to human | Warm transfer to staff phone; ring groups; fallback to message if no answer | Must | P1 |
| CALL-07 | Whisper summary | Staff hears a private 1-line summary before being connected | Should | P2 |
| CALL-08 | Call a list | Upload/select contacts → calls with pacing, hours, DND scrub | Must | P2 |
| CALL-09 | Concurrent calls | Many calls in parallel per business (5 by default, raised with usage history) | Must | P1 |
| CALL-10 | WhatsApp voice calls | Answer/place calls over WhatsApp Business Calling | Should | P2 |
| CALL-11 | Recordings & transcripts | Every call recorded (with consent) + timestamped "what was said" | Must | P1 |
| CALL-12 | Call summary & result | Auto summary, result, collected fields, next step | Must | P1 |
| CALL-13 | Live call view | Watch ongoing calls live (transcript stream) and take over | Should | P2 |
| CALL-14 | Caller recognition | Recognises returning callers by number; greets with context | Must | P1 |

## 5. What they know — knowledge (`KNOW`)

| ID | Feature | Description | Pri | Ph |
|---|---|---|---|---|
| KNOW-01 | Knowledge cards | Everything learned shown as editable plain cards (Services, Prices, Timings, Location, FAQs, Policies) | Must | P1 |
| KNOW-02 | Sources | URL, PDF/DOCX/XLSX, images (OCR), voice notes, typed Q&A | Must | P1 |
| KNOW-03 | Auto-refresh website | Re-crawl linked site weekly; show what changed | Should | P2 |
| KNOW-04 | Unknown-question inbox | Questions the employee couldn't answer → owner answers once → learned | Must | P1 |
| KNOW-05 | Grounded answers only | Facts (prices, timings) answered only from knowledge; otherwise "let me confirm and call you back" | Must | P1 |
| KNOW-06 | Google Sheet as live data | Inventory/availability/doctor schedule read live from a Sheet | Should | P2 |
| KNOW-07 | Per-employee knowledge scope | Share or restrict knowledge per employee | Should | P2 |
| KNOW-08 | Knowledge health score | Shows gaps ("Add your cancellation policy") | Could | P2 |

## 6. What they remember — memory (`MEM`)

| ID | Feature | Description | Pri | Ph |
|---|---|---|---|---|
| MEM-01 | Customer profile | Name, language, preferences, collected fields, history — built automatically | Must | P1 |
| MEM-02 | Shared team memory | All employees see the same customer memory | Must | P2 |
| MEM-03 | Confirmed vs guessed | Facts the customer stated vs inferred are labelled separately | Should | P2 |
| MEM-04 | Owner can correct/forget | Edit or delete any memory; "forget this customer" (DPDP erasure) | Must | P1 |
| MEM-05 | Customer timeline | One chronological view: calls, WhatsApps, handoffs, bookings, payments | Must | P2 |

## 7. Actions the employee can take (`ACT`)

| ID | Feature | Description | Pri | Ph |
|---|---|---|---|---|
| ACT-01 | Book / reschedule / cancel | Google Calendar (P1), practice software & Calendly (P2) | Must | P1 |
| ACT-02 | Send WhatsApp during/after call | Location, brochure, booking confirmation, report link (approved templates) | Must | P1 |
| ACT-03 | Log to Google Sheet | Each call → row with result & fields | Must | P1 |
| ACT-04 | Update CRM | Zoho, LeadSquared, HubSpot, Salesforce (P2/P3) | Should | P2 |
| ACT-05 | Payment link | Razorpay / UPI link via WhatsApp/SMS | Should | P2 |
| ACT-06 | Notify staff | WhatsApp a staff member about a hot lead / urgent issue | Must | P1 |
| ACT-07 | Create follow-up task | Schedules future call/message for self or teammate | Must | P2 |
| ACT-08 | Custom action (Studio) | Call any HTTP API with mapped fields | Could | P3 |

## 8. AI team (`TEAM`)

| ID | Feature | Description | Pri | Ph |
|---|---|---|---|---|
| TEAM-01 | Team templates | Real estate: Lead Caller → Visit Coordinator → Sales Assistant → Payment Caller. Clinic: Receptionist → Reminder Caller → Follow-up Caller → Report Sender | Must | P2 |
| TEAM-02 | Plain-language handoffs | "When a lead is interested, pass to Visit Coordinator" — chosen from dropdown sentences | Must | P2 |
| TEAM-03 | Team map | Visual left-to-right chain of employees with arrows and counts | Must | P2 |
| TEAM-04 | Staff briefs | Before visits/consults, human staff get a WhatsApp brief (needs, budget, concerns) | Should | P2 |
| TEAM-05 | Escalation to owner | Any employee can escalate to owner/staff with reason | Must | P2 |
| TEAM-06 | Custom teams (Studio) | Add/remove roles, custom handoff conditions | Could | P3 |

## 9. Routines — autopilot (`AUTO`)

| ID | Feature | Description | Pri | Ph |
|---|---|---|---|---|
| AUTO-01 | Routine builder (sentence style) | "Every [day] at [6 pm], [call] [tomorrow's appointments] to [confirm]" | Must | P2 |
| AUTO-02 | Event routines | "When [a new lead arrives] from [Facebook], [Lead Caller] [calls within 1 min]" | Must | P1 (lead) / P2 (all) |
| AUTO-03 | Routine library | Ready-made routines per industry (no-show recovery, report ready, EMI reminder) | Must | P2 |
| AUTO-04 | Dry run | "Show me who will be called" before enabling | Should | P2 |
| AUTO-05 | Routine history | What ran, who was contacted, results | Must | P2 |

## 10. Ask me first — approvals (`APPR`)

| ID | Feature | Description | Pri | Ph |
|---|---|---|---|---|
| APPR-01 | Approval rules | Choose what needs approval: discounts, refunds, cancellations, big bookings, list calls | Must | P2 |
| APPR-02 | WhatsApp approve/decline | Interactive buttons; optional voice-note reason | Must | P2 |
| APPR-03 | In-call holding | Employee tells caller "I'll confirm with the team and call you back" | Must | P2 |
| APPR-04 | Timeouts & defaults | If no reply in X min → default action | Should | P2 |
| APPR-05 | Approval log | Who approved what, when | Must | P2 |

## 11. WhatsApp AI Manager (`MGR`)

| ID | Feature | Description | Pri | Ph |
|---|---|---|---|---|
| MGR-01 | Daily report | Morning WhatsApp: calls, results, money-moments, items needing attention, links to recordings | Must | P1 |
| MGR-02 | Ask questions | "How many site visits tomorrow?" "Who called about MRI?" (text or voice note, any launch language) | Must | P1 |
| MGR-03 | Give simple commands | "Pause Priya", "Call Ramesh back at 5", "Call all leads from yesterday who said maybe" (with confirmation) | Must | P1 (simple) / P2 (bulk) |
| MGR-04 | Coach by voice note | Reply to a call summary: "Next time offer Saturday first" → becomes behaviour update (with confirm) | Must | P1 |
| MGR-05 | Instant alerts | Hot lead, angry customer, VIP caller, failed payment | Must | P1 |
| MGR-06 | Weekly insights | "Most asked question this week: parking. Add an answer?" | Should | P2 |
| MGR-07 | Multi-person access | Owner + managers each get their own Manager chat with role limits | Should | P2 |

## 12. Reports & insights (`REP`)

| ID | Feature | Description | Pri | Ph |
|---|---|---|---|---|
| REP-01 | Home dashboard | Today at a glance: calls, results, money-moments, needs attention | Must | P1 |
| REP-02 | Calls list | Filter by employee, result, date, language; search transcripts | Must | P1 |
| REP-03 | Outcome funnel | Leads → contacted → interested → booked → visited/paid | Should | P2 |
| REP-04 | Lead source ROI | Results per ad campaign/source | Should | P2 |
| REP-05 | Quality review | Owner rates calls 👍/👎 with reason → improvement loop | Must | P1 |
| REP-06 | Export | CSV/Sheet export | Must | P1 |

## 13. Connections (`INT`)

| ID | Connection | Pri | Ph |
|---|---|---|---|
| INT-01 | Meta Lead Ads (Facebook/Instagram) | Must | P1 |
| INT-02 | Website form (embed snippet / webhook) | Must | P1 |
| INT-03 | Google Sheets | Must | P1 |
| INT-04 | Google Calendar | Must | P1 |
| INT-05 | WhatsApp Business (Meta Cloud API, direct; decided 3 Nov 2026) | Must | P1 |
| INT-06 | Zapier / Pabbly / Make / n8n | Should | P1 |
| INT-07 | Zoho CRM, LeadSquared, HubSpot | Should | P2 |
| INT-08 | Razorpay payment links | Should | P2 |
| INT-09 | Clinic/practice software (e.g. Practo-type, HIS) | Could | P2 |
| INT-10 | Property portals lead import (99acres, MagicBricks, Housing) | Should | P2 |
| INT-11 | Public API + webhooks (Studio) | Should | P3 |

## 14. Numbers & telephony (`NUM`)

| ID | Feature | Description | Pri | Ph |
|---|---|---|---|---|
Strategy and legal notes: [08 §8 Trusted Caller ID](08-COMPLIANCE-SECURITY.md).

| ID | Feature | Description | Pri | Ph |
|---|---|---|---|---|
| NUM-01 | Get a local business number | Dedicated city-code (e.g. 040) or mobile-series virtual 10-digit number, KYC in the business's name; one stable number per business/branch | Must | P1 |
| NUM-02 | Forward my existing number | Missed/busy call forwarding guide per operator (Jio, Airtel, Vi, BSNL) for inbound | Must | P1 |
| NUM-03 | Purpose-based caller ID routing | Callbacks from the number the customer called; service calls from the verified business number; mandated sectors via 1600/1601; promotional via 140 only (off by default) | Must | P1 |
| NUM-04 | Truecaller Verified Business | Guided setup: green badge, name, logo, call reason on the customer's screen | Must | P1 |
| NUM-05 | Multi-branch numbers | Separate numbers per branch, routed to the right team | Should | P2 |
| NUM-06 | CNAP name registration | Register the business's display name for network caller-name display (live from 1 Nov 2026) | Must | P1 |
| NUM-07 | WhatsApp heads-up before calling | "We'll call you in 2 min from 040-xxxx about your enquiry" (template, optional per routine) | Should | P1 |
| NUM-08 | Number health monitor | Answer rate & spam-label tracking per number; alerts + remediation steps | Must | P1 |
| NUM-09 | Bring my business landline / SIP number | Connect an existing landline/PRI/SIP number via SIP trunk or port, so outbound shows the number customers know (personal mobile SIMs not supported) | Should | P2 |

## 15. Compliance & safety (`CMP`) — detail in [08](08-COMPLIANCE-SECURITY.md)

| ID | Feature | Pri | Ph |
|---|---|---|---|
| CMP-01 | AI disclosure line at call start (localized) | Must | P1 |
| CMP-02 | Recording consent notice | Must | P1 |
| CMP-03 | Consent capture & log (source, time, purpose) | Must | P1 |
| CMP-04 | DND/NCPR scrub before promotional calls | Must | P1 |
| CMP-05 | Calling-hours guard (no calls outside allowed hours) | Must | P1 |
| CMP-06 | Opt-out by voice ("don't call me") → auto suppress | Must | P1 |
| CMP-07 | DLT template mapping for scripts/messages | Must | P2 |
| CMP-08 | Data stored in India; deletion requests | Must | P1 |
| CMP-09 | Healthcare guardrails (no diagnosis/advice) | Must | P1 |
| CMP-10 | Audit log export | Should | P2 |

## 16. Account, team & billing (`ADM`, `BILL`)

| ID | Feature | Pri | Ph |
|---|---|---|---|
| ADM-01 | Roles: Owner, Manager, Staff (view), Agency admin | Must | P1 |
| ADM-02 | Multiple branches under one business | Should | P2 |
| ADM-03 | Interface languages: English, Telugu, Hindi | Must | P1 |
| ADM-04 | Activity log | Should | P1 |
| BILL-01 | Pay-per-minute prepaid wallet (no monthly fee), per-second billing of connected talk-time | Must | P1 |
| BILL-02 | UPI / cards / net-banking + optional UPI AutoPay top-up via Razorpay | Must | P1 |
| BILL-03 | GST invoices | Must | P1 |
| BILL-04 | Low-balance WhatsApp alerts + auto top-up | Must | P1 |
| BILL-05 | Usage breakdown per employee | Should | P1 |
| BILL-06 | Voice tier per employee (Smart ₹3 · Natural ₹4.5 · Signature ₹6 per min) | Must | P1 |
| BILL-07 | Top-up bonus credits by amount | Should | P1 |
| BILL-08 | Spend estimate & monthly cap ("Stop outbound calls after ₹X this month") | Must | P1 |
| BILL-09 | Pass-through extras shown upfront (number rental, WhatsApp fees, verification) | Must | P1 |

## 17. Agency & Studio (`AGY`, `STU`)

| ID | Feature | Pri | Ph |
|---|---|---|---|
| AGY-01 | Partner sign-up & approval | Must | P3 |
| AGY-02 | White-label: logo, colours, domain, email/WhatsApp sender | Must | P3 |
| AGY-03 | Client sub-accounts; switch between clients | Must | P3 |
| AGY-04 | Client billing: agency sets retail price; wholesale billed to agency | Must | P3 |
| AGY-05 | Multi-client dashboard (usage, health, alerts) | Must | P3 |
| AGY-06 | Template library: save/share teams & routines across clients | Should | P3 |
| AGY-07 | Marketplace: publish templates (revenue share) | Could | P3 |
| STU-01 | Studio Mode toggle (advanced editor, never default) | Must | P3 |
| STU-02 | Custom handoff conditions & variables | Should | P3 |
| STU-03 | Custom actions (HTTP), webhooks, API keys | Should | P3 |
| STU-04 | Test suite: simulated callers, regression runs | Should | P3 |
| STU-05 | Choose voice/speech/AI providers (advanced) | Could | P3 |

## 18. Website, help & mobile (`WEB`, `SUP`, `MOB`)

| ID | Feature | Pri | Ph |
|---|---|---|---|
| WEB-01 | Landing page with **"Call me now" live demo** (enter number → Mitra calls in 30 s, in chosen language) | Must | P1 |
| WEB-02 | Industry pages (Clinics, Real estate, Coaching, Agencies) with sample call audio | Must | P1 |
| WEB-03 | Pricing page: per-minute tiers + calculator ("calls a day × minutes" → monthly estimate, vs. telecaller salary) | Must | P1 |
| WEB-04 | Telugu / Hindi versions of site | Should | P1 |
| SUP-01 | In-app help in plain language + WhatsApp support | Must | P1 |
| SUP-02 | Contextual tips (one at a time, dismissible) | Should | P1 |
| MOB-01 | Installable PWA (mobile-first web app) | Must | P1 |
| MOB-02 | Native app (iOS/Android) with push + live call takeover | Could | P3 |

## 19. Competitive gap features (added 2 Nov 2026)

From a public-feature review of Outpero (outpero.com) and Decibyl (decibyl.ai and its public GitHub PR notes). Features only, built our own way; no competitor code is used.

| ID | Feature | Detail | Priority | Phase |
|---|---|---|---|---|
| INT-12 | Lead intake API | `POST /lead-intake/{slug}` with per-business secret header, 202 response, dedupe within minutes, fields become call variables | Must | P1 |
| INT-13 | Outgoing signed webhooks | `call.ended`, `lead.created`, `campaign.finished`; HMAC-SHA256 signature, custom headers, retries, delivery log | Must | P1 |
| INT-14 | Indian lead portals | IndiaMART, JustDial, Google Ads lead forms, Google Forms, WordPress/Wix form plugin, Sell.Do | Should | P1 |
| ACT-09 | Live data lookup in call | Read-only CRM / Sheet / HTTP lookup mid-call (EMI, stock, slot) with owner-approved fields only | Should | P2 |
| CALL-15 | Campaign controls | CSV upload or paste, column → script variables, sample CSV, skip contacts called in last N days, days/holidays calendar, retry ladder, pause/edit/extend live, ETA by channel count, result buckets + export | Must | P1 |
| CALL-16 | Auto-pause on carrier refusal | Stop a campaign when the carrier rejects or spam-flags calls; alert owner | Must | P1 |
| CALL-17 | Voice broadcast | Non-AI recorded message to a list (cheaper tier), same compliance gate | Could | P2 |
| CALL-18 | Listen & whisper | Supervisor listens live and types a private instruction the AI follows, or takes over | Should | P2 |
| CALL-19 | Escalation ladder | Transfer tries staff A → B → owner, then takes a message and hands back to AI; shows a hand-off card | Must | P2 |
| CALL-20 | Missed-call number | "Give a missed call on 040-xxxx" → Mitra calls back in 1 min (free for caller) | Should | P2 |
| ACT-11 | UPI collections with auto-matching | Employee sends a UPI/Razorpay payment link during or after the call; payment webhook marks the bill paid, thanks the customer on WhatsApp and stops reminders; unpaid links feed a reminder routine | Must | P2 |
| VOICE-17 | More languages | Tamil, Kannada, Malayalam, Marathi (after te/hi/en quality bar is met) | Should | P2 |
| EMP-12 | "Polish my script" | One tap adds language-correct politeness (garu/andi, ji/aap) and Indian number style | Should | P1 |
| EMP-13 | Build any role from one line | Owner describes a custom role; Mitra drafts a spec card (steps, fields, hand-offs, schedule) for review before creating it | Should | P2 |
| MGR-08 | In-app "Ask Mitra" thread | Same manager as WhatsApp inside the app, with openers "What happened this week?" / "What needs my attention today?" | Must | P2 |
| MGR-09 | "Call me when it's done" | Mitra phones the owner with the result of a long routine or campaign | Could | P2 |
| APPR-06 | Safe approvals | Approval cards bound to one version and usable once; a spoken "yes" on a call is never an approval; owner can edit before approving | Must | P2 |
| CHAN-01 | WhatsApp chat employee | The same employee answers WhatsApp text and voice notes with shared memory | Must | P2 |
| CHAN-02 | Website chat & Instagram DMs | Embeddable web chat widget and Instagram messages answered by the employee | Should | P3 |
| ACT-10 | Google review request | After a happy call, send a review link (within Google's rules: ask everyone, no gating) | Should | P2 |
| REP-07 | Auto QA score | Every call scored (greeting, facts grounded, next step, politeness); low scores surfaced for coaching | Should | P2 |
