# Mitra landing page: creative direction v2 (approved inputs: 2026-10-18)

Inputs:
- **Founder's favourite MotionSites specs:** [motionsites-references.md](motionsites-references.md) (Vexel, ECHOID, Vesper, Driftbar, Targo).
- **Company site:** viduronai.in (Viduron AI, our parent company).
- **Mood:** cool and friendly. Palette is black, blue, sky blue, white / chalk white.
- **Bar:** feel like Apple, Google Antigravity, GitHub. Alive, premium, never a generic AI-SaaS template.

This file overrides the "Voice Sphere" direction in [07-SCREENS §2.2](../07-SCREENS.md) wherever they differ. The Voice Sphere survives as the visual in "Hear it" (scene 3).

---

## 1. Brand system for marketing

### 1.1 Fonts (shared with Viduron AI's site)

| Role | Font | Source | Notes |
|---|---|---|---|
| Display + UI | **Host Grotesk** (300–700) | Google Fonts | Viduron's sans; headings tight tracking (-0.03 to -0.045em) |
| Labels, chips, micro-copy | **Geist Mono** (400–500) | Google Fonts | ECHOID-style uppercase mono labels, letter-spacing 0.14–0.22em |
| Statement numerals | **Doto** (700) | Google Fonts | Viduron's dot-matrix face. Only for big numbers (₹3 / min, live counters) |
| Accent words | **Instrument Serif** italic | Google Fonts | Vesper-style: one or two italic words per headline, e.g. "starts with a *hello*." |
| Indic | Noto Sans Telugu / Devanagari | Google Fonts | Every Telugu/Hindi string; +10% line-height |

Do not use Google Sans or Product Sans. They appear in the Vexel spec but are proprietary to Google.

### 1.2 Colour (marketing)

| Token | Hex | Use |
|---|---|---|
| `--night` | `#01061A` | Hero sky base (Vexel) |
| `--ink` | `#05070D` | Dark sections, text on chalk |
| `--ink-raised` | `#0B1020` | Dark cards, glass base |
| `--blue` | `#2F6BFF` | Primary brand blue: key CTAs on chalk, links |
| `--blue-deep` | `#123A9E` | Gradients, pressed states |
| `--sky` | `#38C6F4` | Signature accent: live states, voice waveforms, highlights, staircase last line (Targo role) |
| `--sky-soft` | `#9FE3FA` | Glows, focus rings on dark (`#7FD4FF` per Vexel works too) |
| `--chalk` | `#F3F2EE` | Light "paper" sections (Driftbar/Targo role) |
| `--chalk-2` | `#E8E7E2` | Dividers and cards on chalk |
| `--white` | `#FFFFFF` | Text on dark, solid buttons |
| `--mist` | `#DDE8F5` | Footer fog (Driftbar mist recoloured toward sky) |
| `--viduron-ember` | `#FF6A1F` | Only the small "A Viduron AI product" mark |

Glass on dark, from Viduron: fill `rgba(220,235,255,0.04)`, edge `rgba(220,235,255,0.10)`, hi-edge `rgba(220,235,255,0.20)`.

### 1.3 Shared craft rules
- **Buttons.** Vesper "liquid glass" family. Solid is a white-to-chalk gradient with a hover sheen sweep and a sky glow `0 0 24px rgba(56,198,244,.35)`. Ghost is frosted glass with `backdrop-filter: blur(16px)`. On chalk sections the solid button turns `--blue` with white text.
- **Chamfered CTA** (Targo `clip-path`) is used only in chalk sections, for "Get started" and "See pricing".
- **Easing:** `cubic-bezier(.16,1,.3,1)` for reveals, `cubic-bezier(.22,1,.36,1)` for small moves. Masked headline lines rise from `translateY(104%)`.
- **Grain:** a subtle film grain layer at 3–4% on dark sections (Vesper).
- **Accessibility:** focus ring is `2px var(--sky-soft)` with offset 3–4px. Every scene honours `prefers-reduced-motion` (no entrance animation, video replaced by its poster).

## 2. Scene-by-scene: which favourite powers which scene

| # | Scene | Built from | Content |
|---|---|---|---|
| 0 | **Header** | Vexel masthead (in hero) → becomes a sticky compact bar after the hero, with Vesper liquid-metal nav pills recoloured blue-steel. Mobile menu is ECHOID's circular clip-path overlay. | mitra wordmark · Product · Industries · Pricing · Agencies · **Call me now** |
| 1 | **Hero, one screen** | **Vexel**: night-sky gradient, centred masthead + hairline + nav, two masked headline lines, horizon video field at the bottom with a top mask fade. Add a **Vesper badge** above the headline. | Badge: `✦ Speaks Telugu · Hindi · English`. H1 line 1: "Your phone rings." Line 2: "Mitra says *hello*." (Instrument Serif italic on *hello*). Sub: "AI employees that answer every call, call every lead, and handle the follow-up." CTAs: solid **Call me now** → #demo · ghost **Hear a real call** → #hear. Video: Vexel horizon URL. |
| 2 | **Live demo** (#demo) | **ECHOID**: full-bleed cinematic video, black negative space left, right-aligned panel, mono chip, giant thin display word, mono tagline, bottom-border input, sharp ghost and solid buttons. | Chip `[ LIVE DEMO ]` · H: "Hear Mitra." · tagline "A REAL CALL TO YOUR PHONE IN 30 SECONDS." Phone input, then language chips (తెలుగు / हिंदी / English), then industry chips (Clinic / Real estate / Coaching), then solid **Call me now** (sky glow). Below: "Mitra introduces itself as an AI assistant. We never share your number." Video: ECHOID face-sequence URL + poster. |
| 3 | **Hear it** (#hear) | Original **Voice Sphere** (pinned scroll) + Vesper typography | Pinned: the sphere (sky/blue particles) pulses with real sample audio while the transcript types out. A segmented switch picks Clinic · Real estate · Payment reminder. An opt-in "🔊 Sound on" toggle. |
| 4 | **One call becomes a team** | **Targo** on chalk: staircase uppercase headline, last line in `--sky`, chamfered CTA, video tinted via `mix-blend-mode: hue` overlay in sky blue, media flush to the right edge | "ONE CALL / BECOMES / A TEAM" (TEAM in sky). Team map: Lead Caller → Visit Coordinator → Sales Assistant → Payment Caller, with light beams between nodes. Paragraph + **See how teams work**. Videos: Targo URLs, hue-tinted sky. |
| 5 | **Run it from WhatsApp** | Apple-style pinned story on chalk | A floating phone. The Manager chat plays out as you scroll (daily report → approval tap → voice-note command). |
| 6 | **Your number. Your name.** | Dark ink + Vesper glass | Lock-screen incoming call "Sunrise Clinic ✓ · Verified business". Copy on Trusted Caller ID, with no 140/160 spam. |
| 7 | **Pricing statement** | Doto numerals on night blue + **Vesper stats strip** | Huge dot-matrix **₹3 · ₹4.5 · ₹6** "per minute. No monthly fee." Stats strip: "Answers in under a second" · "3 languages at launch" · "Pay only for talk-time". CTA **See pricing**. |
| 8 | **Industries** | Chalk cards with hover sheen | Clinics · Real estate · Coaching · Agencies, each with a ▶ sample. |
| 9 | **Footer** | **Driftbar**: chalk paper top with brand block + 3 link columns, the blue-hour meadow video in the lower half fading into the paper, a giant frosted-glass **"mitra"** wordmark sinking into fog recoloured to `--mist` | Brand block "AI employees for every Indian business" + **Call me now**, status chips ("● Live in Hyderabad", "Telugu · Hindi · English", "Data stored in India"), "A Viduron AI product" with an ember dot. Columns: Product · Company · Legal. |

## 3. Media
- Use the CloudFront video/poster URLs from the references verbatim, hotlinked as the specs require: Vexel horizon, ECHOID face, Targo hero and about, Driftbar meadow + poster.
- **TODO before public launch:** confirm the MotionSites licence terms. If they allow it, re-host on our CDN (S3 Mumbai + CloudFront) for reliability. Always set `poster` and give each scene a static gradient fallback.
- Lazy-load every video below the hero (`preload="none"` + IntersectionObserver). On phones with `saveData` or a slow connection, show posters only.

## 4. Performance and quality gates
- LCP ≤ 2.0 s and CLS < 0.05 on mobile 4G, measured on the hero.
- The 3D/canvas sphere is lazy-loaded and capped at 30fps on mobile.
- Fonts are self-hosted via `next/font` and subset.
- Lighthouse: Performance ≥ 85 mobile, Accessibility ≥ 95, SEO ≥ 95.
- No horizontal scroll at 360px. Every scene is checked at 360, 768, 1280, 1440 and 1920 widths.
