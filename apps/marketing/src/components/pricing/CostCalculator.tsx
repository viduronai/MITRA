"use client";

import { useId, useState } from "react";
import type { PricingCopy, TierId } from "@/content/pricing";
import { rates } from "@/content/pricing";
import { RupeeDots } from "../RupeeDots";
import s from "./pricing-page.module.css";

const inr = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });
const fmt = (template: string, vars: Record<string, string | number>) =>
  template.replace(/\{(\w+)\}/g, (_, k: string) => String(vars[k] ?? ""));

export type CalcResult = { minutes: number; mitra: number; telecallers: number; telecallerCost: number };

/** calls/day × avg minutes × 30 days × tier rate, vs telecallers for the same talk-time. */
export function estimate(callsPerDay: number, avgMinutes: number, tier: TierId): CalcResult {
  const minutes = callsPerDay * avgMinutes * rates.daysPerMonth;
  const telecallers = Math.max(1, Math.ceil(minutes / rates.telecallerMinutes));
  return {
    minutes,
    mitra: Math.round(minutes * rates[tier]),
    telecallers,
    telecallerCost: telecallers * rates.telecallerMonthly,
  };
}

export type Slider = { value: number; min: number; max: number; step: number };

export function Range({
  id,
  label,
  unit,
  slider,
  onChange,
}: {
  id: string;
  label: string;
  unit?: string;
  slider: Slider;
  onChange: (v: number) => void;
}) {
  const pct = ((slider.value - slider.min) / (slider.max - slider.min)) * 100;
  return (
    <div className={s.range}>
      <div className={s.rangeTop}>
        <label htmlFor={id}>{label}</label>
        <output htmlFor={id} className={s.rangeValue}>
          {slider.value}
          {unit ? ` ${unit}` : ""}
        </output>
      </div>
      <input
        id={id}
        type="range"
        min={slider.min}
        max={slider.max}
        step={slider.step}
        value={slider.value}
        onChange={(e) => onChange(Number(e.target.value))}
        aria-valuetext={unit ? `${slider.value} ${unit}` : undefined}
        style={{ "--p": `${pct}%` } as React.CSSProperties}
      />
      <div className={s.rangeEnds} aria-hidden="true">
        <span>{slider.min}</span>
        <span>{slider.max}</span>
      </div>
    </div>
  );
}

export function CostCalculator({ t, tiers }: { t: PricingCopy["calc"]; tiers: PricingCopy["tiers"]["items"] }) {
  const ids = useId();
  const [calls, setCalls] = useState(40);
  const [minutes, setMinutes] = useState(2);
  const [tier, setTier] = useState<TierId>("natural");
  const r = estimate(calls, minutes, tier);
  const max = Math.max(r.mitra, r.telecallerCost);
  const saving = r.telecallerCost - r.mitra;

  return (
    <div className={s.calc}>
      <div className={s.controls}>
        <Range
          id={`${ids}-calls`}
          label={t.calls}
          slider={{ value: calls, min: 5, max: 300, step: 5 }}
          onChange={setCalls}
        />
        <Range
          id={`${ids}-min`}
          label={t.minutes}
          unit={t.minutesUnit}
          slider={{ value: minutes, min: 0.5, max: 8, step: 0.5 }}
          onChange={setMinutes}
        />
        <fieldset className={s.tierPick}>
          <legend>{t.tier}</legend>
          <div className={s.segments}>
            {tiers.map((item) => (
              <label key={item.id} className={s.segment}>
                <input
                  type="radio"
                  name={`${ids}-tier`}
                  value={item.id}
                  checked={tier === item.id}
                  onChange={() => setTier(item.id)}
                />
                <span>
                  {item.name}
                  <small>₹{rates[item.id]}</small>
                </span>
              </label>
            ))}
          </div>
        </fieldset>
      </div>

      <div className={s.result}>
        <p className={s.resultLabel}>{t.result}</p>
        <p className={s.resultNum} aria-live="polite" aria-atomic="true">
          <span className="sr-only">₹</span>
          <RupeeDots className={s.resultRupee} />
          <span>{inr.format(r.mitra)}</span>
          <span className={s.resultPer}>{t.perMonth}</span>
        </p>
        <p className={s.breakdown}>
          {fmt(t.breakdown, { calls, minutes, total: inr.format(r.minutes) })}
        </p>

        <div className={s.bars}>
          <div className={s.bar} data-kind="mitra">
            <div className={s.barTop}>
              <span>{t.mitra}</span>
              <span>₹{inr.format(r.mitra)}</span>
            </div>
            <span className={s.track} aria-hidden="true">
              <i style={{ width: `${Math.max(2, (r.mitra / max) * 100)}%` }} />
            </span>
          </div>
          <div className={s.bar} data-kind="human">
            <div className={s.barTop}>
              <span>
                {t.telecallers} ·{" "}
                {r.telecallers === 1 ? t.telecallerOne : fmt(t.telecallerMany, { n: r.telecallers })}
              </span>
              <span>₹{inr.format(r.telecallerCost)}</span>
            </div>
            <span className={s.track} aria-hidden="true">
              <i style={{ width: `${Math.max(2, (r.telecallerCost / max) * 100)}%` }} />
            </span>
          </div>
        </div>
        {saving > 0 && <p className={s.save}>{fmt(t.save, { amount: `₹${inr.format(saving)}` })}</p>}
        <p className={s.calcNote}>{t.note}</p>
      </div>
    </div>
  );
}
