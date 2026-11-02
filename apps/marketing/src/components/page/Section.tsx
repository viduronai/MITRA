import { Accented, accentLine, cssVars } from "./Accented";
import s from "./page.module.css";

type Tone = "chalk" | "ink" | "night";

type Props = {
  id?: string;
  tone?: Tone;
  label?: string;
  /** Heading lines (masked reveal on scroll). */
  title?: string[];
  accent?: string;
  lead?: string;
  tight?: boolean;
  /** Estimated rendered height for content-visibility (keeps the scrollbar stable). */
  cis?: string;
  children?: React.ReactNode;
};

/** A full-bleed section with an optional label / heading / lead row. */
export function Section({ id, tone = "chalk", label, title, accent, lead, tight, cis = "900px", children }: Props) {
  const headingId = id ? `${id}-title` : undefined;
  const accentAt = title ? accentLine(title, accent) : -1;
  return (
    <section
      id={id}
      className={`${s.section} ${tone === "chalk" ? "on-chalk" : "grain"} offscreen`}
      data-tone={tone}
      data-tight={tight ? "" : undefined}
      style={cssVars({ "--cis": cis })}
      aria-labelledby={title ? headingId : undefined}
    >
      <div className={s.inner}>
        {(label || title || lead) && (
          <div className={s.head} data-solo={lead ? undefined : ""} data-reveal>
            <div>
              {label && <p className={`${s.label} fade-in`}>{label}</p>}
              {title && (
                <h2 id={headingId} className={s.h2}>
                  {title.map((line, i) => (
                    <span key={line} className="mask">
                      <span className="mask-in" style={cssVars({ "--i": i })}>
                        <Accented text={line} accent={i === accentAt ? accent : undefined} />
                      </span>
                    </span>
                  ))}
                </h2>
              )}
            </div>
            {lead && (
              <p className={`${s.lead} fade-in`} style={cssVars({ "--i": 2 })}>
                {lead}
              </p>
            )}
          </div>
        )}
        {children}
      </div>
    </section>
  );
}

export type CardItem = { title: string; text: string; note?: string };

/** Numbered card grid. */
export function Cards({ items, numbered = true }: { items: CardItem[]; numbered?: boolean }) {
  return (
    <ul className={s.cards} data-reveal>
      {items.map((c, i) => (
        <li key={c.title} className={`${s.card} fade-in`} style={cssVars({ "--i": i })}>
          {numbered && <span className={s.cardIndex}>{String(i + 1).padStart(2, "0")}</span>}
          <h3 className={s.cardTitle}>{c.title}</h3>
          <p className={s.cardText}>{c.text}</p>
          {c.note && <p className={s.cardNote}>{c.note}</p>}
        </li>
      ))}
    </ul>
  );
}

export type CheckItem = { title: string; text: string };

export function Checklist({ items }: { items: CheckItem[] }) {
  return (
    <ul className={s.checks} data-reveal>
      {items.map((c, i) => (
        <li key={c.title} className="fade-in" style={cssVars({ "--i": i })}>
          <div>
            <b>{c.title}</b>
            {c.text}
          </div>
        </li>
      ))}
    </ul>
  );
}

export type StatItem = { value: string; label: string };

export function Stats({ items }: { items: StatItem[] }) {
  return (
    <ul className={s.stats} data-reveal>
      {items.map((st, i) => (
        <li key={st.label} className={`${s.stat} fade-in`} style={cssVars({ "--i": i })}>
          <span className={s.statNum}>{st.value}</span>
          <span className={s.statLabel}>{st.label}</span>
        </li>
      ))}
    </ul>
  );
}
