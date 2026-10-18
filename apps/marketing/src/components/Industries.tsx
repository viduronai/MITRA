import { copy } from "@/content";
import { SampleButton } from "./SampleButton";
import s from "./industries.module.css";

const BARS = [8, 14, 20, 12, 17, 9, 15, 21, 11, 7, 13, 18, 10, 6];

export function Industries() {
  const { industries: ind } = copy;
  return (
    <section
      id="industries"
      className={`${s.industries} on-chalk offscreen`}
      style={{ "--cis": "1100px" } as React.CSSProperties}
      aria-labelledby="ind-title"
    >
      <div className={s.head} data-reveal>
        <div>
          <p className={`${s.eyebrow} mono-label fade-in`}>{ind.eyebrow}</p>
          <h2 id="ind-title" className={s.title}>
            <span className="mask">
              <span className="mask-in">{ind.title[0]}</span>
            </span>
            <span className="mask">
              <span className="mask-in" style={{ "--i": 1 } as React.CSSProperties}>
                <em className="accent">{ind.title[1]}</em>
              </span>
            </span>
          </h2>
        </div>
      </div>

      <ul className={s.grid} data-reveal>
        {ind.cards.map((card, i) => {
          const agency = card.scenario === null;
          return (
            <li
              key={card.id}
              id={agency ? "agencies" : undefined}
              className={`${s.card} ${agency ? s.featured : ""} fade-in`}
              style={{ "--i": i } as React.CSSProperties}
            >
              <span className={s.index}>{String(i + 1).padStart(2, "0")}</span>
              <h3 className={s.name}>
                <a href={card.href} className={s.nameLink}>
                  {card.name}
                </a>
              </h3>
              <p className={s.line}>{card.line}</p>
              <ul className={s.tasks}>
                {card.tasks.map((t) => (
                  <li key={t}>{t}</li>
                ))}
              </ul>
              <div className={s.foot}>
                {card.scenario ? (
                  <>
                    <SampleButton className={s.sample} scenario={card.scenario} label={ind.sample} industry={card.name}>
                      <span className={s.playDot} aria-hidden="true">
                        <svg viewBox="0 0 9 10" fill="currentColor">
                          <path d="M0 .8v8.4a.6.6 0 0 0 .9.5l7.4-4.2a.6.6 0 0 0 0-1L.9.3A.6.6 0 0 0 0 .8Z" />
                        </svg>
                      </span>
                      {ind.sample}
                    </SampleButton>
                    <span className={s.bars} aria-hidden="true">
                      {BARS.map((h, j) => (
                        <i key={j} style={{ height: `${h}px` }} />
                      ))}
                    </span>
                  </>
                ) : (
                  <span className={s.partner} aria-hidden="true">
                    {ind.partner} →
                  </span>
                )}
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
