import { content, type Copy } from "@/content";
import { media } from "@/lib/media";
import { LazyVideo } from "./LazyVideo";
import s from "./team.module.css";

const cssVar = (vars: Record<string, string | number>) => vars as React.CSSProperties;

function Accent({ text, word }: { text: string; word: string }) {
  const at = text.toLowerCase().lastIndexOf(word.toLowerCase());
  if (at < 0) return <>{text}</>;
  return (
    <>
      {text.slice(0, at)}
      <span className={s.sky}>{text.slice(at, at + word.length)}</span>
      {text.slice(at + word.length)}
    </>
  );
}

export function Team({ copy = content.en }: { copy?: Copy }) {
  const { team } = copy;
  return (
    <section
      id="team"
      className={`${s.team} on-chalk offscreen`}
      style={cssVar({ "--cis": "2300px" })}
      aria-labelledby="team-title"
    >
      {/* A · Targo hero */}
      <div className={s.top}>
        <div className={s.topMedia} aria-hidden="true">
          <LazyVideo className={s.video} src={media.teamHero} />
        </div>
        <div className={s.topScrim} aria-hidden="true" />
        <div className={s.topCopy} data-reveal>
          <p className={`${s.eyebrow} mono-label fade-in`}>{team.eyebrow}</p>
          <h2 id="team-title" className={s.stair}>
            {team.lines.map((line, i) => (
              <span key={line} className={`mask ${i > 0 ? s.indent : ""}`}>
                <span className="mask-in" style={cssVar({ "--i": i })}>
                  {i === team.lines.length - 1 ? <Accent text={line} word={team.accentWord} /> : line}
                </span>
              </span>
            ))}
          </h2>
        </div>
        <div className={s.ctaRow}>
          <a href="#demo" className="btn btn-blue btn-chamfer">
            {team.cta}
            <span className="trail" aria-hidden="true" />
          </a>
        </div>
      </div>

      {/* B · Targo about */}
      <div className={s.about}>
        <div className={s.aboutCopy} data-reveal>
          <h3 className={s.h3}>
            {team.subTitle.map((line, i) => (
              <span key={line} className={`mask ${i > 0 ? s.indent : ""}`}>
                <span className={`mask-in ${i > 0 ? s.sky : ""}`} style={cssVar({ "--i": i })}>
                  {line}
                </span>
              </span>
            ))}
          </h3>
          <p className={`${s.text} fade-in`} style={cssVar({ "--i": 2 })}>
            {team.body}
          </p>
          <a href="/how-it-works" className={`${s.more} fade-in`} style={cssVar({ "--i": 3 })}>
            {team.more}
            <span aria-hidden="true">→</span>
          </a>
        </div>
        <div className={s.aboutMediaCol}>
          <div className={s.aboutMedia} aria-hidden="true">
            <LazyVideo className={s.video} src={media.teamAbout} />
          </div>
        </div>
      </div>

      {/* C · Team map */}
      <div className={s.map}>
        <div className={s.mapHead}>
          <span className="mono-label">{team.mapLabel}</span>
          <span className="mono-label">{team.mapNote}</span>
        </div>
        <ol className={s.nodes} data-reveal>
          {team.roles.map((role, i) => (
            <li key={role.name} className={`${s.node} fade-in`} style={cssVar({ "--i": i })}>
              <span className={s.orb} aria-hidden="true" />
              {i < team.roles.length - 1 && <span className={s.beam} aria-hidden="true" />}
              <span className={s.index}>{String(i + 1).padStart(2, "0")}</span>
              <h4 className={s.role}>{role.name}</h4>
              <p className={s.duty}>{role.duty}</p>
              <span className={s.status}>{role.status}</span>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
