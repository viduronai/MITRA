import { Fragment } from "react";
import { copy } from "@/content";
import { DotNumber } from "./DotNumber";
import s from "./pricing.module.css";

const icons = [
  // Answers in under a second: bolt in a tile
  <svg key="a" className={s.icon} viewBox="0 0 24 24" aria-hidden="true">
    <rect x="2.4" y="2.4" width="19.2" height="19.2" rx="6.2" fill="#fff" />
    <path d="M13 6.5 8.5 13H12l-1 4.5L15.5 11H12Z" fill="#05070d" />
  </svg>,
  // 3 languages: dual pill (Vesper)
  <svg key="b" className={s.icon} viewBox="0 0 24 24" aria-hidden="true">
    <defs>
      <linearGradient id="pl1" x1="3" y1="2" x2="14" y2="22">
        <stop offset="0" stopColor="#9fe3fa" stopOpacity=".55" />
        <stop offset="1" stopColor="#123a9e" stopOpacity=".7" />
      </linearGradient>
      <linearGradient id="pl2" x1="13" y1="2" x2="22" y2="22">
        <stop offset="0" stopColor="#123a9e" stopOpacity=".5" />
        <stop offset="1" stopColor="#38c6f4" stopOpacity=".8" />
      </linearGradient>
    </defs>
    <rect x="3.4" y="2.6" width="7.2" height="18.8" rx="3.6" fill="url(#pl1)" />
    <rect x="13.4" y="2.6" width="7.2" height="18.8" rx="3.6" fill="url(#pl2)" />
    <rect x="9.2" y="10.9" width="5.6" height="2.2" rx="1.1" fill="#38c6f4" />
  </svg>,
  // Talk-time: waveform tile
  <svg key="c" className={s.icon} viewBox="0 0 24 24" aria-hidden="true">
    <rect x="2.4" y="2.4" width="19.2" height="19.2" rx="6.2" fill="#38c6f4" />
    <path d="M7.5 10.5v3M10.5 8v8M13.5 9.5v5M16.5 11v2" stroke="#05070d" strokeWidth="1.85" strokeLinecap="round" />
  </svg>,
];

// Doto has no ₹ glyph, so the rupee is drawn on the same 5×7 dot grid.
const RUPEE = ["11111", "00010", "11111", "01100", "00100", "00010", "00001"];

function RupeeDots() {
  return (
    <svg className={s.rupee} viewBox="0 0 5 7" aria-hidden="true">
      {RUPEE.flatMap((row, y) =>
        row
          .split("")
          .map((on, x) =>
            on === "1" ? (
              <rect key={`${x}-${y}`} x={x + 0.11} y={y + 0.11} width="0.78" height="0.78" rx="0.14" />
            ) : null,
          ),
      )}
    </svg>
  );
}

export function Pricing() {
  const { pricing: p } = copy;
  const [before, accent] = p.line.split(p.lineAccent);
  return (
    <section id="pricing" className={`${s.pricing} grain offscreen`} aria-labelledby="pricing-title">
      <p className={`${s.eyebrow} mono-label`}>{p.eyebrow}</p>
      <h2 id="pricing-title" className="sr-only">
        {p.srTitle}
      </h2>
      <ul className={s.tiers}>
        {p.tiers.map((t, i) => (
          <Fragment key={t.name}>
            {i > 0 && (
              <li className={s.sep} aria-hidden="true">
                ·
              </li>
            )}
            <li className={s.tier} data-featured={i === 1 ? "" : undefined}>
              <span className={s.num}>
                <span className="sr-only">₹</span>
                <RupeeDots />
                <DotNumber value={t.price.replace("₹", "")} delay={i * 160} />
              </span>
              <span className={s.name}>{t.name}</span>
            </li>
          </Fragment>
        ))}
      </ul>
      <div data-reveal>
        <p className={`${s.per} fade-in`}>{p.perMinute}</p>
        <p className={`${s.line} fade-in`} style={{ "--i": 1 } as React.CSSProperties}>
          {before}
          <em className="accent">{p.lineAccent}</em>
          {accent}
        </p>
        <p className={`${s.fine} fade-in`} style={{ "--i": 2 } as React.CSSProperties}>
          {p.fine}
        </p>
        <div className={`${s.cta} fade-in`} style={{ "--i": 3 } as React.CSSProperties}>
          <a href="/pricing" className="btn btn-solid">
            {p.cta}
          </a>
        </div>
      </div>
      <div className={s.statsWrap}>
        <ul className={s.stats} data-reveal>
          {p.stats.map((label, i) => (
            <li key={label} className={`${s.stat} fade-in`} style={{ "--i": i } as React.CSSProperties}>
              {icons[i]}
              {label}
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
