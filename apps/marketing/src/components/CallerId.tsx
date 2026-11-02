import { content, type Copy } from "@/content";
import s from "./callerid.module.css";

const cssVar = (vars: Record<string, string | number>) => vars as React.CSSProperties;

const Phone = () => (
  <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
    <path d="M6.6 10.8a15.1 15.1 0 0 0 6.6 6.6l2.2-2.2a1 1 0 0 1 1-.25 11.4 11.4 0 0 0 3.6.57 1 1 0 0 1 1 1V20a1 1 0 0 1-1 1A17 17 0 0 1 3 4a1 1 0 0 1 1-1h3.5a1 1 0 0 1 1 1c0 1.25.2 2.45.57 3.57a1 1 0 0 1-.25 1Z" />
  </svg>
);

export function CallerId({ copy = content.en }: { copy?: Copy }) {
  const { callerId: c } = copy;
  const initials = c.caller
    .split(" ")
    .map((w) => w[0])
    .join("");
  return (
    <section id="caller-id" className={`${s.caller} grain offscreen`} aria-labelledby="caller-title">
      <div className={s.copy} data-reveal>
        <p className={`${s.eyebrow} mono-label fade-in`}>{c.eyebrow}</p>
        <h2 id="caller-title" className={s.title}>
          <span className="mask">
            <span className="mask-in">{c.titleBefore}</span>
          </span>
          <span className="mask">
            <span className="mask-in" style={cssVar({ "--i": 1 })}>
              {c.titleAccentBefore}
              <em className="accent">{c.titleAccent}</em>
              {c.titleAfter}
            </span>
          </span>
        </h2>
        <p className={`${s.body} fade-in`} style={cssVar({ "--i": 2 })}>
          {c.body}
        </p>
        <ul className={s.points}>
          {c.points.map((p, i) => (
            <li key={p} className={`${s.point} fade-in`} style={cssVar({ "--i": 3 + i })}>
              <span className={s.check} aria-hidden="true">
                <svg
                  viewBox="0 0 12 12"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.8"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="m2.5 6.2 2.3 2.3 4.7-5" />
                </svg>
              </span>
              {p}
            </li>
          ))}
        </ul>
      </div>

      <div className={s.phoneCol} data-reveal>
        <div className={`${s.phone} fade-in`} role="img" aria-label={c.screenLabel}>
          <div className={s.screen} aria-hidden="true">
            <span className={s.island} />
            <span className={s.date}>{c.date}</span>
            <span className={s.clock}>{c.time}</span>
            <div className={`${s.card} fade-in`} style={cssVar({ "--i": 2, "--d": "200ms" })}>
              <span className={s.incoming}>{c.incoming}</span>
              <span className={s.avatar}>{initials}</span>
              <span className={s.name}>
                {c.caller}
                <svg className={s.tick} viewBox="0 0 24 24" fill="currentColor">
                  <path d="M12 1.5 14.6 4l3.5-.4.9 3.4 3 1.9-1.3 3.3 1.3 3.3-3 1.9-.9 3.4-3.5-.4L12 22.5 9.4 20l-3.5.4-.9-3.4-3-1.9L3.3 12 2 8.7l3-1.9.9-3.4 3.5.4Zm-1.3 13.9 6-6-1.4-1.4-4.6 4.6-2.3-2.3L7 11.7Z" />
                </svg>
              </span>
              <span className={s.verified}>✓ {c.verified}</span>
              <span className={s.sub}>{c.callerSub}</span>
            </div>
            <div className={s.buttons}>
              <span className={s.btn}>
                <span className={`${s.round} ${s.decline}`}>
                  <Phone />
                </span>
                {c.decline}
              </span>
              <span className={s.btn}>
                <span className={`${s.round} ${s.accept}`}>
                  <Phone />
                </span>
                {c.accept}
              </span>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
