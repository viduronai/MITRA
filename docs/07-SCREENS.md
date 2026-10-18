# 07 · Screens & Information Architecture

Covers the marketing site and the web app (mobile-first PWA). Components from [06-DESIGN-SYSTEM.md](06-DESIGN-SYSTEM.md).

---

## 1. Information architecture (app)

```
Home (Today)
Calls
  └ Call detail
Team  (P1: "My employee", P2: "My team")
  ├ Employee detail → Behaviour · What they know · Voice · Hours · Results · History
  └ Team map (P2)
Customers
  └ Customer timeline
Routines (P2)
Approvals (P2, also via WhatsApp)
Connect (integrations, numbers)
More
  ├ Billing & minutes
  ├ Business profile & branches
  ├ People & access
  ├ Compliance (consent, opt-outs, data requests)
  ├ Language & appearance
  └ Help & WhatsApp support
Agency console (P3, separate shell)
```

**Navigation:** mobile bottom bar = Home · Calls · Team · Customers · More. Desktop sidebar adds Routines, Approvals, Connect.

## 2. Marketing site

### 2.1 Pages
`/` Home · `/clinics` · `/real-estate` · `/education` · `/agencies` · `/pricing` · `/how-it-works` · `/safety` (compliance & trust) · `/about` · `/blog` · `/te` and `/hi` localised versions · legal pages.

### 2.2 Creative direction — "alive, not a template"

**Mandate from founders:** the marketing site must **not** look like typical AI-calling SaaS sites (Outpero, Bolna and similar: hero + feature grid + logos + pricing). It must feel as premium and alive as **Apple, Google Antigravity and GitHub** product pages.

| Reference | What we take from it |
|---|---|
| **Apple** product pages | Cinematic **scroll storytelling**: one idea per full-screen moment, huge confident typography, product as hero, scroll-pinned sequences, generous whitespace, restraint |
| **Google Antigravity** | A sense of **living, floating space**: soft particles and depth, calm dark canvas, elements that react gently to cursor and scroll |
| **GitHub** homepage | **Glowing depth and real product UI**: dark gradients, light beams, real interface shots that animate in, a large showpiece visual (their globe → our "voice sphere") |

**Signature concept: "The Voice Sphere."** A live, breathing 3D orb of particles in sky blue and Mitra Blue, made from sound. It ripples when Mitra "speaks" (sample audio playing), calms when idle, and follows the cursor slightly. **v2: it now lives in the "Hear it" scene. The full scene plan is in [design/landing-direction.md](design/landing-direction.md).**

**Scroll story (replaces the generic section list below as the primary structure):**
1. **Silence → a phone rings** (dark screen, a single ringing sound visual) → *"Every missed call is a missed customer."*
2. **The Voice Sphere wakes up** → *"Meet Mitra. Your AI employee who sounds like your best staff."* + **Call me now**
3. **Hear it** — pinned section: real call audio plays, transcript types along in Telugu/Hindi/English, the sphere pulses with the voice
4. **One call becomes a team** — the sphere splits into four smaller orbs (Lead Caller → Visit Coordinator → Sales Assistant → Payment Caller) connected by light beams
5. **Run it from WhatsApp** — a phone floats in 3D; the Manager chat plays out as you scroll
6. **Your number. Your name.** — a lock-screen incoming call showing "Sunrise Clinic ✓" (Trusted Caller ID)
7. **₹3 a minute. Nothing else.** — huge numerals, pricing as a statement
8. **Final CTA** — the sphere returns; "Your phone rings. Mitra answers."

**Craft rules:**
- **Sources:** 21st.dev (heroes, interactive and 3D components, shaders, gradients), MotionSites.ai prompts (animated hero backgrounds, 3D sections), Aceternity/Magic UI for beams and spotlights. Everything is restyled to Mitra tokens, with no stock-template look.
- **Tech:** Next.js + Motion (scroll-linked animation), React Three Fiber/three.js or WebGL shaders for the sphere, Lenis for smooth scrolling, GSAP ScrollTrigger only if Motion can't handle a pinned sequence.
- **Dark-first** marketing canvas with light sections for contrast moments. Display typography: 72–120 px desktop with tight tracking.
- **Sound design:** opt-in sound toggle; voice samples are the "music" of the page.
- **Performance is part of premium:** LCP ≤ 2.0 s on 4G mid-range Android. The sphere renders at reduced particle count on mobile, with a static poster fallback for low-end devices or `prefers-reduced-motion`. 3D is lazy-loaded after first paint.
- **No clichés:** no stock photos of headset agents, no generic robot illustrations, no "AI-powered" buzzword copy.

### 2.3 Home page — content checklist (sections that must exist inside the story)

| # | Section | Content | Suggested source / effect |
|---|---|---|---|
| 1 | Sticky header | Logo · Industries · Pricing · Agencies · Login · **Try free** | Glass blur on scroll |
| 2 | **Hero** | H1: "Hire an AI employee who sounds like your best staff." Sub: "Answers every call, calls every lead, does the follow-up — in Telugu, Hindi and English." **Primary: "Call me now"** (live demo) · Secondary: "Hear sample calls" | Aceternity spotlight / background beams, React Bits text reveal, Vexel-style horizon video + masked headline (see design/landing-direction.md) |
| 3 | **Live demo module** | Phone input + language chips + industry chips → "Mitra will call you in 30 seconds" + live status (Dialling… Connected… Call ended → see your summary) | Custom; shimmer button (Magic UI) |
| 4 | Sample calls | 4 cards (Clinic · Real estate · Coaching · Payments) with waveform players + transcript toggle; language switch | Custom audio card |
| 5 | Logo / proof strip | Early customers, partner logos, "Calls handled" ticker | Magic UI marquee + number ticker |
| 6 | How it works | 3 steps: Teach → Test → Go live, each with tiny looping UI video | Bento or stepper |
| 7 | **AI team** | Animated team map: Lead Caller → Visit Coordinator → Sales Assistant → Payment Caller | Magic UI animated beam |
| 8 | **Run it from WhatsApp** | Phone mockup with Manager chat animation (report, approval, voice-note command) | Device frame + scripted chat |
| 9 | Industries | Clinic / Real estate / Education / Agencies cards → industry pages | 21st.dev feature cards |
| 10 | Human-grade voice | "Listen for yourself" A/B: Mitra vs typical robotic AI | Two players |
| 11 | Trust & compliance | AI disclosure, India data storage, consent, DND — plain words + badges | Simple icons grid |
| 12 | Pricing teaser | 3 plans + "Calculate my cost" | Origin UI pricing |
| 13 | Testimonials | Short quotes with audio of owner speaking (P2) | 21st.dev testimonial |
| 14 | FAQ | 8 questions in plain language | Accordion |
| 15 | Final CTA | "Your phone rings. Mitra answers." + Call me now | Spotlight |
| 16 | Footer | Links, language switch, WhatsApp us, legal | — |

**Performance budget:** LCP ≤ 2.0 s on 4G Moto-G-class; heavy effects lazy-loaded below the fold; hero effect has static fallback.

### 2.4 Pricing page
Headline: **"Pay only when Mitra talks. From ₹3 a minute. No monthly fee."**
Three tier cards (Smart ₹3 · **Natural ₹4.5** highlighted · Signature ₹6) each with ▶ voice sample, "All features included" strip. **Calculator:** "Calls per day [slider] · Avg minutes [slider] · Tier" → "≈ ₹X/month" + comparison "A telecaller costs ≈ ₹18,000/month". Top-up bonus table, pass-through extras listed plainly, FAQs on per-second billing, unanswered calls free, numbers, GST.

### 2.5 Agencies page
Pitch: "Sell AI calling teams under your brand." Margin calculator, white-label preview (logo/colour swap demo), partner application form.

## 3. App — Phase 1 screens

### 3.1 Sign up / Login
- Phone number → OTP (6 boxes, auto-read on Android) · "Continue with Google".
- Language toggle (EN/తెలుగు/हिंदी) top-right.

### 3.2 Onboarding (5-step stepper, progress saved)
1. **Your business** — Name, Industry (icon grid), City, Languages customers speak (chips), Working hours (pre-set 9–9). Optional "Paste Google Business link to auto-fill".
2. **Choose a role** — 4 large cards with one-line description + ▶ sample. Default highlighted by industry (clinic → Receptionist; real estate → Lead Caller).
3. **Teach Mitra** — three equal options: 🔗 Paste link · 📄 Upload / photo · 🎤 Speak for 2 minutes. Shows progress "Reading your website…" then **What they know** cards to review (✓ correct / ✎ edit). Unknowns highlighted: "What is your consultation fee?"
4. **Pick a voice** — Voice cards filtered by business languages; samples generated with the business's own name & info ("Namaskaram, Sunrise Clinic nunchi…"). Name the employee (prefilled).
5. **Test call** — Big button "Call my phone (98xxxxxx21)". Live status + live transcript. After call: summary + "Anything to fix?" (mic button / text) → applied → "Test again" or "Looks good".
6. **Go live** (finish) — three cards: Forward my missed calls (shows exact codes for Jio/Airtel/Vi/BSNL, "Test forwarding" button) · Get a local business number (city code, KYC, then **"Show my name when calling"**: Truecaller verification + CNAP name, with a phone-screen preview) · Connect my leads (Facebook / Website / Google Sheet). Success screen with confetti-lite + "Your first report arrives tomorrow 8 am on WhatsApp".

### 3.3 Home (Today)
- Greeting + date + status line: "Priya is working · 2 calls live".
- **Stat tiles (2×2):** Calls today · Booked · Missed calls rescued · Needs you.
- **Needs you** list (unknown questions, angry callers, failed actions) — each with one action.
- **Live now** strip (P2) with listen-in.
- Recent calls (5) → Calls.
- Setup checklist card until 100%.

### 3.4 Calls
- Filters as chips: Today · Booked · Interested · Call back · Missed · All results ▾ · Employee ▾ · Language ▾. Search transcripts.
- Call rows (see components).
- **Call detail:** header (contact, result pill, time, duration, employee) → audio player → summary (3 bullets) → collected info → **What was said** transcript → actions taken (WhatsApp sent, Booked 6:15 pm) → 👍/👎 + "Teach Priya something from this call".

### 3.5 Employee detail (tabs)
- **Overview:** status toggle (Working/Paused), today's results, ▶ sample.
- **Behaviour:** guided sections (Greeting · What to ask · How to answer · Never say · When to transfer) each as editable sentences; "Improve with AI" suggestions; version history.
- **What they know:** knowledge cards by category; sources list; unknown-question inbox.
- **Voice:** current voice, change voice, speaking speed (slower/normal/faster), formality (Friendly/Respectful/Formal), languages.
- **Hours & routing:** working hours, holidays, out-of-hours behaviour, transfer numbers.
- **Results:** result types & questions to collect.

### 3.6 Customers
- List with search, tags (Hot lead, Patient, VIP), last contact, next step.
- **Customer timeline:** profile header (name, phone masked, language) → memory ("Prefers evening calls · Budget 60–70L · Asked about 3BHK") with confirmed/guessed badges, edit/forget → chronological events.

### 3.7 Connect
- **Phone numbers — "Trusted Caller ID" card:** number, KYC status, ✓ Truecaller verified, ✓ CNAP name, answer rate (7 days) with health pill (Healthy / Watch / Paused), forwarding test, "What customers see" phone mockup preview · Lead sources · Calendar · Sheets · WhatsApp · Zapier/Pabbly · (P2 CRM, payments). Each = logo card + Connect button + plain-language "what this does".

### 3.8 Billing & minutes
- Wallet balance (big number, ≈ minutes left at current tiers) · Top up (UPI, bonus shown) · auto top-up toggle · monthly spend cap · "This month so far ₹X" · voice tier per employee · usage by day/employee · extras (number rental, WhatsApp fees) · invoices (GST).

### 3.9 Compliance (simple view)
- Toggles with plain explanations: AI introduction line (always on, editable wording), recording notice, calling hours, opt-out list, data requests queue, consent log export.

## 4. App — Phase 2 screens
- **Team map** (hire team template, edit handoffs as sentences, per-node stats).
- **Routines** list + sentence builder + dry run + history.
- **Approvals** inbox (also WhatsApp) + rules ("Ask me first when…").
- **Call a list** (upload CSV/Sheet → map columns with smart guess → choose employee & goal → compliance summary "142 can be called · 18 on DND removed" → schedule).
- **Insights** funnel, source ROI, top questions.
- **Live call view** with takeover.

## 5. Agency console — Phase 3
- Clients grid (health, minutes, results, alerts) · Add client wizard (template + branding inherits) · Templates library · Pricing & margins · Billing (wholesale vs retail) · Brand settings (logo, colours, domain, sender) · Team & roles.
- **Studio Mode** (per client, behind toggle): advanced behaviour editor, variables, custom actions, test suites, provider choice.

## 6. WhatsApp Manager — message designs

| Message | Format |
|---|---|
| Daily report | Header "☀️ Sunrise Clinic · Sat 18 Oct" → 4 lines of numbers → "2 need you" → buttons [See details] [Pause all] |
| Approval | Context + amount + customer → [Approve] [Decline] [Call myself] |
| Hot lead alert | Name, need, budget, language → [Call now] [Assign to Ravi] |
| Coaching confirmation | "I'll change: … " → [Confirm] [Edit] |
| Answer to question | Direct answer first, then link "Open in app" |

Rules: ≤ 6 lines per message, numbers first, local language of the owner, emoji only as category markers.

## 7. States every screen must define
Loading (skeleton) · Empty (illustration + one action) · Error (plain cause + fix) · Partial (some sources failed) · Offline (cached read-only + banner) · Permission-limited (staff role).
