# 03 · User Flows

How each person moves through Mitra. Diagrams use Mermaid (renders on GitHub, VS Code, Notion).
Rule for every flow: **one primary action per screen, a sensible default for every choice, and a way back.**

---

## 1. Visitor → trial (landing page)

```mermaid
flowchart LR
  A[Lands on mitra site] --> B{Hears sample calls<br/>in their language}
  B --> C[Clicks 'Call me now']
  C --> D[Enters phone + picks language + industry]
  D --> E[Mitra calls within 30 s<br/>demo for their industry]
  E --> F{Impressed?}
  F -- yes --> G[Start free trial<br/>phone OTP]
  F -- not yet --> H[Book a demo / WhatsApp us]
  G --> I[Onboarding flow §2]
```

**Key moment:** the live demo call is the product's best salesperson. It must work flawlessly, in Telugu, Hindi, and English.

## 2. Owner onboarding (Phase 1) — target ≤ 10 minutes

```mermaid
flowchart TD
  S[Sign up: phone OTP] --> P[Business basics<br/>name · industry · city · languages · hours]
  P --> R[Pick a role<br/>Receptionist / Lead Caller / Reminder / Payment]
  R --> T{Teach Mitra about your business}
  T -->|Paste link| T1[Website / Google Business]
  T -->|Upload| T2[PDF · photo of price list]
  T -->|Speak| T3[2-min voice note]
  T1 & T2 & T3 --> K[Review 'What they know' cards<br/>edit anything wrong]
  K --> V[Pick a voice<br/>hear samples using YOUR business info]
  V --> C[Test call to my phone]
  C --> Q{Happy?}
  Q -- no --> X[Say/type a correction] --> C
  Q -- yes --> G{Go live how?}
  G -->|Missed calls| G1[Forward-on-busy/no-answer<br/>operator-specific codes shown]
  G -->|New number| G2[Get local business number + KYC<br/>→ verify name: Truecaller + CNAP]
  G -->|Leads| G3[Connect Facebook Leads / form / Sheet]
  G1 & G2 & G3 --> L[🎉 Live — first WhatsApp report tomorrow 8am]
```

Screen-level detail in [07-SCREENS.md](07-SCREENS.md) §3.

**Edge cases**
- No website → skip to photo/voice note; industry starter pack fills common FAQs.
- Test call not answered → retry button + "Call my other number".
- KYC pending for new number → allow go-live via call forwarding meanwhile.
- Owner abandons mid-way → WhatsApp nudge after 2 h with deep link to the exact step.

## 3. A day with Mitra — owner on WhatsApp

```mermaid
sequenceDiagram
  participant M as Mitra Manager (WhatsApp)
  participant O as Owner
  M->>O: 8:00 Daily report: 38 calls · 9 booked · 2 need you
  O->>M: 🎤 "Who are the 2?"
  M->>O: 1) Mr. Rao wants 10% discount [Approve][Decline]<br/>2) Angry caller about wait time [Listen][Call back myself]
  O->>M: taps Approve
  M->>O: Done. Priya will call Mr. Rao now.
  O->>M: 🎤 "Tell everyone parking is in the basement from tomorrow"
  M->>O: I'll add: "Parking: basement, from 19 Oct". [Confirm][Edit]
  O->>M: Confirm
  M->>O: ✅ All employees updated.
```

## 4. Inbound call (caller's experience)

```mermaid
sequenceDiagram
  participant C as Caller
  participant E as Priya (AI Receptionist)
  C->>E: Rings clinic (owner busy / after hours)
  E->>C: "Namaskaram, Sunrise Clinic nunchi Priya, AI assistant ni. Ela help cheyagalanu?"
  C->>E: "Doctor appointment kavali, tomorrow evening"
  E->>C: "Sure andi… (checks calendar) 5:30 or 6:15 available. Edi convenient?"
  C->>E: "6:15"
  E->>C: Confirms name, sends WhatsApp confirmation with location
  Note over E: Logs result=Booked, updates memory,<br/>schedules reminder (Reminder Caller in Phase 2)
```

Escape hatches at any point: caller says "talk to a person" → warm transfer (or message if no one free); caller says "don't call me" → suppressed.

## 5. Lead calling (real estate)

```mermaid
flowchart LR
  L[New Facebook lead] -->|< 60 s| A[Lead Caller calls]
  A --> B{Answered?}
  B -- no --> R[Retry plan: 10 min, 2 h, next day<br/>+ WhatsApp 'tried calling you']
  B -- yes --> Q[Qualify: budget · location · timeline · BHK]
  Q --> D{Interested?}
  D -- hot --> H[Book site visit + alert sales team on WhatsApp]
  D -- warm --> W[Send brochure, callback in 3 days]
  D -- not interested --> N[Mark result, stop]
  H --> P[Phase 2: Visit Coordinator takes over]
```

## 6. Correcting a mistake (trust loop)

```mermaid
flowchart LR
  A[Owner reads summary / listens] --> B[Taps 👎 or replies with voice note]
  B --> C[Mitra proposes change in plain words<br/>'Next time say fee is ₹500, not ₹400']
  C --> D{Confirm?}
  D -- yes --> E[Behaviour/knowledge updated<br/>version saved]
  D -- edit --> C
  E --> F[Optional: 'Test it now' call]
```

## 7. Building an AI team (Phase 2)

```mermaid
flowchart TD
  A[Team page: 'Hire a team'] --> B[Choose industry template<br/>e.g. Real estate team]
  B --> C[See team map:<br/>Lead Caller → Visit Coordinator → Sales Assistant → Payment Caller]
  C --> D[For each member: keep defaults or change voice/name]
  D --> E[Review handoffs in sentences<br/>'When interested → Visit Coordinator books visit']
  E --> F[Choose 'Ask me first' items<br/>discounts · cancellations]
  F --> G[Test whole journey with simulated lead]
  G --> H[Activate team]
```

## 8. Creating a routine (Phase 2)

```mermaid
flowchart LR
  A[Routines → New] --> B{Start from library<br/>or write a sentence}
  B --> C["Every [day] at [6 pm] → [Reminder Caller]<br/>calls [tomorrow's appointments] to [confirm]"]
  C --> D[Dry run: shows 14 people who'd be called]
  D --> E[Turn on]
```
Also creatable by WhatsApp: *"Every evening call tomorrow's patients to confirm"* → Manager drafts routine → owner confirms.

## 9. Staff member (front-desk) flow

```mermaid
flowchart LR
  A[Gets WhatsApp: Hot lead / transfer] --> B{Transfer call?}
  B -- yes --> C[Hears whisper summary] --> D[Talks to customer]
  B -- no, brief --> E[Reads brief before visit]
  D & E --> F[Marks outcome in app or replies 'visited' on WhatsApp]
```

## 10. Agency flow (Phase 3)

```mermaid
flowchart TD
  A[Agency applies as partner] --> B[Approved → sets brand: logo, colours, domain]
  B --> C[Sets retail pricing & margins]
  C --> D[Adds client → picks team template]
  D --> E[Imports client knowledge + connects client's ad account]
  E --> F[Client gets branded login + WhatsApp Manager]
  F --> G[Agency dashboard: all clients' calls, health, usage, billing]
```

## 11. Billing & low balance

```mermaid
flowchart LR
  A[Talk-time billed per second × voice-tier rate] --> B{Balance < 20%?}
  B -- yes --> C[WhatsApp: 'Top up?' with UPI link]
  C --> D{Auto top-up on?}
  D -- yes --> E[Charged via UPI AutoPay]
  D -- no --> F[At 0: employees finish current calls,<br/>new outbound paused, inbound → take message]
```
Inbound calls must **never** silently fail — at zero balance, Mitra still takes a short message (grace minutes).

## 12. Data deletion request (customer of the business)

Caller: "Delete my data" → employee confirms → request logged → owner notified → erasure job within SLA → confirmation WhatsApp to caller. See [08](08-COMPLIANCE-SECURITY.md).
