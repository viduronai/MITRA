import { copy } from "@/content";
import { HeroIntro } from "./HeroIntro";
import { HeroVideo } from "./HeroVideo";
import { Wordmark } from "./Wordmark";
import s from "./hero.module.css";

const nbsp = (text: string) => text.replace(/ /g, " ");

export function Sparkle({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M12 2.6C12.55 2.6 12.88 3.15 13.08 4.7c.62 4.7 1.52 5.6 6.22 6.22 1.55.2 2.1.53 2.1 1.08s-.55.88-2.1 1.08c-4.7.62-5.6 1.52-6.22 6.22-.2 1.55-.53 2.1-1.08 2.1s-.88-.55-1.08-2.1c-.62-4.7-1.52-5.6-6.22-6.22C3.15 12.88 2.6 12.55 2.6 12s.55-.88 2.1-1.08c4.7-.62 5.6-1.52 6.22-6.22C11.12 3.15 11.45 2.6 12 2.6Z" />
    </svg>
  );
}

export function Hero() {
  const { hero, nav } = copy;
  return (
    <section id="top" className={s.hero} aria-labelledby="hero-title" data-hero-root>
      <header className={s.masthead}>
        <a href="#top" className={s.wordmark} aria-label={nav.home} data-hero="wordmark">
          <Wordmark />
        </a>
        <div className={s.hairline} data-hero="hairline" aria-hidden="true" />
        <nav className={s.nav} aria-label="Primary">
          {nav.links.map((link, i) => (
            <a
              key={link.href}
              href={link.href}
              className={s.navLink}
              data-hero="nav"
              data-outer={i === 0 || i === nav.links.length - 1 ? "" : undefined}
            >
              {link.label}
            </a>
          ))}
        </nav>
      </header>

      <div className={s.gap} aria-hidden="true" />

      <div className={s.copy}>
        <p className={s.badge} data-hero="badge">
          <Sparkle className={s.star} />
          <span>{hero.badge}</span>
        </p>
        <h1 id="hero-title" className={s.h1}>
          <span className={s.line}>
            <span className={s.lineInner} data-hero="line">
              {hero.line1}
            </span>
          </span>
          <span className={`${s.line} ${s.line2}`}>
            <span className={s.lineInner} data-hero="line">
              {hero.line2Before}
              <em className={s.hello} data-hero="hello">
                {hero.line2Accent}
              </em>
              {hero.line2After}
            </span>
          </span>
        </h1>
        <p className={s.sub} data-hero="sub">
          {hero.sub.map(nbsp).join(" ")}
        </p>
        <div className={s.actions}>
          <a href="#demo" className={`btn btn-solid ${s.primary}`} data-hero="primary">
            {hero.primary}
          </a>
          <a href="#hear" className={`btn btn-ghost ${s.secondary}`} data-hero="secondary">
            <svg className={s.play} viewBox="0 0 9 10" aria-hidden="true">
              <path d="M0 0.8v8.4a.6.6 0 0 0 .9.5l7.4-4.2a.6.6 0 0 0 0-1L.9.3A.6.6 0 0 0 0 .8Z" />
            </svg>
            {hero.secondary}
          </a>
        </div>
      </div>

      <div className={s.field} aria-hidden="true">
        {/* Our own render of the horizon (not a frame of the licensed video):
            paints immediately as the hero image, then the video fades in over it. */}
        {/* eslint-disable-next-line @next/next/no-img-element -- geometry is set by the Vexel CSS, not next/image */}
        <img
          className={`${s.video} ${s.poster}`}
          src="/hero-horizon.webp"
          alt=""
          width={1240}
          height={740}
          fetchPriority="high"
        />
        <HeroVideo className={s.video} />
      </div>
      <span className={s.scrollCue} aria-hidden="true" data-hero="cue" />
      <HeroIntro />
    </section>
  );
}
