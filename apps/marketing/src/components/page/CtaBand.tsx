import { Accented, accentLine, cssVars } from "./Accented";
import s from "./cta.module.css";

type Props = {
  title: string[];
  accent?: string;
  text?: string;
  primary: { label: string; href: string };
  secondary?: { label: string; href: string };
};

/** Closing scene on every page: the voice orb returns, one sentence, one call to action. */
export function CtaBand({ title, accent, text, primary, secondary }: Props) {
  const accentAt = accentLine(title, accent);
  return (
    <section className={`${s.band} grain offscreen`} aria-labelledby="cta-title">
      <div className={s.orb} aria-hidden="true">
        <span />
        <span />
        <span />
        <i />
      </div>
      <div className={s.copy} data-reveal>
        <h2 id="cta-title" className={s.title}>
          {title.map((line, i) => (
            <span key={line} className="mask">
              <span className="mask-in" style={cssVars({ "--i": i })}>
                <Accented text={line} accent={i === accentAt ? accent : undefined} />
              </span>
            </span>
          ))}
        </h2>
        {text && (
          <p className={`${s.text} fade-in`} style={cssVars({ "--i": 2 })}>
            {text}
          </p>
        )}
        <div className={`${s.actions} fade-in`} style={cssVars({ "--i": 3 })}>
          <a href={primary.href} className="btn btn-solid">
            {primary.label}
          </a>
          {secondary && (
            <a href={secondary.href} className="btn btn-ghost">
              {secondary.label}
            </a>
          )}
        </div>
      </div>
    </section>
  );
}
