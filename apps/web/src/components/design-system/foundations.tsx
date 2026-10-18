import { cn } from "@/lib/utils";
import { DsSection, Specimen } from "./ds-section";

interface Swatch {
  token: string;
  light: string;
  dark: string;
  use?: string;
}

// Values mirror docs/06 §3; swatches render the live variable, so they follow the theme.
const colourGroups: { title: string; swatches: Swatch[] }[] = [
  {
    title: "Brand · Mitra Blue & Sky",
    swatches: [
      { token: "--brand-50", light: "#EEF3FF", dark: "#0B1430", use: "Subtle fills" },
      { token: "--brand-100", light: "#DCE6FF", dark: "#122045", use: "Selected rows" },
      { token: "--brand-500", light: "#2F6BFF", dark: "#6E97FF", use: "Focus rings, links" },
      { token: "--brand-600", light: "#2459F5", dark: "#7FA3FF", use: "Primary buttons" },
      { token: "--brand-700", light: "#1A46CC", dark: "#A3BEFF", use: "Hover / pressed" },
      { token: "--sky-400", light: "#38C6F4", dark: "#4CCFF7", use: "Sky — live, voice, waveforms" },
      { token: "--sky-100", light: "#E2F6FD", dark: "#0A2A38", use: "Sky backgrounds" },
    ],
  },
  {
    title: "Neutrals · Chalk (light) & Ink (dark)",
    swatches: [
      { token: "--bg", light: "#F4F3EF", dark: "#05070D" },
      { token: "--surface", light: "#FFFFFF", dark: "#0B1020" },
      { token: "--surface-2", light: "#ECEBE6", dark: "#121829" },
      { token: "--border", light: "#E1E0DA", dark: "#1E2638" },
      { token: "--text", light: "#0C0E14", dark: "#F2F4F8" },
      { token: "--text-muted", light: "#585D6A", dark: "#A3ABBC" },
      { token: "--text-subtle", light: "#868B97", dark: "#6F788B" },
    ],
  },
  {
    title: "Semantic",
    swatches: [
      { token: "--success", light: "#12A150", dark: "#3DD68C", use: "Booked, live, connected" },
      { token: "--warning", light: "#D98E04", dark: "#F5B83D", use: "Needs attention" },
      { token: "--danger", light: "#DC3545", dark: "#FF6B6B", use: "Failed, destructive" },
      { token: "--info", light: "#2F7FE0", dark: "#6AA8FF", use: "Neutral notices" },
    ],
  },
];

// Text-on-fill pairs that must stay ≥ 4.5:1 (computed for both themes).
const contrastPairs = [
  { label: "On brand", fg: "--on-brand", bg: "--brand-600", ratio: "5.5 / 8.2" },
  { label: "Brand on brand-50", fg: "--brand-700", bg: "--brand-50", ratio: "6.8 / 9.8" },
  { label: "Sky ink on sky-100", fg: "--sky-ink", bg: "--sky-100", ratio: "8.0 / 12.0" },
  { label: "Muted on bg", fg: "--text-muted", bg: "--bg", ratio: "5.9 / 8.7" },
];

const typeScale = [
  { role: "Display", spec: "Host Grotesk 40/44 → 72/76 · 500 · −3%", className: "font-display text-[40px] leading-[44px] font-medium tracking-[-0.03em] md:text-[72px] md:leading-[76px]", sample: "Your phone rings." },
  { role: "H1", spec: "Host Grotesk 28/34 → 36/42 · 600", className: "font-display text-[28px] leading-[34px] md:text-4xl md:leading-[42px]", sample: "Good morning, Lakshmi" },
  { role: "H2", spec: "Host Grotesk 22/28 → 28/34 · 600", className: "font-display text-[22px] leading-7 md:text-[28px] md:leading-[34px]", sample: "Recent calls" },
  { role: "H3", spec: "Host Grotesk 18/26 → 20/28 · 600", className: "text-lg leading-[26px] md:text-xl md:leading-7", sample: "Finish setting up" },
  { role: "Body L", spec: "Host Grotesk 17/26 · 400", className: "text-[17px] leading-[26px] font-normal", sample: "Priya booked 9 appointments today." },
  { role: "Body", spec: "Host Grotesk 15/24 → 16/24 · 400", className: "text-[15px] leading-6 font-normal md:text-base", sample: "Calls will appear here once Priya starts answering." },
  { role: "Small", spec: "Host Grotesk 13/20 · 400–500", className: "text-[13px] leading-5 font-medium", sample: "6:15 pm · 2m 14s" },
  { role: "Eyebrow", spec: "Geist Mono 11–12/16 · uppercase · +0.14em", className: "eyebrow text-text-muted", sample: "Step 2 of 6" },
  { role: "Numbers", spec: "Host Grotesk tabular 32/36 → 44/48 · 600", className: "text-[32px] leading-9 tabular-nums md:text-[44px] md:leading-[48px]", sample: "₹1,20,000" },
];

const radii = [
  { name: "Inputs & buttons", value: "12px", className: "rounded-lg" },
  { name: "Cards", value: "16px", className: "rounded-xl" },
  { name: "Sheets & modals", value: "24px", className: "rounded-2xl" },
  { name: "Avatars & pills", value: "full", className: "rounded-full" },
];

const shadows = [
  { name: "shadow-xs", className: "shadow-xs" },
  { name: "shadow-sm", className: "shadow-sm" },
  { name: "shadow-md", className: "shadow-md" },
  { name: "shadow-lg", className: "shadow-lg" },
];

const motion = [
  { name: "motion-fast", spec: "120ms · cubic-bezier(.2,0,0,1)", use: "Hovers, toggles", className: "motion-fast" },
  { name: "motion-base", spec: "200ms · cubic-bezier(.2,0,0,1)", use: "Dropdowns, tabs", className: "motion-base" },
  { name: "motion-slow", spec: "320ms · cubic-bezier(.16,1,.3,1)", use: "Sheets, modals", className: "motion-slow" },
];

export function Foundations() {
  return (
    <>
      <DsSection id="colour" title="Colour" description="Black, Mitra Blue, Sky and chalk white. One confident brand colour; Sky only for live and voice moments. Toggle the theme to see dark values.">
        <div className="flex flex-col gap-8">
          {colourGroups.map((group) => (
            <div key={group.title}>
              <h3 className="mb-3 text-base font-semibold">{group.title}</h3>
              <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-7">
                {group.swatches.map((swatch) => (
                  <li key={swatch.token} className="overflow-hidden rounded-xl border bg-card">
                    <div className="h-16 border-b" style={{ background: `var(${swatch.token})` }} />
                    <div className="flex flex-col gap-0.5 p-3 text-[13px] leading-5">
                      <span className="font-mono font-medium">{swatch.token}</span>
                      <span className="font-mono text-text-muted">
                        {swatch.light} / {swatch.dark}
                      </span>
                      {swatch.use && <span className="text-text-muted">{swatch.use}</span>}
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          ))}
          <div>
            <h3 className="mb-3 text-base font-semibold">Contrast pairs (light / dark)</h3>
            <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {contrastPairs.map((pair) => (
                <li
                  key={pair.label}
                  className="flex items-center justify-between gap-3 rounded-xl border p-4"
                  style={{ background: `var(${pair.bg})`, color: `var(${pair.fg})` }}
                >
                  <span className="font-medium">{pair.label}</span>
                  <span className="font-mono text-sm tabular-nums">{pair.ratio}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </DsSection>

      <DsSection id="type" title="Typography" description="Host Grotesk for everything, Geist Mono for small uppercase labels (sparingly). Indic scripts use Noto Sans with taller lines and are never uppercased.">
        <div className="flex flex-col divide-y rounded-xl border bg-card shadow-xs">
          {typeScale.map((row) => (
            <div key={row.role} className="flex flex-col gap-2 p-5 md:flex-row md:items-baseline md:gap-8">
              <div className="w-56 shrink-0">
                <p className="text-sm font-semibold">{row.role}</p>
                <p className="font-mono text-xs text-text-muted">{row.spec}</p>
              </div>
              <p className={cn("min-w-0 font-semibold break-words", row.className)}>{row.sample}</p>
            </div>
          ))}
          <div className="grid grid-cols-1 gap-4 p-5 md:grid-cols-2">
            <div>
              <p className="mb-1 text-sm font-semibold">Telugu · Noto Sans Telugu</p>
              <p lang="te" className="text-[17px]">
                నమస్కారం, Sunrise Clinic నుంచి Priya మాట్లాడుతున్నాను.
              </p>
            </div>
            <div>
              <p className="mb-1 text-sm font-semibold">Hindi · Noto Sans Devanagari</p>
              <p lang="hi" className="text-[17px]">
                नमस्ते, मैं Sunrise Clinic से Priya बोल रही हूँ।
              </p>
            </div>
          </div>
        </div>
      </DsSection>

      <DsSection id="shape" title="Shape, depth & motion" description="Prefer borders and subtle backgrounds over heavy shadows. Motion explains; it never decorates.">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          <Specimen label="Radius">
            <div className="grid grid-cols-2 gap-3">
              {radii.map((radius) => (
                <div key={radius.name} className="flex flex-col items-start gap-2">
                  <div className={cn("size-14 border-2 border-brand-500 bg-brand-50", radius.className)} />
                  <span className="text-[13px] leading-5 text-text-muted">
                    {radius.name} · {radius.value}
                  </span>
                </div>
              ))}
            </div>
          </Specimen>
          <Specimen label="Elevation">
            <div className="grid grid-cols-2 gap-4 bg-bg p-2">
              {shadows.map((shadow) => (
                <div key={shadow.name} className={cn("flex h-16 items-center justify-center rounded-xl bg-surface font-mono text-xs", shadow.className)}>
                  {shadow.name}
                </div>
              ))}
            </div>
          </Specimen>
          <Specimen label="Motion (hover the bars)">
            <ul className="flex flex-col gap-4">
              {motion.map((item) => (
                <li key={item.name} className="group">
                  <div className="h-2 overflow-hidden rounded-full bg-surface-2">
                    <div className={cn("h-full w-1/5 rounded-full bg-brand-600 transition-[width] group-hover:w-full", item.className)} />
                  </div>
                  <p className="mt-1.5 text-[13px] leading-5">
                    <span className="font-mono font-medium">{item.name}</span>{" "}
                    <span className="text-text-muted">
                      {item.spec} · {item.use}
                    </span>
                  </p>
                </li>
              ))}
            </ul>
          </Specimen>
        </div>
      </DsSection>
    </>
  );
}
