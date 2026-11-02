import { Accented, accentLine, cssVars } from "./Accented";
import s from "./page.module.css";

export type HeroAction = { label: string; href: string; kind?: "solid" | "ghost" };

type Props = {
  eyebrow: string;
  /** Headline lines; `accent` is italicised in the last line it appears in. */
  title: string[];
  accent?: string;
  sub?: string;
  actions?: HeroAction[];
  /** Optional visual on the right (stacks below on phones). */
  aside?: React.ReactNode;
  children?: React.ReactNode;
};

/** Night hero with the horizon arc. Entrance is CSS-only so LCP never waits on JS. */
export function PageHero({ eyebrow, title, accent, sub, actions, aside, children }: Props) {
  const accentAt = accentLine(title, accent);
  return (
    <section className={`${s.hero} grain`} aria-labelledby="page-title">
      <div className={s.horizon} aria-hidden="true" />
      <div className={s.heroInner} data-aside={aside ? "" : undefined}>
        <div>
          <p className={`${s.eyebrow} ${s.fadeUp}`} style={cssVars({ "--i": -3 })}>
            {eyebrow}
          </p>
          <h1 id="page-title" className={s.h1}>
            {title.map((line, i) => (
              <span key={line} className={s.line}>
                <span className={s.lineIn} style={cssVars({ "--i": i })}>
                  <Accented text={line} accent={i === accentAt ? accent : undefined} />
                </span>
              </span>
            ))}
          </h1>
          {sub && (
            <p className={`${s.sub} ${s.fadeUp}`} style={cssVars({ "--i": 1 })}>
              {sub}
            </p>
          )}
          {actions && actions.length > 0 && (
            <div className={`${s.actions} ${s.fadeUp}`} style={cssVars({ "--i": 2 })}>
              {actions.map((a) => (
                <a
                  key={a.href + a.label}
                  href={a.href}
                  className={`btn ${a.kind === "ghost" ? "btn-ghost" : "btn-solid"}`}
                >
                  {a.label}
                </a>
              ))}
            </div>
          )}
          {children}
        </div>
        {aside && (
          <div className={s.fadeUp} style={cssVars({ "--i": 3 })}>
            {aside}
          </div>
        )}
      </div>
    </section>
  );
}
