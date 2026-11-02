"use client";

import { useId, useState } from "react";
import type { agencies } from "@/content/pages/agencies";
import s from "./agencies.module.css";

/** Type a name, pick a colour: the client console re-brands live. */
export function BrandPreview({ t }: { t: (typeof agencies)["brand"] }) {
  const ids = useId();
  const [name, setName] = useState("");
  const [color, setColor] = useState(t.colors[0].value);
  const brand = name.trim() || t.namePlaceholder;
  const initials = brand
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? "")
    .join("");

  return (
    <div className={s.brand}>
      <div className={s.brandControls}>
        <label htmlFor={`${ids}-name`} className={s.fieldLabel}>
          {t.nameLabel}
        </label>
        <input
          id={`${ids}-name`}
          className={s.input}
          value={name}
          maxLength={32}
          placeholder={t.namePlaceholder}
          onChange={(e) => setName(e.target.value)}
        />
        <fieldset className={s.swatches}>
          <legend className={s.fieldLabel}>{t.colorLabel}</legend>
          <div>
            {t.colors.map((c) => (
              <label key={c.value} className={s.swatch} style={{ "--c": c.value } as React.CSSProperties}>
                <input
                  type="radio"
                  name={`${ids}-color`}
                  value={c.value}
                  checked={color === c.value}
                  onChange={() => setColor(c.value)}
                />
                <span aria-hidden="true" />
                <b className="sr-only">{c.name}</b>
              </label>
            ))}
          </div>
        </fieldset>
      </div>

      <figure className={s.console} style={{ "--brand": color } as React.CSSProperties}>
        <figcaption className="sr-only">{t.preview}</figcaption>
        <div className={s.consoleBar}>
          <span className={s.logo} aria-hidden="true">
            {initials}
          </span>
          <span className={s.consoleName}>{brand}</span>
          <span className={s.dots} aria-hidden="true">
            <i />
            <i />
            <i />
          </span>
        </div>
        <div className={s.consoleBody}>
          <p className={s.consoleClient}>
            {t.client} · {t.today}
          </p>
          <ul className={s.consoleStats}>
            {t.stats.map(([label, value]) => (
              <li key={label}>
                <b>{value}</b>
                <span>{label}</span>
              </li>
            ))}
          </ul>
          <span className={s.consoleBtn} aria-hidden="true">
            + {t.action}
          </span>
          <p className={s.powered}>{t.powered}</p>
        </div>
      </figure>
    </div>
  );
}
