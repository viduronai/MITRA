# MotionSites reference specs (founder favourites)

> Pasted by the founder on 2026-10-18 as inspiration for the Mitra landing page. These are specs for OTHER brands (Vexel, ECHOID, Vesper, Driftbar, Targo). Use them for craft, structure, motion and layout, and adapt everything to Mitra. Never ship their brand names, copy, logos or fonts (e.g. Google Sans is proprietary). See docs/design/landing-direction.md for how each one is used.

---

viduronai.in is our companies main site so use fonts, accents same it contains(for reference) and for landing page frontend same i said before. 

claude mcp add motionsites --scope user --transport http https://xgdzyqfalbibzelpdpvr.supabase.co/functions/v1/mcp

choose the best that suits our product. it would be appreciable if its also a mix of multiple designs. 

my favs are Build one standalone HTML document that is the entire Vexel hero screen. Output only that file. Reproduce the markup, CSS, SVG paths, type, motion, and responsive rules exactly. Do not restyle, simplify, rename classes, or substitute a different background.

Page
- Language English. Title: Vexel — Your next customer starts with a hello.
- Viewport: width=device-width, initial-scale=1, viewport-fit=cover. Theme color #01061a.
- One screen, no page scroll. Column, centered. Background #01061a with a horizontal sky gradient: #00061a 0%, #01071b 22%, #01071a 45%, #010718 62%, #010614 80%, #020511 100%.

Type
- Font family "Google Sans", then "Product Sans", ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif.
- Embed Google Sans with font-display:block:
  weight 400 from assets/google-sans-400.woff2
  weight 500 from assets/google-sans-500.woff2
- Antialiased, geometricPrecision, normal kerning.

Scale
- Reference frame is 1280×800. Every layout number is multiplied by --u. At 1280×800, --u is 1px.
- Default: --u = min(100dvh/800, max(100vw/1280, min(100vw/640, .75px))). Fall back to vh where dvh is unsupported.
- Colors: ink #ffffff; nav rgba(238,242,255,.9); subhead rgba(226,233,255,.74); link rgba(212,236,255,.77); hairline rgba(255,255,255,.19); button #ffffff with ink #0a0a0a.

Masthead, centered
- Wordmark link, aria-label "Vexel home", href "#". White filled SVG, viewBox "588 40.5 103.5 23.5", height max(23.5u, 17px), shifted left by 0.5u. Paths, in order:
  M588.6 40.8H594.9L601.4 56.6L606.5 40.8H612.6L604.2 63.5H597.8Z
  M612.8 40.8H630.5V45.2H619.2V49.8H628.3V54.4H619.2V58.9H631.5V63.5H612.8Z
  M631.3 40.8H637.9L642.5 47.4L646.5 40.8H653.1L646.4 52L653.6 63.5H647.1L642.5 56.4L638.3 63.5H631.4L638.8 52Z
  M653.6 40.8H669.6V63.5H653.6V58.9H664.3V54.4H657V49.8H664.3V45.2H653.6Z
  M672.4 40.8H677.6V58.9H690.5V63.5H672.4Z
- Top padding: safe-area-inset-top plus 40.5u.
- Hairline under the logo: width max(284u, 252px), 1px, margin-top 24u.
- Nav width matches the hairline. Three links, space-between, margin-top 17.4u, side padding 8.9u: Platform #platform, Company #company, Contact #contact. Size max(15u, 13px), tracking -0.033em, color the nav token, hover #fff.

Copy, centered
- A flexible gap above the copy flexes at 82.98 and never shorter than 24u.
- Headline, weight 400, size max(68u, 34px), line-height 0.9559, tracking -0.0279em, nowrap. Two masked lines:
  line 1: Your next customer
  line 2: starts with a hello.
  Line 2 tracking -0.0294em and shifted right 2.6u. Each line is a span.l containing a span.li.
- Subhead: "Make the first move. We’ll help with what follows." Join the words inside each sentence with U+00A0 no-break spaces. The only normal space is the space after the period, so that is the only wrap point. Size max(21u, 15px), tracking -0.005em, margin-top 18.98u, color the subhead token, text-wrap balance.
- Button "Start a conversation" to #contact. Width max(216u, 196px), height max(46u, 44px), radius max(4.5u, 4px), weight 500, size max(17u, 15px), tracking -0.0265em, margin-top 25.64u. Hover fill #e8eef7 and a 4u ring of rgba(120,200,255,.12).
- Link "Discover the platform" to #platform, size max(14.8u, 13px), tracking -0.051em, margin-top 20.55u. Beside it, a 0.68em by 0.85em stroke arrow, viewBox "0 0 11 12.6", stroke 1.45, round caps: M5.5 .4V12M1 7.5L5.5 12L10 7.5. On hover the arrow moves down 0.12em.

Background video
- Use this URL and no other asset. Do not download it and do not replace it with a local file or poster image:
  https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20261005_182549_18378239-da8f-48a7-9666-d6e0a6a88561.mp4
- Video element: autoplay, muted, loop, playsinline, no controls, decorative.
- The field fills the remaining height (flex 318.68, min-height 160u) and is a size container. The video is absolutely centered, width auto, pointer-events none. Its horizon, 50.463% down the frame, sits 36.4u above the bottom of the copy. Height is the larger of fitting the field width at the artwork ratio 1619:971 and reaching the bottom edge: max(100cqw * 971/1619, (100cqh + 36.4u) / 0.49537 + 1px). Without container units, fall back to max(60vw, 105vh). Fade the top 4% of the video to transparent with a mask.

Focus
- Remove the default outline. Visible focus on the wordmark, nav links, and discover link is a 2px #7fd4ff outline offset 4px. The button uses offset 3px.

Responsive
- Tablet, 600px to 1099.98px wide and at least 541px tall: hold --u at min(100dvh/800, 1px, max(100vw/1280, 100dvh/1190, .86px)). Cap the video field at 48% of the screen height. Enlarge tap targets with negative margin so nothing moves: nav links 14px 8px, discover link 12px 10px.
- Portrait under 600px: same scale model, but use svh. Keep the two headline lines nowrap. Headline size is max(26px, min(68u, (100vw - 48px) / 8.235)). Subhead floor 16px, size min(21u, 3.345vw), line-height 1.25, overflow-wrap break-word. Hero side padding 24px. Hairline and nav width min(max(284u, 252px), 100vw - 32px). Field max-height 48%. Same enlarged tap targets.
- Landscape shorter than 540px: keep the desktop proportions and lower the floors — logo 13px, hairline and nav 210px, nav 11px, headline 28px, subhead 12px, button 150×34px at 12.5px, discover 11px, gap min 14u, field min 120u.
- Coarse pointer in that short landscape: grow tap targets only.
- At 359px and below, outside the portrait block, allow the headline to wrap at 30px.
- prefers-reduced-motion: no transitions, and do not run the entrance.

Entrance, once per load, only if Web Animations and matchMedia exist and reduced motion is off
- Add class "intro" immediately. If the entrance has not started within 3500ms, remove it.
- While intro is on: wordmark, nav items, subhead, button, and discover link start at opacity 0. Hairline starts at scaleX(0). Each headline line is clipped at its baseline and its inner span starts at translateY(104%).
- Wait for document.fonts.ready and for the video loadeddata event, but never longer than 900ms, then start.
- Distances scale with k, the logo height divided by 23.5, clamped from 0.65 to 1.
- Wordmark: from opacity 0 and translateY(-6k px), delay 60ms, 900ms, cubic-bezier(0.22, 1, 0.36, 1).
- Hairline: scaleX 0 to 1, delay 180ms, 1000ms, cubic-bezier(0.7, 0, 0.2, 1).
- Nav: center link first at 420ms, then the outer links at 490ms. Each from opacity 0 and translateY(-4k px), 700ms, the same quint easing.
- Headline lines rise from translateY(104%) to none, 1100ms, cubic-bezier(0.16, 1, 0.3, 1). First line delay 200ms, second 290ms.
- Subhead rises 10k px, delay 700ms, 850ms, quint.
- Button rises 12k px from scale 0.975, delay 860ms, 900ms, expo.
- Discover link rises 6k px, delay 1040ms, 700ms, quint.
- Arrow starts 5k px above and settles, delay 1120ms, 820ms, expo.
- All animations use fill both. When every animation finishes, remove intro, cancel the animations, and if focus is not inside the page, toggle the page display none for one reflow so the masks do not leave a separate GPU layer. Then set data-intro="done" on the document element.


Recreate this exact full-viewport dark hero landing page for “ECHOID” — a voice-identity product for the E network. Match every detail below precisely. Do not invent extra sections, cards, stats, or decorative overlays. Desktop composition: full-bleed cinematic background video on the left/center with a right-aligned signup panel; black negative space on the left; UI pinned top (nav), right (form), and bottom (legal).

═══════════════════════════════════════
PAGE META
═══════════════════════════════════════
- Document title: ECHOID — Your voice ID to the E network
- Lang: en
- Pure black page background (#000)
- Antialiased text
- Single full-viewport section only (no other page sections)

═══════════════════════════════════════
EXACT MEDIA URLS (CloudFront — use these verbatim)
═══════════════════════════════════════
Background video (MP4):
https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260806_133255_956f653f-5d80-4b06-abd5-0f46c98b60fa.mp4

Poster / fallback still (PNG):
https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260806_132328_5f9029c8-218f-4489-82b6-29ff2849920e.png

Video attributes: autoPlay, muted, loop, playsInline, preload="auto"
Video CSS: width/height 100%, object-fit: cover, object-position: center
Media layer: position absolute, inset 0, z-index -1, black background behind video
Preconnect to: https://d8j0ntlcm91z4.cloudfront.net

Video content (for reference): dark cinematic AI/surreal face sequence — abstract metallic/glass facial forms, cool dark palette, motion graphic identity vibe. Full-bleed edge-to-edge; never inset, never in a card.

═══════════════════════════════════════
FONTS (exact Google Fonts)
═══════════════════════════════════════
Load from Google Fonts:
family=Sora:wght@200;300;400
family=JetBrains+Mono:wght@300;400;500
display=swap
Preconnect fonts.googleapis.com and fonts.gstatic.com

CSS stacks:
--font-display: "Sora", "Helvetica Neue", Helvetica, Arial, sans-serif
--font-mono: "JetBrains Mono", ui-monospace, "SF Mono", "Cascadia Mono", Menlo, Consolas, monospace

Usage map:
- Sora 200: nav logo “ECHOID”, hero H1 “ECHOID”
- Sora 300: email input, legal footer text
- JetBrains Mono 400: nav links, JOIN UP CTA, chip, buttons, referral link, mobile menu links/CTA
- JetBrains Mono 300: tagline “YOUR VOICE ID TO THE E NETWORK.”

═══════════════════════════════════════
DESIGN TOKENS
═══════════════════════════════════════
--bg: #000000
--text: #ffffff
--text-dim: rgba(255,255,255,0.62)
--text-dimmer: rgba(255,255,255,0.42)
--line: rgba(255,255,255,0.14)
--line-strong: rgba(255,255,255,0.26)
--fill-ghost: rgba(255,255,255,0.05)
--fill-solid: rgba(255,255,255,0.10)
--gutter: clamp(20px, 5vw, 100px)
--ease-premium: cubic-bezier(0.16, 1, 0.3, 1)

═══════════════════════════════════════
LAYOUT SHELL
═══════════════════════════════════════
.hero:
- position relative, width 100%
- height: 100vh AND 100svh
- min-height: 640px (if max-height ≤640px, min-height becomes 100svh)
- overflow hidden
- CSS grid: grid-template-rows: auto 1fr auto
- isolation: isolate

Row 1 = navbar
Row 2 = right-aligned form body (flex end / center on mobile)
Row 3 = legal footer

═══════════════════════════════════════
SCRIM (dual gradient overlay on video)
═══════════════════════════════════════
Desktop (≥721px) — two stacked linear-gradients:
1) to right:
   transparent 0% → transparent 45% → rgba(0,0,0,0.45) 72% → rgba(0,0,0,0.72) 100%
2) to bottom:
   rgba(0,0,0,0.55) 0% → transparent 22% → transparent 78% → rgba(0,0,0,0.65) 100%

Mobile (≤720px) — single bottom gradient:
rgba(0,0,0,0.6) 0% → rgba(0,0,0,0.25) 30% → rgba(0,0,0,0.75) 100%

═══════════════════════════════════════
NAVBAR (top)
═══════════════════════════════════════
Flex space-between, align center, gap 32px
Padding: clamp(20px, 2.4vw, 34px) horizontal gutter; respect safe-area insets

LEFT — Logo link “ECHOID”
- Sora 200
- font-size: clamp(20px, 1.75vw, 30px)
- letter-spacing: 0.16em
- white, no underline, line-height 1

RIGHT — nav cluster (gap clamp(24px, 3.2vw, 62px)):
A) Desktop links (≥901px): Story, Platforms, Identity, Contact
   - JetBrains Mono 400
   - font-size: clamp(11px, 0.78vw, 14px)
   - letter-spacing: 0.18em
   - text-transform: uppercase
   - white; hover → --text-dim
   - transition color 0.25s ease
   - link gap: clamp(20px, 2.8vw, 56px)
   - hrefs: #story #platforms #identity #contact

B) Desktop CTA “Join up” (renders as JOIN UP via uppercase)
   - same mono type as links
   - padding: clamp(12px,1vw,17px) clamp(20px,1.8vw,32px)
   - border: 1px solid --line-strong
   - hover: background --fill-ghost, border-color rgba(255,255,255,0.5)
   - transition background+border 0.25s ease
   - href #join

C) Mobile hamburger (≤900px only; desktop links+CTA hidden)
   - 44×44 hit target, 3 bars 22px wide × 1px tall, white
   - bars at top 16/22/28px, centered with translateX(-50%)
   - Active (X morph): bar1 rotate(45deg) to top 22px; bar2 opacity 0 + scaleX(0); bar3 rotate(-45deg) to top 22px
   - transition: transform 0.45s --ease-premium, opacity 0.25s ease

═══════════════════════════════════════
MOBILE MENU OVERLAY
═══════════════════════════════════════
Fixed fullscreen, z-index 50 (nav is 60)
Background: rgba(4,4,6,0.94)
backdrop-filter: blur(28px) saturate(140%)
Closed: clip-path circle(3% at calc(100% - 42px) 42px), opacity 0, pointer-events none
Open: clip-path circle(150% at same origin), opacity 1, pointer-events auto
Transition: clip-path 0.7s --ease-premium, opacity 0.45s ease
Centered column of uppercase mono links (Story/Platforms/Identity/Contact) then bordered “Join up”
Link size: clamp(20px, 5.5vw, 28px), letter-spacing 0.14em
CTA: letter-spacing 0.22em, padding 16px 40px, border 1px --line-strong
Stagger entrance: each item starts opacity 0 + translateY(16px); when open → opacity 1 + translateY(0)
Delay: calc(180ms + var(--i) * 70ms) where i = 0..3 for links, i=4 for CTA
Transition on items: opacity 0.4s ease, transform 0.5s --ease-premium
Escape closes; click backdrop closes; body.menu-open { overflow:hidden }; restore focus; auto-close at ≥901px

═══════════════════════════════════════
RIGHT PANEL (voice entry signup)
═══════════════════════════════════════
hero__body: flex align center, justify flex-end (center on ≤720px), horizontal gutter, min-height 0, overflow-y auto

.panel desktop: width min(34vw, 620px), min-width 380px, column flex-start
≤1100px: width min(70vw, 520px), min-width 0
≤720px: width 100%, stretch; chip stays flex-start

Elements in order:

1) CHIP: “[ Voice entry ]” displayed as uppercase “[ VOICE ENTRY ]”
   - JetBrains Mono 400
   - font-size: clamp(11px, 0.72vw, 14px)
   - letter-spacing: 0.2em
   - background: rgba(255,255,255,0.09)
   - padding: clamp(9px,0.8vw,14px) clamp(14px,1.1vw,20px)
   - line-height 1
   - NO rounded pill — sharp rectangle

2) H1: “ECHOID”
   - Sora 200
   - font-size: clamp(54px, 6.2vw, 118px)  [≤380px: clamp(44px,15vw,64px)]
   - letter-spacing: 0.03em
   - line-height: 0.95
   - margin-top: clamp(28px, 3vw, 52px)
   - Brand-first: this is the dominant hero word; nothing larger

3) TAGLINE: “Your voice ID to the E network.”
   - JetBrains Mono 300, uppercase via CSS
   - font-size: clamp(11px, 0.94vw, 17px)
   - letter-spacing: 0.14em
   - color: --text-dim
   - margin-top: clamp(14px, 1.4vw, 24px)
   - line-height 1.4

4) FORM (noValidate, prevent default submit):
   margin-top: clamp(38px, 4.6vw, 82px)
   column gap: clamp(14px, 1.3vw, 22px)
   width 100%

   a) Email field
      - Visually-hidden label “Email”
      - Transparent input, no side borders, bottom border only 1px --line-strong
      - border-radius 0
      - padding: 0 2px clamp(12px,1.1vw,18px)
      - Sora 300, clamp(16px,0.95vw,18px), white text
      - placeholder “Email” color --text-dim
      - focus: bottom border rgba(255,255,255,0.85); placeholder → --text-dimmer
      - transition border-color 0.25s ease

   b) Button “Proceed using email” (.btn--ghost)
      - full width, border-radius 0, no border
      - padding: clamp(17px,1.6vw,27px) 20px
      - JetBrains Mono 400, uppercase, letter-spacing 0.22em
      - font-size: clamp(11px,0.78vw,14px)
      - background --fill-ghost, color --text-dimmer
      - hover: bg rgba(255,255,255,0.09), color white

   c) Button “Access” (.btn--solid)
      - same type/padding as above
      - background --fill-solid, color white
      - hover: bg rgba(255,255,255,0.17)

5) Referral link (centered under form): “I've got an invite key”
   - JetBrains Mono 400, uppercase via CSS
   - font-size: clamp(11px, 0.74vw, 14px)
   - letter-spacing: 0.18em
   - margin-top: clamp(26px, 2.6vw, 46px)
   - align-self: center
   - href #invite
   - hover: --text-dim + underline, underline-offset 4px

═══════════════════════════════════════
LEGAL FOOTER
═══════════════════════════════════════
border-top: 1px solid --line
padding: clamp(18px,1.7vw,30px) gutter; safe-area bottom
text-align center
Copy exact:
“Opening an e.xyz account signals that you accept our Privacy Notice and Service Contract.”
- Sora 300, clamp(12px,0.82vw,16px), color --text-dim, line-height 1.5
- “Privacy Notice” and “Service Contract” are white underlined links (underline-offset 3px, thickness 1px), hrefs #privacy-notice and #service-contract
- link hover → --text-dim

═══════════════════════════════════════
FOCUS / A11Y
═══════════════════════════════════════
Focus-visible outline: 1px solid rgba(255,255,255,0.7), offset 3px on buttons, CTA, toggle, referral, input, mobile links
Mobile menu: role=dialog, aria-modal, aria-label="Site menu", aria-hidden when closed, inert when closed
Toggle: aria-expanded, aria-controls="mobileMenu", aria-label Open/Close menu

═══════════════════════════════════════
REDUCED MOTION
═══════════════════════════════════════
prefers-reduced-motion: reduce → hide video; show poster as cover background-image on .hero__media; crush all animation/transition durations to 0.01ms

═══════════════════════════════════════
SHORT-HEIGHT COMPRESS (max-height: 640px)
═══════════════════════════════════════
Tighter nav padding; smaller H1 (clamp(36px,7vw,64px)); smaller form margins/gaps; thinner buttons; smaller legal (11px); tighter mobile menu

═══════════════════════════════════════
MOTION SUMMARY (what animates)
═══════════════════════════════════════
1. Background video continuous loop (primary presence)
2. Hover color/background transitions at 0.25s ease on links, CTAs, buttons, input border
3. Hamburger ↔ X morph 0.45s premium ease
4. Mobile menu circular clip-path expand 0.7s premium ease + opacity 0.45s
5. Mobile menu items staggered fade/slide-up with 70ms index delay
NO entrance animation on desktop panel. NO floating badges over video. NO cards, pills, glow, purple, or multi-shadow chrome. Sharp rects only. Aesthetic: black / white / translucent white glass, terminal-mono UI over cinematic face video.

═══════════════════════════════════════
STACK / IMPLEMENTATION NOTES
═══════════════════════════════════════
React + plain CSS (or equivalent). No Tailwind utility look required — custom properties as above. Form action="#" method="post" but preventDefault. Page is the hero only.
```

---

**Media URLs to keep verbatim:**

- Video: `https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260806_133255_956f653f-5d80-4b06-abd5-0f46c98b60fa.mp4`
- Poster: `https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260806_132328_5f9029c8-218f-4489-82b6-29ff2849920e.png`
- Fonts: **Sora** (200/300/400) + **JetBrains Mono** (300/400/500)


Recreate this exact single-viewport landing page for **Vesper.ai**. Document title: `Vesper.ai — Operational AI Infrastructure`. `lang="en"`. One HTML file with inline CSS and a small IIFE for the menu + animation fallback. Pure black `#000000`. No extra sections, cards, forms, pricing tables, or footer beyond the three stats. Do **not** add a video, WebGL, Three.js, or Lottie. Do **not** invent a CloudFront URL.

Force black immediately so the page can never flash white:

- First CSS rule: `html, body { background: #000000 !important; color: #ffffff; }`
- Body attribute: `style="background:#000;color:#fff"`
- Then again: `html, body { background: #000000; background: var(--bg, #000000); color: #ffffff; color: var(--text, #ffffff); }`

---

### Fonts (exact)

Self-hosted WOFF2s sitting next to `index.html`:

```css
@font-face {
  font-family: "Inter";
  font-style: normal;
  font-weight: 100 900;
  font-display: swap;
  src: url("inter.woff2") format("woff2");
}
@font-face {
  font-family: "Instrument Serif";
  font-style: italic;
  font-weight: 400;
  font-display: swap;
  src: url("instrument-serif-italic.woff2") format("woff2");
}
```

Stacks:

- UI / logo / nav / buttons / badge / lede / stats: `"Inter", system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif`
- **Only** the H1 words `AI agents`: `"Instrument Serif", "Times New Roman", Times, serif`

If those files are missing, load this exact Google Fonts CSS (Inter variable roman + Instrument Serif italic only):

```
https://fonts.googleapis.com/css2?family=Inter:ital,opsz,wght@0,14..32,100..900&family=Instrument+Serif:ital@1&display=swap
```

Body: `-webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale; text-rendering: optimizeLegibility; overflow-x: hidden; position: relative`. `html { scroll-behavior: smooth }`. Universal reset: `box-sizing: border-box; margin: 0; padding: 0`. Links `color: inherit; text-decoration: none`. Buttons `font-family: inherit`.

---

### Image / asset URLs (exact — there are only these)

**1. Herovide obackgorumf 100% opacity no overlay**  
Relative file, same folder as the HTML:

```
https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260818_072341_50851634-bbc3-4c33-9acc-7647d4db44aa.mp4
```

**3. Favicon (exact data URI)** — same mark as the logo, white:

```
data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='white'%3E%3Cg transform='rotate(-30 12 12)'%3E%3Ccircle cx='7.3' cy='3.2' r='1.45'/%3E%3Crect x='5.5' y='4.7' width='3.6' height='14.6' rx='1.8'/%3E%3Crect x='14.9' y='4.7' width='3.6' height='14.6' rx='1.8'/%3E%3Ccircle cx='16.7' cy='20.8' r='1.45'/%3E%3C/g%3E%3C/svg%3E
```

No other images. All other icons are inline SVG.

---

### Tokens (default / ~1440px)

```
--bg: #000000
--text: #ffffff
--muted: #9a9a9a
--stat: #d8d8d8
--border: rgba(255, 255, 255, 0.16)
--border-soft: rgba(255, 255, 255, 0.12)

--logo: 15.5px
--logo-mark: 22px
--nav: 14px
--nav-h: 40px
--btn: 13.5px
--btn-h: 40px
--hero-btn-h: 42px
--h1: 48px
--lede: 15.5px
--badge: 12.5px
--stat-size: 13.5px
--header-y: 22px
--header-x: 40px
--stats-x: 72px
--stats-y: 36px
--hero-gap: 85px
--copy-max: 860px
--lede-max: 470px
```

---

### Layer stack (back → front)

1. `html/body` black  
2. `.hero-photo` + `::after` scrim  
3. `.page` — `position: relative; z-index: 1; display: grid; grid-template-rows: auto 1fr auto; min-height: 100vh / 100dvh`  
4. `.grain` at `z-index: 100`

Markup order inside body:

```
.grain
.hero-photo
.page
  .menu-backdrop
  header.header
  main.hero#top
  footer.stats
script
```

---

### Header — 3-column grid

`display: grid; grid-template-columns: 1fr auto 1fr; align-items: center;`  
Padding: `var(--header-y) var(--header-x) 10px`. `z-index: 50; position: relative`.

**Left — logo** `a.logo.appear.appear--scale` → `#top`, `aria-label="Vesper.ai"`.  
`display: inline-flex; align-items: center; gap: 9px; justify-self: start; font-size: var(--logo); font-weight: 600; letter-spacing: -0.03em; color: #fff`.

Mark SVG 22×22, `viewBox="0 0 24 24"`, `fill="currentColor"`, group `transform="rotate(-30 12 12)"`:

- `circle cx="7.3" cy="3.2" r="1.45"`
- `rect x="5.5" y="4.7" width="3.6" height="14.6" rx="1.8"`
- `rect x="14.9" y="4.7" width="3.6" height="14.6" rx="1.8"`
- `circle cx="16.7" cy="20.8" r="1.45"`

Wordmark: `Vesper` + `<span class="logo-suffix">.ai</span>` at `font-weight: 400`.

**Center — nav** `#site-nav`, `aria-label="Primary"`, `display: flex; align-items: center; gap: 8px; justify-self: center`.

| Label | href | appear class |
|---|---|---|
| Benefits | `#benefits` | `appear--scale` |
| How It Works | `#how-it-works` | `appear--soft` |
| FAQs | `#faqs` | `appear--scale` |
| Pricing | `#pricing` | `appear--soft` |

Each link is a **liquid-metal pill**: `height: var(--nav-h); padding: 0 18px; border-radius: 7px; overflow: hidden; position: relative;`  
`border: 1px solid rgba(198,198,198,0.55)`  
`background: linear-gradient(105deg, #050505 0%, #2a2a2a 48%, #4a4a4a 100%)`  
color `#f3f3f3`, `font-size: var(--nav)`, weight 400, `letter-spacing: -0.01em`, `white-space: nowrap`.  
Transition: `background / border-color / box-shadow 0.35s ease`.

Shine `::before`: `linear-gradient(115deg, transparent 30%, rgba(255,255,255,0.16) 50%, transparent 70%)`, idle `translateX(-120%)`, hover `translateX(120%)` over `0.6s ease`.

Hover: border `rgba(235,235,235,0.9)`, gradient `#111 → #3a3a3a 45% → #6a6a6a`, glow `0 0 18px rgba(200,210,230,0.18)`.

**Right — header CTA:** `a.btn.btn-solid.header-cta.appear.appear--scale` “Start for Free” → `#start`, `justify-self: end`.

**Burger** (hidden ≥901px, `display: none` → `display: grid` on phone): 42×42, `border-radius: 6px`, `border: 1px solid var(--border)`, `background: rgba(8,8,8,0.55)`, `z-index: 60`, `aria-controls="site-nav"`, `aria-expanded="false"`, label “Open menu”. Three white bars 16×1.5px, gap 5px, `border-radius: 1px`. Hover: border `rgba(255,255,255,0.32)`, bg `rgba(255,255,255,0.05)`. Open (`body.menu-open`): bar 1 `translateY(6.5px) rotate(45deg)`, bar 2 `opacity: 0`, bar 3 `translateY(-6.5px) rotate(-45deg)`, 0.25s / 0.2s.

---

### Buttons (shared liquid-glass language)

`.btn`: `position: relative; isolation: isolate; overflow: hidden; display: inline-flex; align-items: center; justify-content: center; height: var(--btn-h); padding: 0 16px; border-radius: 6px; font-size: var(--btn); font-weight: 500; letter-spacing: -0.02em; line-height: 1; white-space: nowrap; cursor: pointer`. Transitions 0.35s on background, border, shadow, color, filter.

Shine `::after`: `linear-gradient(115deg, transparent 20%, rgba(255,255,255,0.45) 48%, transparent 76%)`, idle `translateX(-130%)`, hover `translateX(130%)` in `0.65s ease`.

**Solid:**  
`background: linear-gradient(180deg, #ffffff 0%, #e7e7e7 48%, #cfcfcf 100%)`  
`color: #111; border: 1px solid #fff`  
`box-shadow: inset 0 1px 0 rgba(255,255,255,0.95)`  
Hover: `#fff → #f3f6ff 42% → #d5def2`, border `#f2f6ff`,  
`inset 0 1px 0 #fff, 0 0 22px rgba(186,208,255,0.35), 0 8px 18px rgba(255,255,255,0.12)`

Hero solid hover glow is slightly stronger: `0 0 26px rgba(186,208,255,0.4), 0 8px 18px rgba(255,255,255,0.14)`.

**Ghost (header-level):**  
`background: linear-gradient(135deg, rgba(255,255,255,0.1), rgba(0,0,0,0.45) 50%, rgba(160,175,200,0.08))`  
`color: #fff; border: 1px solid rgba(198,198,198,0.45)`  
`box-shadow: inset 0 1px 0 rgba(255,255,255,0.12)`  
Hover: `rgba(210,225,255,0.18) → rgba(0,0,0,0.35) 48% → rgba(180,195,220,0.16)`, border `rgba(220,230,255,0.75)`,  
`inset 0 1px 0 rgba(255,255,255,0.22), 0 0 20px rgba(170,200,255,0.22)`

**Hero ghost** (stronger frost):  
`background: linear-gradient(135deg, rgba(255,255,255,0.12), rgba(0,0,0,0.5) 46%, rgba(150,170,200,0.1))`  
`border: 1px solid rgba(198,198,198,0.55)`  
`backdrop-filter: blur(16px); -webkit-backdrop-filter: blur(16px)`  
Hover glow `0 0 24px rgba(170,200,255,0.28)`, border `rgba(220,230,255,0.8)`.

Hero action buttons: height `var(--hero-btn-h)`, padding `0 18px`.

---

### Hero (bottom-centered, NOT vertically centered)

`.hero`: `display: flex; align-items: flex-end; justify-content: center; padding: 8px 24px var(--hero-gap); min-height: 0`.

`.hero-copy`: `position: relative; z-index: 1; flex-direction: column; align-items: center; text-align: center; max-width: var(--copy-max); width: 100%`.

**Badge** `.badge.appear.appear--pop` — text `Operational AI Infrastructure`  
`inline-flex; gap: 8px; margin-bottom: 22px; padding: 9px 15px; border: 0; border-radius: 5px`  
`background: linear-gradient(90deg, #7d7d7d 0%, #2a2a2a 52%, #0a0a0a 100%)`  
color `#f2f2f2`, `font-size: var(--badge)`, weight 400, `letter-spacing: -0.01em`.

Sparkle SVG 18×20, white, `filter: drop-shadow(0 0 3px rgba(255,255,255,0.45))`, path:

```
M12 2.6C12.55 2.6 12.88 3.15 13.08 4.7c.62 4.7 1.52 5.6 6.22 6.22 1.55.2 2.1.53 2.1 1.08s-.55.88-2.1 1.08c-4.7.62-5.6 1.52-6.22 6.22-.2 1.55-.53 2.1-1.08 2.1s-.88-.55-1.08-2.1c-.62-4.7-1.52-5.6-6.22-6.22C3.15 12.88 2.6 12.55 2.6 12s.55-.88 2.1-1.08c4.7-.62 5.6-1.52 6.22-6.22C11.12 3.15 11.45 2.6 12 2.6Z
```

**H1** two masked lines, Inter 500, `letter-spacing: -0.045em`, `line-height: 1.12`, `#fff`, column, centered:

- Line 1: `Train <em>AI agents</em> on your`
- Line 2: `workflows in minutes.`

`.headline-line`: `display: block; overflow: hidden; padding: 0.06em 0.15em 0.14em`.  
`em`: Instrument Serif italic 400, `font-size: 1.08em`, `letter-spacing: -0.03em`, color **`#9a9a9a`** (not white).

**Lede** `.lede.appear.appear--soft`, `max-width: var(--lede-max)`, `margin-top: 18px`, color `#9a9a9a`, `15.5px`, weight 400, `line-height: 1.55`, `letter-spacing: -0.015em`:

`Deploy adaptive AI agents that learn, execute, and scale operational tasks across your business.`

**Actions** `.hero-actions`: flex, wrap, center, gap `10px`, `margin-top: 26px`.

1. Solid `.appear.appear--btn`: `Start for Free` → `#start`  
2. Ghost `.appear.appear--side`: `See it in action` → `#demo`

---

### Stats footer

`.stats`: flex, `align-items: center; justify-content: space-between; gap: 24px;`  
padding `0 var(--stats-x) var(--stats-y)` and `padding-bottom: max(var(--stats-y), env(safe-area-inset-bottom))`, color `#d8d8d8`.

Each `.stat.appear.appear--stat`: `inline-flex; align-items: center; gap: 14px; font-size: var(--stat-size); letter-spacing: -0.015em; white-space: nowrap`. Icon 20×20 (`#e8e8e8`). Wide avatar icon 38×21.

**1. Dual-pill / workflow icon** (`viewBox="0 0 24 24"`):  
Left rect `x=3.4 y=2.6 w=7.2 h=18.8 rx=3.6` fill linear `#ffffff@0.38 → #3a3a3a@0.62` (`x1=3 y1=2 x2=14 y2=22`).  
Right rect `x=13.4 y=2.6` same size, inverted `#3a3a3a@0.38 → #ffffff@0.62`.  
Connector `x=9.2 y=10.9 w=5.6 h=2.2 rx=1.1` fill `#4a4a4a`.  
Label: `4.2M+ workflows automated`

**2. Download tile:** white rounded square `x=2.4 y=2.4 w=19.2 h=19.2 rx=6.2` fill `#ffffff`. Arrow `#111` stroke-width `1.85` round: vertical `M12 7.1v7.4`, chevron `M8.15 12.35L12 16.2l3.85-3.85`.  
Label: `92% reduction in manual operations`

**3. Three avatars** (`viewBox="0 0 40 22"`, class `stat-icon-wide`):  
- Dark circle `cx=10.2 cy=11 r=9.2` `#2b2b2b` + pale ellipse face `cx=10.2 cy=12.1 rx=4.15 ry=3.7` `#f4f4f4` + two ear triangles + eyes `r=0.7` `#1a1a1a`  
- White circle `cx=20.2` `#ffffff` + black eyes `r=1.7` + nose ellipse + smile path stroke `#111` width `1.2`  
- Orange circle `cx=30.2` `#f26b1d` + white Inter 700 `e` at `x=30.2 y=15.1 font-size=12.5 text-anchor=middle`  
Label: `180+ operational teams onboarded`

---

### Entrance motion (exact)

`.appear` resting opacity is **1** (so the page is never blank if animations fail).  
`animation-duration: 1.05s; animation-fill-mode: both; animation-timing-function: cubic-bezier(0.16, 1, 0.3, 1); animation-delay: var(--d, 0.08s)`.  
`both` applies the 0% keyframe during the delay, so they still hide then fade in when animations run.

On each element’s own `animationend`, add `.is-in` (`animation: none; opacity: 1; transform: none; clip-path: none; filter: none`). Same for `.hero-photo.is-in`.

JS fallback: after two `requestAnimationFrame`s, if `el.getAnimations()` has nothing `running` or `finished`, add `.is-in` to every `.appear` and `.hero-photo`.

| Element | Modifier | `--d` |
|---|---|---|
| Logo | `appear--scale` | 0.08s |
| Nav 1 Benefits | `appear--scale` | 0.16s |
| Nav 2 How It Works | `appear--soft` | 0.28s |
| Nav 3 FAQs | `appear--scale` | 0.40s |
| Nav 4 Pricing | `appear--soft` | 0.52s |
| Header CTA + burger | `appear--scale` | 0.34s |
| Badge | `appear--pop` | 0.22s |
| H1 line 1 | `appear--mask` | 0.42s |
| H1 line 2 | `appear--mask` | 0.62s |
| Lede | `appear--soft` | 0.82s, duration **1.25s** |
| Solid CTA | `appear--btn` | 0.96s |
| Ghost CTA | `appear--side` | 1.10s |
| Stat 1 | `appear--stat` | 1.12s |
| Stat 2 | `appear--stat` | 1.28s |
| Stat 3 | `appear--stat` | 1.44s |

Keyframes (all end at opacity 1 / identity transform):

- `in-scale`: `opacity 0, scale(0.84)` → 1  
- `in-soft`: `opacity 0, translateY(14px)` → 0  
- `in-mask`: `opacity 0, translateY(40%)` → 0 (clipped by `.headline-line` overflow)  
- `in-pop`: 0 `scale(0.9)` → 70% `scale(1.03)` → 100% `scale(1)`  
- `in-btn`: `translateY(18px) scale(0.94)` → rest  
- `in-side`: `translateX(22px)` → 0  
- `in-stat`: `translateY(20px)` → 0  
- `in-star` on `.badge-star`, `0.9s`, delay `0.28s`, both: `scale(0.2) rotate(-50deg)` → 65% `scale(1.2) rotate(8deg)` → rest  
- `in-em` on `h1 em`, `1.2s`, delay `0.72s`, both: `opacity 0.35; filter: blur(4px)` → sharp  

`prefers-reduced-motion: reduce`: `transition: none !important; animation: none !important` on `*, *::before, *::after`. Force `.appear, .hero-photo, .hero h1 em, .badge-star` to `opacity: 1; transform: none; clip-path: none; filter: none`.

---

### Responsive (copy these breakpoints)

**≥1600:** logo 17 / mark 24 / nav 15 / nav-h 44 / btn 15 / btn-h 44 / hero-btn 48 / h1 **64** / lede 18 / badge 13.5 / stat 15 / header 28×64 / stats 96×44 / copy 980 / lede-max 540. Nav pad `0 20px`. Badge mb 26, lede mt 22, actions mt 30 gap 12. Icons 22, wide 45×24.

**≥1920:** logo 18 / mark 26 / nav 16 / nav-h 48 / btn 16 / btn-h 48 / hero-btn 52 / h1 **76** / lede 20 / badge 14.5 / stat 16 / header 32×80 / stats 120×52 / copy 1120 / lede-max 620. Nav gap 10, pad `0 22px`. Buttons pad `0 22px`. Badge pad `10px 15px`. Wide icon 48×26.

**≥2560:** h1 **88**, lede 22, header-x 120, stats-x 160, copy 1280, lede-max 680.

**1280–1599:** h1 54, lede 16, header-x 48, stats-x 80, copy 900.

**901–1279:** logo 15, nav 13, nav-h 36, btn 13, btn-h 38, hero-btn 40, h1 **42**, lede 15, badge 12, stat 12.5, header 16×28, stats 36×28, hero-gap 64, copy 760, lede-max 440. Nav pad `0 14px`. Badge mb 16, lede mt 14, actions mt 20.

**≥901 and max-height 850:** header-y 14, stats-y 24, hero-gap 48, h1 40; badge mb 12, lede mt 12, actions mt 16.

**≥901 and max-height 720:** h1 34, lede 14, hero-gap 32, stats-y 18, nav-h 30, btn-h 34, hero-btn 36, badge mb 8.

**≥901 desktop lock:** `html, body { height: 100%; overflow: hidden }`. `.page { height: 100vh / 100dvh; overflow: hidden }`. One frame, **no scroll**.

**≤900 phone:** no 100vh lock; `html/body` `height: auto; overflow-y: auto`. Header `grid-template-columns: 1fr auto auto`, gap 8, safe-area padding. Logo / CTA / burger `z-index: 80`. Burger shown.

Full-screen menu: `.menu-backdrop` `display: block; position: fixed; inset: 0; z-index: 40; background: rgba(8,8,8,0.42)`, idle `opacity: 0; visibility: hidden`. Open: opacity 1 + **`backdrop-filter: blur(24px)`**, 0.28s. Nav becomes full-viewport column, `z-index: 45`, transparent, centered, gap 12, padding `96px 22px 32px` with `padding-top: max(96px, calc(env(safe-area-inset-top) + 88px))`. Links full-width, height 56, `font-size: 19px`, `border-radius: 10px`. Escape / nav click / resize ≥901 closes. Toggle `aria-expanded` and label Open/Close menu. `body.menu-open { overflow: hidden }`.

Hero pad `20px 20px 64px`, still `align-items: flex-end`. Stats **column**, centered, gap 16, `white-space: normal`. Copy/lede max-width 100%. Tokens: logo 16, btn 15 / 46, hero-btn 48, h1 **36**, lede 16.5, badge 13.5, stat 15, header 16×18, stats 20×28, hero-gap 36.

**≤560:** h1 34, lede 16, header-x 16. Hero actions **column**, buttons `width: 100%`.

---

### JS (only this)

1. Each `.appear` → own `animationend` → add `is-in` (`once: true`).  
2. If animations are not running after two rAFs, force `.is-in` on all `.appear` and `.hero-photo`.  
3. Burger toggles `body.menu-open`.  
4. Nav links and Escape close the menu.  
5. Resize to `(min-width: 901px)` closes the menu.

---


---



# Prompt: Recreate the Driftbar Meadow Footer (exact spec)

Copy everything below the line into your AI coding tool.

---

Build a single-file `index.html` (inline CSS, no frameworks, no build step) that recreates the **Driftbar** footer **exactly** as specified. It is one full-viewport footer:
- a pale paper top holding a brand block and three link columns
- a looping video of a blue-hour meadow (lavender mist, fireflies, first stars) filling the lower half and fading into the paper
- a giant frosted-glass "Driftbar" wordmark sinking into lavender fog at the bottom

Follow every value literally.

## 1. Media (use these exact URLs)

```html
<div class="footer__stage" aria-hidden="true">
  <video class="footer__video"
    src="https://d2ol7oe51mr4n9.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/4d01c727-d9c5-47c8-a778-35a451ffd39f.mp4"
    poster="https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20261014_121838_c97d0940-f430-4304-8573-4f47ee44f447.png"
    autoplay muted loop playsinline preload="auto"></video>
</div>
```

The video is 1920×1080 and loops seamlessly. It shows rolling grassy hills at blue hour: a grassy slope in the left foreground, misty hills receding to the right, a pink-violet horizon, a periwinkle sky with a few stars, and warm fireflies over the grass.

## 2. Font

**Inter** (variable, optical size 14–32, weight 400–700) for everything:

```html
<link rel="preconnect" href="https://fonts.googleapis.com" />
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
<link href="https://fonts.googleapis.com/css2?family=Inter:opsz,wght@14..32,400..700&display=swap" rel="stylesheet" />
```

Stack: `"Inter", system-ui, -apple-system, "Segoe UI", Helvetica, Arial, sans-serif`, with antialiased font smoothing.

## 3. Head

`<title>Driftbar — Meadow Footer</title>` and `<meta name="viewport" content="width=device-width, initial-scale=1" />`.

## 4. Tokens and unit system

```css
:root {
  --paper: #f1f1ee;
  --ink: #0c0c0c;
  --body: #6f6f6c;
  --muted: #9c9c98;
  --wordmark: #efefeb;
  --mist: #e2e3f1; /* pale lavender the blue-hour meadow fades into */
  --font: "Inter", system-ui, -apple-system, "Segoe UI", Helvetica, Arial, sans-serif;
}
*, *::before, *::after { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }
body { margin: 0; background: var(--paper); color: var(--ink); font-family: var(--font); }
a { color: inherit; text-decoration: none; }
ul { margin: 0; padding: 0; list-style: none; }
```

The footer is drawn on a **1440 × 672 canvas**. Every desktop size below is `calc(N * var(--u))`, written as `N u`:

```css
.footer {
  --u: min(100vw / 1440, 100vh / 672);
  --u: min(100vw / 1440, 100svh / 672);
  position: relative; height: 100vh; height: 100svh;
  background: var(--paper); overflow: hidden; isolation: isolate;
}
```

## 5. Structure (exact DOM order)

```
footer.footer
  div.footer__stage[aria-hidden] > video.footer__video        (section 1)
  p.footer__wordmark[aria-hidden]   "Driftbar"
  div.footer__fog[aria-hidden]
  div.footer__content
    div.brand
      a.brand__logo[href="#"][aria-label="Driftbar home"] > span.brand__mark + "Driftbar"
      h2.brand__title    "The calm bar for macOS"
      p.brand__text      "Driftbar gathers music, tasks, meetings, weather, search, focus timers, quick notes, and more handy widgets into one calm floating bar just above your Mac Dock."
      a.brand__cta[href="#"] > Apple-logo svg + "Get Driftbar today"
      p.brand__copy      "© 2026 Driftbar Inc. - Made in Lisbon."
      p.brand__by        "Built with " span.brand__heart[aria-label="love"] "💙" " by " span.brand__author > (span.brand__avatar[aria-hidden] > svg) "Mira Okafor"
      ul.brand__status   (chips, below)
    nav.col.col--menu[aria-label="Menu"]          h3.col__title "Menu"          ul.col__list: Tour, Showcase, Q&A, Licence, Journal
    nav.col[aria-label="Essentials"]              h3.col__title "Essentials"    ul.col__list: Support, Up next, Privacy notice, Usage guidelines, Manage licences
    nav.col[aria-label="From our team"]           h3.col__title "From our team" ul.col__list: Clipnest.io, Tallyo.io, Pinwell.io, Glyfo.co, Shelfmark.app, Wireloom.com, Gridcraft.app
```

Every link is `<li><a href="#">…</a></li>`.

**Apple logo (CTA):**
```html
<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
<path
d="M17.05 12.54c-.03-2.75 2.25-4.07 2.35-4.14-1.28-1.87-3.27-2.13-3.98-2.16-1.69-.17-3.3 1-4.16 1-.86 0-2.18-.97-3.59-.95-1.85.03-3.55 1.07-4.5 2.72-1.92 3.33-.49 8.25 1.38 10.95.91 1.32 2 2.8 3.43 2.75 1.38-.06 1.9-.89 3.56-.89 1.66 0 2.13.89 3.59.86 1.48-.03 2.42-1.34 3.33-2.67 1.05-1.53 1.48-3.02 1.5-3.1-.03-.01-2.88-1.1-2.91-4.37ZM14.31 4.46c.76-.92 1.27-2.2 1.13-3.46-1.09.04-2.41.73-3.19 1.64-.7.81-1.31 2.1-1.15 3.34 1.22.09 2.46-.62 3.21-1.52Z"
/>
</svg>
```

**Avatar:**
```html
<svg viewBox="0 0 24 24">
<rect width="24" height="24" fill="#e6e6e3" />
<circle cx="12" cy="9.2" r="4.4" fill="#1b1b1b" />
<path d="M3 25c0-6 4-9.4 9-9.4S21 19 21 25Z" fill="#1b1b1b" />
</svg>
```

**Status chips:**
```html
<ul class="brand__status" aria-label="Driftbar status">
<li class="chip"><span class="chip__dot" aria-hidden="true"></span>9,400 Macs in sync</li>
<li class="chip">
<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 11a8 8 0 1 0-2.3 5.7" /><path d="M20 4v7h-7" /></svg>
v1.8 · Shipped today
</li>
<li class="chip">
<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m12 3 2.7 5.6 6.1.8-4.5 4.2 1.1 6-5.4-2.9-5.4 2.9 1.1-6L3.2 9.4l6.1-.8Z" /></svg>
Rated 4.8 avg
</li>
</ul>
```

## 6. Desktop styles

**Stage and video**
- `.footer__stage`: absolute, `inset:0`, z-index 0.
- `.footer__video`: block, 100% × 100%, `object-fit:cover; object-position:50% 100%; transform:translateY(9%)`.
- `.footer__stage::after` (a haze so the copy stays readable): absolute, `inset:0`, `linear-gradient(to bottom, var(--paper) 0%, rgb(241 241 238 / .96) 26%, rgb(241 241 238 / .72) 44%, rgb(241 241 238 / 0) 70%)`.

**Wordmark, frosted glass**
- Position: absolute, `left:50%; bottom:-2u; transform:translateX(-50%)`, z-index 1, margin 0.
- Type: `font-size:390u` (this makes "Driftbar" span about 1200u), weight 600, `line-height:.74`, `letter-spacing:-0.045em`, no wrap, `pointer-events:none; user-select:none`.
- Glass fill, clipped to the letters:
  ```css
  color: rgb(232 234 250 / .4);
  background: linear-gradient(to bottom, rgb(255 255 255 / .78), rgb(214 218 246 / .36) 48%, rgb(255 255 255 / .62));
  -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent;
  filter: drop-shadow(0 -1u 0 rgb(255 255 255 / .55)) drop-shadow(0 0 18u rgb(190 200 255 / .45));
  ```
  Do **not** use `-webkit-text-stroke`. The letters overlap slightly, and a stroke would draw lines through the overlaps.

**Fog**
- `.footer__fog`: absolute at the bottom (`inset:auto 0 0`), z-index 2, `height:17%`, no pointer events.
- Background: `linear-gradient(to top, var(--mist) 0%, rgb(226 227 241 / .6) 30%, rgb(226 227 241 / 0) 100%)`.

**Content grid**
- `.footer__content`: relative, z-index 3.
- Grid columns `440u 240u 240u 1fr`, `align-items:start`.
- Width `1440u`, `margin:0 auto`, padding `86u 100u 0 160u`.

**Brand block**
- `.brand__logo`: inline-flex, centred, gap `10u`, `17u`, weight 500, letter-spacing −0.02em.
- `.brand__mark`: a `30u` square with radius `8u`.
  - Background `linear-gradient(to bottom, #2b2b2b, #0a0a0a 55%)`, shadow `0 1u 2u rgb(0 0 0 / .25)`.
  - `::after` is a white pill: left and right 13%, bottom 14%, height 19%, radius 999px.
- `.brand__title`: margin-top `19u`, `20u`, weight 600, line-height 1.2, −0.045em.
- `.brand__text`: max-width `412u`, margin-top `18u`, `--body` colour, `13.7u`, line-height 1.43, −0.012em.
- `.brand__cta`:
  - Box: inline-flex, gap `6u`, height `32.5u`, margin-top `20u`, padding `0 16u 0 15u`, radius `7u`, black, white text.
  - Type: `11.8u`, weight 500, −0.01em.
  - Icon: the svg is `13u` with margin-top `−1.5u`.
  - Hover: background `#262626` and `translateY(-1px)` (.2s).
- `.brand__copy`: margin-top `23u`, `--muted`, `12.2u`, letter-spacing .01em.
- `.brand__by`: flex, centred, gap `5u`, margin-top `21u`, `11.8u`, weight 500, −0.01em.
  - `.brand__heart` is .95em. `.brand__author` is inline-flex with gap `6u` and margin-left `5u`.
  - `.brand__avatar` is a `23u` circle on `#e3e3e0`.
- `.brand__status`: flex, wrap, gap `8u`, margin-top `16u`.
- `.chip`:
  - Box: inline-flex, gap `6u`, height `25u`, padding `0 10u`, `1px solid rgb(12 12 12 / .12)`, radius 999px, `rgb(255 255 255 / .55)` background.
  - Type: `10.8u`, weight 500, −0.01em, no wrap.
  - Icons: the chip svg is `11u`, no fill, `stroke:currentColor`, stroke-width 2, round caps and joins.
  - `.chip__dot`: a `6u` circle in `#2fb36a` with a ring `0 0 0 2.5u rgb(47 179 106 / .18)`.

**Link columns**
- `.col__title`: `16u`, weight 600, line-height 1, −0.045em.
- `.col__list`: grid, gap `20.5u`, margin-top `24u`, `13.7u`, line-height 1.24, letter-spacing .022em, colour `#161616`.
- The Menu column's list overrides that: gap `15u`, margin-top `21u`, weight 500, −0.025em, `--ink`.
- Links fade to opacity .55 on hover (.2s).

## 7. Tablet (768–1023px)

- `--u: min(100vw / 1040, 100svh / 672)`.
- Columns `400u 190u 210u 1fr`, width `1040u`, padding `64u 40u 0`.
- Brand text max-width `350u`.
- Wordmark `286u`, bottom `10u`.

## 8. Mobile (≤767px)

- **Footer:** `--u:1px`. It becomes a flex column, `height:auto; min-height:100svh`.
- **Haze:** `linear-gradient(to bottom, var(--paper) 0%, rgb(241 241 238 / .95) 50%, rgb(241 241 238 / .8) 68%, rgb(241 241 238 / 0) 90%)`. It runs further down than on desktop because the blue-hour hills are darker.
- **Content:**
  - Grid columns `auto auto auto`, `justify-content:space-between`.
  - Gaps: column 12px, row 36px.
  - Width 100%, padding `40px 20px 0`, margin-bottom `max(34vw, 150px)`.
  - `.brand` spans all columns.
- **Brand block sizes:**
  - Title 21px. Text max-width 34em, 14px.
  - CTA: height 38px, padding `0 18px 0 16px`, radius 8px, 13px, svg 14px.
  - Copy and credit line 12.5px.
  - Chips: height 28px, 12px.
- **Columns:**
  - Column titles 15px.
  - All lists: gap 14px, margin-top 20px, 13px, letter-spacing 0, no wrap.
- **Wordmark and fog:** wordmark `bottom:5vw; font-size:27vw`, fog height 7%.
- **Below 360px:** columns become `1fr 1fr`.

## 9. Motion

The only motion is the looping video and the hover transitions. Under `prefers-reduced-motion: reduce`, turn off the CTA and link transitions.

## 10. Acceptance check

At 1440×900 you should see:
- **Top left:** the black logo tile and "Driftbar".
- **Brand block:** "The calm bar for macOS", the three-line grey paragraph and the black "Get Driftbar today" button. Below them, the copyright, the "Built with 💙 by Mira Okafor" line and three chips.
- **Columns:** Menu, Essentials and From our team, starting at x≈600, 840 and 1080.
- **Lower half:** the blue-hour meadow with fireflies, fading into the paper above.
- **Wordmark:** a giant frosted-glass "Driftbar" spanning roughly x 140–1320, sinking into lavender fog at the bottom edge.


# Prompt: Recreate the Targo hero + about sections

Build a single-page site with exactly two sections. Font: **Quantico** (Google Fonts, weights 400 + 700), fallback 'Arial Narrow', sans-serif. Accent color: **#15BCDF** (hover #3fd0ef, border #0fa3c2). Page/body background: **#F2F1F0**. Text colors: headings #2b3033, nav links #3a3a3a, body gray #6b6f72. All headings uppercase, letter-spacing 0.01em, line-height 0.98.

## Section 1 — Hero (min-height: 100svh, background #F2F1F0, overflow hidden)

**Background video** (absolutely positioned, pointer-events none, no crop — objectFit: contain, height auto):
`https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260823_050407_500d0339-ab28-41c1-9688-132a74a3b5aa.mp4`
- Desktop: top 0, right -20%, width 99%.
- Mobile (≤700px): top 0, left -12%, width 119%.
- Attributes: autoplay, muted, loop, playsinline, preload auto. Robustness: retry `video.play()` every 1s and on first document click/touchstart (always set muted before play, swallow rejections).
- Desktop only: a scrim overlay on the left 70% of the section, `linear-gradient(90deg, #F2F1F0 0%, #F2F1F0 55%, rgba(242,241,240,0.85) 78%, rgba(242,241,240,0) 100%)`, no scrim on mobile.

**Navbar** (relative, flex, wrap, gap clamp(20px,5vw,56px), padding clamp(20px,3vw,38px) clamp(20px,4vw,48px) 0):
- Logo: 38px dark (#111) circle containing a white 20×8px ellipse rotated -25°, next to lowercase word "targo" (font-size clamp(22px,5vw,30px), weight 400, color #111, letter-spacing -0.5px).
- Links HOME / ABOUT / CONTACT US: bold 700, font-size clamp(12px,2.4vw,15px), letter-spacing 0.06em, color #3a3a3a, nowrap, gap 34px. Hidden on mobile.
- Right-aligned "Contact us" button (desktop only): transparent, **no border**, white text, uppercase, letter-spacing 0.14em, padding 14px 26px, chamfered corners via `clip-path: polygon(0 0, calc(100% - 12px) 0, 100% 12px, 100% 100%, 12px 100%, 0 calc(100% - 12px))`, with a white stroked mail-envelope SVG icon (17×13, stroke-width 1.4). Hover: background rgba(255,255,255,0.14).
- Mobile: hamburger button (3 white 22×2px bars, gap 5px) replacing links + contact button; tapping toggles a stacked menu of the 3 links (dark #1a1c1e, bold, gap 18px).

**Headline** (h1, 6 staircase lines, uppercase, weight 700):
```
SCALING
THE
PLATFORM
        FOR
        YOUR
        BUSINESS   ← this line in #15BCDF
```
Last three lines indented by `min(238px, 28vw)`.
- Desktop: padding `min(clamp(40px,9vw,120px),9vh) 20px min(clamp(24px,4vw,44px),5vh) clamp(20px,9vw,118px)`; font-size `min(clamp(34px,7.6vw,80px), 9.2vh)` (vh caps keep headline + button inside 100vh on short monitors).
- Mobile: margin-top 360px (text sits below the video), padding `0 20px 28px 20px`, font-size `clamp(34px,10vw,56px)`.

**CTA button** "GET STARTED" under the headline, left edge aligned with the FOR/YOUR/BUSINESS indent (left padding `calc(clamp(20px,9vw,118px) + min(238px,28vw))`, bottom padding `min(clamp(36px,6vw,80px),7vh)`). Style: background #15BCDF, border 1px solid #0fa3c2, dark text #1a1c1e, uppercase, weight 700, letter-spacing 0.14em, padding 18px 34px, font-size clamp(13px,2.2vw,16px), chamfered corners `clip-path: polygon(0 0, calc(100% - 16px) 0, 100% 16px, 100% 100%, 16px 100%, 0 calc(100% - 16px))`, glow `box-shadow: 0 0 0 1px rgba(21,188,223,0.35), 0 10px 30px -12px rgba(15,163,194,0.6)`, trailing 22×1px dark line. Hover: background #3fd0ef, stronger glow.

## Section 2 — About (flex, wrap, align center, gap 40px)

Background: `linear-gradient(180deg, #F2F1F0 0%, #F7F6F8 18%, #F7F6F8 100%)` (smooth handoff from hero). Padding: `clamp(60px,10vw,140px) 0 clamp(30px,5vw,70px) clamp(20px,9vw,118px)` — **no right padding** so the media touches the right screen edge.

**Left column** (flex 1 1 420px, min-width 300px):
- h2, two staircase lines: "ABOUT" then "BUSINESS" in #15BCDF indented by `min(160px,18vw)`. Font-size clamp(34px,6.5vw,72px), weight 700, uppercase.
- Paragraph (max-width 520px, margin 32px 0 0 min(160px,18vw), font-size clamp(14px,1.6vw,17px), line-height 1.7, color #6b6f72), text verbatim:
  "Targo builds the testing infrastructure modern teams rely on. From automated pipelines to full-scale QA audits, we make sure your software ships fast and breaks nothing. Hundreds of releases, zero surprises."
- "LEARN MORE" button, identical style to the hero CTA, margin 36px 0 0 min(160px,18vw).

**Right column** (flex 1 1 360px, min-width 280px, justify-content flex-end, position relative):
- Video, width 100%, max-width 644px, height auto, flush to the right edge:
  `https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260823_063501_2e2c8971-de1e-473a-8611-a0c9ae7ee186.mp4`
  Same attributes + autoplay-retry logic as the hero video.
- Overlay rectangle exactly covering the video (absolute, top 0, right 0, width 100%, max-width 644px, height 100%): background **#15BCDF** with `mix-blend-mode: hue`, pointer-events none, z-index 1 (tints the video cyan).

## Global
- `body { margin: 0; background: #F2F1F0; }`; links: color #3a3a3a, no underline, hover #000.
- Mobile breakpoint: 700px (JS-driven via window.innerWidth + resize listener, or media queries).
- No other sections, no footer.


so mitra giving a cool, friendly vibes i like to put black, blue, sky blue, white or chalk white kinda colors (not exactly but telling you for reference so plan the design system). 

for remaining questions, move forward step by step with multi subagents.