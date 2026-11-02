import { cssVars } from "./Accented";
import s from "./faq.module.css";

export type FaqItem = { q: string; a: string };

/** Plain-language FAQ. Native <details>, so it works without JS and with any AT. */
export function Faq({ items }: { items: FaqItem[] }) {
  return (
    <div className={s.faq} data-reveal>
      {items.map((item, i) => (
        <details key={item.q} className={`${s.item} fade-in`} style={cssVars({ "--i": i })}>
          <summary className={s.q}>
            <span>{item.q}</span>
            <span className={s.icon} aria-hidden="true" />
          </summary>
          <p className={s.a}>{item.a}</p>
        </details>
      ))}
    </div>
  );
}
