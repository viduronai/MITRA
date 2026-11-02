"use client";

import { useState } from "react";
import s from "./pricing-page.module.css";

/**
 * ▶ voice sample for a tier. TODO(voice): play the recorded sample once the
 * voice team delivers per-tier clips; until then it says the sample is coming.
 */
export function SampleChip({ label, tier, soon }: { label: string; tier: string; soon: string }) {
  const [asked, setAsked] = useState(false);
  return (
    <div className={s.sampleWrap}>
      <button
        type="button"
        className={s.sample}
        aria-label={`${label}: ${tier}`}
        aria-describedby={asked ? `sample-${tier}` : undefined}
        onClick={() => setAsked(true)}
      >
        <span className={s.samplePlay} aria-hidden="true">
          <svg viewBox="0 0 9 10" fill="currentColor">
            <path d="M0 .8v8.4a.6.6 0 0 0 .9.5l7.4-4.2a.6.6 0 0 0 0-1L.9.3A.6.6 0 0 0 0 .8Z" />
          </svg>
        </span>
        {label} {tier}
        <span className={s.sampleBars} aria-hidden="true">
          <i />
          <i />
          <i />
          <i />
          <i />
        </span>
      </button>
      <span id={`sample-${tier}`} className={s.sampleSoon} role="status">
        {asked ? soon : ""}
      </span>
    </div>
  );
}
