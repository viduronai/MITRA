"use client";

import { useId, useState } from "react";
import type { agencies } from "@/content/pages/agencies";
import { wholesale } from "@/content/pages/agencies";
import { rates, type TierId } from "@/content/pricing";
import { Range } from "../pricing/CostCalculator";
import p from "../pricing/pricing-page.module.css";
import s from "./agencies.module.css";

const inr = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });
const TIERS: { id: TierId; name: string }[] = [
  { id: "smart", name: "Smart" },
  { id: "natural", name: "Natural" },
  { id: "signature", name: "Signature" },
];

/** clients × minutes × (your retail price − wholesale) per month. */
export function margin(clients: number, minutes: number, tier: TierId, retail: number) {
  const volume = clients * minutes;
  const revenue = volume * retail;
  const cost = volume * wholesale[tier];
  return { revenue, cost, margin: revenue - cost, pct: revenue > 0 ? ((revenue - cost) / revenue) * 100 : 0 };
}

export function MarginCalculator({ t }: { t: (typeof agencies)["calc"] }) {
  const ids = useId();
  const [clients, setClients] = useState(8);
  const [minutes, setMinutes] = useState(2000);
  const [tier, setTier] = useState<TierId>("natural");
  const [retail, setRetail] = useState<number>(rates.natural);
  const r = margin(clients, minutes, tier, retail);

  const pickTier = (id: TierId) => {
    setTier(id);
    setRetail(rates[id]);
  };

  return (
    <div className={p.calc}>
      <div className={p.controls}>
        <Range id={`${ids}-c`} label={t.clients} slider={{ value: clients, min: 1, max: 50, step: 1 }} onChange={setClients} />
        <Range
          id={`${ids}-m`}
          label={t.minutes}
          slider={{ value: minutes, min: 500, max: 10000, step: 500 }}
          onChange={setMinutes}
        />
        <fieldset className={p.tierPick}>
          <legend>{t.tier}</legend>
          <div className={p.segments}>
            {TIERS.map((item) => (
              <label key={item.id} className={p.segment}>
                <input
                  type="radio"
                  name={`${ids}-tier`}
                  value={item.id}
                  checked={tier === item.id}
                  onChange={() => pickTier(item.id)}
                />
                <span>
                  {item.name}
                  <small>₹{wholesale[item.id]}</small>
                </span>
              </label>
            ))}
          </div>
        </fieldset>
        <Range
          id={`${ids}-r`}
          label={t.retail}
          unit="₹"
          slider={{ value: retail, min: wholesale[tier], max: wholesale[tier] * 3, step: 0.1 }}
          onChange={(v) => setRetail(Math.round(v * 10) / 10)}
        />
      </div>

      <div className={p.result}>
        <p className={p.resultLabel}>{t.margin}</p>
        <p className={p.resultNum} aria-live="polite" aria-atomic="true">
          <span>₹{inr.format(r.margin)}</span>
          <span className={p.resultPer}>{t.perMonth}</span>
        </p>
        <p className={p.breakdown}>{t.marginPct.replace("{pct}", r.pct.toFixed(0))}</p>
        <dl className={s.sums}>
          <div>
            <dt>{t.revenue}</dt>
            <dd>₹{inr.format(r.revenue)}</dd>
          </div>
          <div>
            <dt>{t.cost}</dt>
            <dd>₹{inr.format(r.cost)}</dd>
          </div>
        </dl>
        <p className={p.calcNote}>{t.note}</p>
      </div>
    </div>
  );
}
