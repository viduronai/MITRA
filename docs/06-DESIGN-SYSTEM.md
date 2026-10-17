# 06 · Design System — "Mitra UI"

Direction: **clean, neat, premium, calm.** Think a well-run private clinic reception, not a cockpit.
Built on **Tailwind CSS v4 tokens + shadcn/ui (Radix)**, extended with curated components (see §9).

---

## 1. Design principles

| # | Principle | In practice |
|---|---|---|
| 1 | **One thing per screen** | One primary button per view. Secondary actions are quiet (ghost/link). |
| 2 | **Talk like a person** | "Priya booked 9 appointments today", not "9 conversions (agent_id 42)". Glossary in [00 §5](00-README.md) is law. |
| 3 | **Show, then let them change** | Every setting starts with a good default, shown as a sentence the owner can tap to change. |
| 4 | **Hear it** | Anything about voice has a ▶ play button. Never describe a voice without letting them listen. |
| 5 | **Calm confidence** | Lots of white space, few colours, soft motion. No dense tables on mobile, no red unless something is truly wrong. |
| 6 | **Always reversible** | Undo, version history, "pause" one tap away. Owners must feel safe experimenting. |
| 7 | **Mobile-first, 4G-first** | Designed at 360 px first; fast on mid-range Android; works one-handed. |
| 8 | **Bharat-ready** | UI in English, Telugu, Hindi; Indic scripts render beautifully; ₹, lakh/crore, DD MMM formats. |

**The Grandmother test:** a non-technical owner can complete the task, unaided, on a phone, in under 2 minutes. Every new screen is tested this way before shipping.

## 2. Brand

- **Name:** Mitra (మిత్ర · मित्र) — friend.
- **Personality:** warm, dependable, quietly premium, never gimmicky.
- **Logo direction:** wordmark "mitra" in rounded geometric sans + a minimal sound-wave dot motif (three dots forming a smile/wave). Works in one colour.
- **Voice of copy:** short sentences, second person, positive, no jargon, no exclamation overload (max one per screen).

## 3. Colour tokens

Neutral-led palette with one confident brand colour and one warm accent.

### 3.1 Brand
| Token | Light | Dark | Use |
|---|---|---|---|
| `--brand-50` | `#EEF0FF` | `#14152E` | subtle fills |
| `--brand-100` | `#DCE0FF` | `#1C1E40` | selected rows |
| `--brand-500` | `#4B4DED` | `#7C7EFF` | focus rings, links |
| `--brand-600` | `#3B3BD6` | `#8E90FF` | **primary buttons** |
| `--brand-700` | `#2F2FB0` | `#A7A9FF` | hover/pressed |
| `--accent-400` | `#F7B84B` | `#F7B84B` | "Marigold" — highlights, live/voice moments, celebrations |
| `--accent-100` | `#FFF3DC` | `#3A2C10` | accent backgrounds |

### 3.2 Neutrals (warm grey "Stone")
| Token | Light | Dark |
|---|---|---|
| `--bg` | `#FBFBFA` | `#0B0B0D` |
| `--surface` | `#FFFFFF` | `#141417` |
| `--surface-2` | `#F4F4F2` | `#1B1B1F` |
| `--border` | `#E7E6E3` | `#2A2A30` |
| `--text` | `#17171A` | `#F2F2F3` |
| `--text-muted` | `#5F5E66` | `#A1A0A8` |
| `--text-subtle` | `#8C8B93` | `#76757D` |

### 3.3 Semantic
| Token | Light | Dark | Meaning |
|---|---|---|---|
| `--success` | `#12A150` | `#3DD68C` | Booked, live, connected |
| `--warning` | `#D98E04` | `#F5B83D` | Needs attention, low balance |
| `--danger` | `#DC3545` | `#FF6B6B` | Failed, blocked, destructive |
| `--info` | `#2F7FE0` | `#6AA8FF` | Neutral notices |

Rules: text contrast ≥ 4.5:1; brand colour only on the single primary action + key highlights; status always paired with icon + label (never colour alone).

Implementation (Tailwind v4):
```css
@import "tailwindcss";
@theme {
  --color-brand-600: #3B3BD6;
  --color-accent-400: #F7B84B;
  --font-sans: "Inter Variable", "Noto Sans Telugu", "Noto Sans Devanagari", system-ui, sans-serif;
  --font-display: "Geist", "Inter Variable", sans-serif;
  --radius-card: 1rem;
}
:root { --bg: #FBFBFA; /* …all tokens… */ }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { --bg: #0B0B0D; } }
:root[data-theme="dark"] { --bg: #0B0B0D; }
```

## 4. Typography

| Role | Font | Size / line-height (mobile → desktop) | Weight |
|---|---|---|---|
| Display (marketing hero) | Geist | 40/44 → 72/76, tracking -2% | 600 |
| H1 | Geist | 28/34 → 36/42 | 600 |
| H2 | Geist | 22/28 → 28/34 | 600 |
| H3 | Inter | 18/26 → 20/28 | 600 |
| Body L | Inter | 17/26 | 400 |
| Body (default) | Inter | 15/24 → 16/24 | 400 |
| Small | Inter | 13/20 | 400–500 |
| Numbers / stats | Inter (tabular-nums) | 32/36 → 44/48 | 600 |

- **Indic scripts:** Noto Sans Telugu / Devanagari / Tamil / Kannada / Malayalam with +10% line-height when script ≠ Latin (`:lang(te) { line-height: 1.7 }`).
- Minimum body size on mobile: 15 px. Never all-caps for Indic.
- Load via `next/font` with `display: swap`, subset per locale.

## 5. Spacing, layout, shape, depth

- **Spacing scale (4 px base):** 4, 8, 12, 16, 20, 24, 32, 40, 48, 64, 80, 96.
- **Mobile gutter:** 16 px. **Desktop container:** 1200 px max (app), 1280 px (marketing).
- **Grid:** 4-col mobile, 8-col tablet, 12-col desktop.
- **Radius:** inputs/buttons 12 px · cards 16 px · sheets/modals 24 px · avatars/pills full.
- **Elevation (soft, warm):**
  - `shadow-xs`: `0 1px 2px rgba(23,23,26,.05)`
  - `shadow-sm`: `0 2px 8px rgba(23,23,26,.06)`
  - `shadow-md`: `0 8px 24px rgba(23,23,26,.08)` (popovers)
  - `shadow-lg`: `0 24px 48px rgba(23,23,26,.12)` (modals)
- Prefer **borders + subtle background** over heavy shadows. Glass/blur only on marketing hero & sticky headers.

## 6. Iconography & illustration

- **Icons:** Lucide (default shadcn) at 20 px / 1.75 stroke; Phosphor duotone for empty states.
- **Avatars for AI employees:** soft gradient circles with initials + subtle animated sound ring when speaking (no fake human photos — honesty principle).
- **Illustrations:** simple line + Marigold accent; Lottie for onboarding success, empty states.
- **Logos of integrations:** official marks, monochrome until hovered.

## 7. Motion

| Token | Duration | Easing | Use |
|---|---|---|---|
| `motion-fast` | 120 ms | `cubic-bezier(.2,0,0,1)` | hovers, toggles |
| `motion-base` | 200 ms | `cubic-bezier(.2,0,0,1)` | dropdowns, tabs |
| `motion-slow` | 320 ms | `cubic-bezier(.16,1,.3,1)` | sheets, modals, page transitions |
| `motion-spring` | spring(stiffness 380, damping 30) | — | cards, drag, success |

Rules: motion explains (where something came from/went); never decorative inside the app; marketing can be expressive. **Respect `prefers-reduced-motion`** — swap to fades. Voice waveform animations run only while audio is actually playing.

## 8. Core components (app)

Base: shadcn/ui. Each has light/dark, sizes, states (default, hover, focus-visible, active, disabled, loading, error).

| Component | Notes |
|---|---|
| Button | `primary` (brand), `secondary` (surface + border), `ghost`, `danger`, `link`; sizes 40/48/56 px height (56 = mobile primary CTA, full width) |
| Input, Textarea, Select, Combobox | 48 px height, label above, helper text below, inline validation |
| **Sentence builder** | Inline chips inside a sentence ("Every **[day]** at **[6 pm]**, **[Meena]** calls **[tomorrow's patients]**") — tapping a chip opens a bottom sheet picker. Core pattern for routines, handoffs, rules |
| Card | 16 px radius, 20–24 px padding; clickable cards have hover lift 2 px |
| **Stat tile** | Big number + label + tiny trend; tap → filtered list |
| **Employee card** | Avatar + name + role + status pill + "Listen to a sample" + today's results |
| **Voice card** | Name, personality line, language/dialect chips, ▶ sample with waveform, select radio |
| **Call row** | Contact, employee avatar, result pill, duration, time; tap → call detail |
| **Transcript bubble** | Caller (left, neutral) vs employee (right, brand-50), timestamp, ▶ jump-to-audio |
| **Audio player** | Waveform scrubber, 1×/1.5×/2×, skip silence |
| **Result pill** | Booked (success), Interested (brand), Call back (info), Not interested (neutral), Failed (danger) |
| **Approval card** | Who/what/why + Approve (primary) / Decline (secondary) / Call myself (ghost) |
| **Team map** | Horizontal flow of employee nodes with arrows + counts; vertical stack on mobile |
| **Timeline** | Customer journey events with icons (call, WhatsApp, handoff, booking, payment) |
| **Knowledge card** | Category icon + facts list + "Edit" + source badge ("from website") |
| Checklist / Stepper | Onboarding progress, 5 steps max |
| Bottom sheet (mobile) / Dialog (desktop) | Same component, responsive |
| Toast | Bottom-centre mobile, bottom-right desktop; includes Undo where possible |
| Empty state | Illustration + one sentence + one action |
| Skeletons | For every async list/card; no spinners > 300 ms |
| Tabs, Segmented control | Max 4 options |
| Navigation | Mobile: bottom tab bar (Home, Calls, Team, Customers, More). Desktop: left sidebar collapsible |
| Live indicator | Pulsing Marigold dot when an employee is on a call |

## 9. Component & inspiration sources (curated)

All are "copy-in source" or prompt resources, so we own the code and must restyle to our tokens.

| Source | Use it for | Notes |
|---|---|---|
| **shadcn/ui** | App foundation (forms, dialogs, tables, sheets, charts) | Base layer for everything |
| **21st.dev** | Community React + Tailwind + shadcn components, heroes, pricing, testimonials, templates; install via shadcn CLI or `npx @21st-dev/cli init --client claude` for coding agents | Free tier has daily copy limits; membership for premium |
| **Magic UI** | Marketing motion: marquee (logos), animated beams (integration diagram), bento grid, number ticker, shimmer button | Open source |
| **Aceternity UI** | Hero effects: spotlight, background beams, 3D/hover cards, text generate | Free + paid blocks |
| **React Bits** | Text animations, subtle cursor/scroll effects; has reduced-motion controls | Good for hero headline |
| **Origin UI** | Polished inputs, OTP, pricing, tables, auth blocks | shadcn-compatible |
| **Motion Primitives / Cult UI / Kibo UI** | Micro-interactions, special components (e.g. Kibo for dropzone, code blocks) | Use sparingly |
| **Tailark** | shadcn marketing blocks (feature, CTA, footer sections) | Fast landing assembly |
| **MotionSites.ai** | Prompt library for animated hero/backgrounds & 3D sections for AI builders (Claude, Cursor, Lovable) | Inspiration + prompts, not a component library |
| **Lottie / LottieFiles** | Success, empty states, onboarding illustrations | — |
| **Mobbin, Refero, Godly, Land-book** | Pattern & visual inspiration (fintech/healthtech onboarding, dashboards) | Reference only |

**Rules for using external components:** (1) restyle to Mitra tokens — no foreign colours/fonts, (2) remove effects that hurt performance on mid-range Android, (3) add reduced-motion fallback, (4) keep accessibility (focus, labels, ARIA), (5) record source + licence in `packages/ui/SOURCES.md`.

## 10. Content & copy rules

- Sentence case everywhere. Buttons start with a verb: "Hear sample", "Start test call", "Go live".
- Numbers first: "9 booked", "3 need you".
- Never blame the user. Errors explain + fix: "We couldn't reach your number. Check it and try again."
- Indian formats: ₹1,20,000 · 1.2 lakh · 18 Oct · 6:15 pm.
- Translations: written by native speakers (not raw machine translation) for TE/HI; keep English loanwords people actually use ("appointment", "booking").

## 11. Accessibility

WCAG 2.2 AA: contrast, focus-visible rings (2 px brand-500 + 2 px offset), 44×44 px touch targets, labels for every input, captions/transcripts for every audio, keyboard paths for all flows, `lang` attribute per text for correct screen-reader voices.

## 12. Dark mode

Supported in app and marketing; follows system by default with manual toggle. Brand colours lighten in dark (see tokens); shadows replaced by borders + elevated surfaces.

## 13. Design deliverables checklist (for designer)

- [ ] Figma library mirroring these tokens (variables for light/dark) and components
- [ ] Logo + app icon + favicon + WhatsApp profile image
- [ ] Voice card & employee avatar system
- [ ] All P1 screens from [07-SCREENS.md](07-SCREENS.md) at 360 px and 1440 px
- [ ] Landing page (EN + TE + HI) with live-demo module
- [ ] Prototype for onboarding + test call; run Grandmother tests with 5 real owners
