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
    title: "Brand",
    swatches: [
      { token: "--brand-50", light: "#EEF0FF", dark: "#14152E", use: "Subtle fills" },
      { token: "--brand-100", light: "#DCE0FF", dark: "#1C1E40", use: "Selected rows" },
      { token: "--brand-500", light: "#4B4DED", dark: "#7C7EFF", use: "Focus rings, links" },
      { token: "--brand-600", light: "#3B3BD6", dark: "#8E90FF", use: "Primary buttons" },
      { token: "--brand-700", light: "#2F2FB0", dark: "#A7A9FF", use: "Hover / pressed" },
      { token: "--accent-400", light: "#F7B84B", dark: "#F7B84B", use: "Marigold — live, voice" },
      { token: "--accent-100", light: "#FFF3DC", dark: "#3A2C10", use: "Accent backgrounds" },
    ],
  },
  {
    title: "Neutrals · Stone",
    swatches: [
      { token: "--bg", light: "#FBFBFA", dark: "#0B0B0D" },
      { token: "--surface", light: "#FFFFFF", dark: "#141417" },
      { token: "--surface-2", light: "#F4F4F2", dark: "#1B1B1F" },
      { token: "--border", light: "#E7E6E3", dark: "#2A2A30" },
      { token: "--text", light: "#17171A", dark: "#F2F2F3" },
      { token: "--text-muted", light: "#5F5E66", dark: "#A1A0A8" },
      { token: "--text-subtle", light: "#8C8B93", dark: "#76757D" },
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

const typeScale = [
  { role: "Display", spec: "Geist 40/44 → 72/76 · 600", className: "font-display text-[40px] leading-[44px] tracking-[-0.02em] md:text-[72px] md:leading-[76px]", sample: "Your phone rings." },
  { role: "H1", spec: "Geist 28/34 → 36/42 · 600", className: "font-display text-[28px] leading-[34px] md:text-4xl md:leading-[42px]", sample: "Good morning, Lakshmi" },
  { role: "H2", spec: "Geist 22/28 → 28/34 · 600", className: "font-display text-[22px] leading-7 md:text-[28px] md:leading-[34px]", sample: "Recent calls" },
  { role: "H3", spec: "Inter 18/26 → 20/28 · 600", className: "text-lg leading-[26px] md:text-xl md:leading-7", sample: "Finish setting up" },
  { role: "Body L", spec: "Inter 17/26 · 400", className: "text-[17px] leading-[26px] font-normal", sample: "Priya booked 9 appointments today." },
  { role: "Body", spec: "Inter 15/24 → 16/24 · 400", className: "text-[15px] leading-6 font-normal md:text-base", sample: "Calls will appear here once Priya starts answering." },
  { role: "Small", spec: "Inter 13/20 · 400–500", className: "text-[13px] leading-5 font-medium", sample: "6:15 pm · 2m 14s" },
  { role: "Numbers", spec: "Inter tabular 32/36 → 44/48 · 600", className: "text-[32px] leading-9 tabular-nums md:text-[44px] md:leading-[48px]", sample: "₹1,20,000" },
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
      <DsSection id="colour" title="Colour" description="Neutral-led, one confident brand colour and one warm accent. Toggle the theme to see dark values.">
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
        </div>
      </DsSection>

      <DsSection id="type" title="Typography" description="Geist for display and headings, Inter for everything else. Indic scripts use Noto Sans with taller lines.">
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
                నమస్కారం, సన్‌రైజ్ క్లినిక్ నుంచి ప్రియ మాట్లాడుతున్నాను.
              </p>
            </div>
            <div>
              <p className="mb-1 text-sm font-semibold">Hindi · Noto Sans Devanagari</p>
              <p lang="hi" className="text-[17px]">
                नमस्ते, मैं सनराइज़ क्लिनिक से प्रिया बोल रही हूँ।
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
