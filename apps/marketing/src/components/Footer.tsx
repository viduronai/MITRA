import { content, type Copy, type Locale } from "@/content";
import { LangSwitch } from "./LangSwitch";
import { media } from "@/lib/media";
import { LazyVideo } from "./LazyVideo";
import { Wordmark } from "./Wordmark";
import s from "./footer.module.css";

const chipIcons = [
  null,
  <svg key="lang" viewBox="0 0 24 24" aria-hidden="true">
    <path d="M4 5h9M8.5 3v2M6 5c.6 3.6 3 6.4 6 8M11 5c-.8 3.6-3.6 6.8-7 8.5M13 20l4-9 4 9M14.4 17h5.2" />
  </svg>,
  <svg key="shield" viewBox="0 0 24 24" aria-hidden="true">
    <path d="M12 3 4.5 6v5.5c0 4.6 3.1 8.2 7.5 9.5 4.4-1.3 7.5-4.9 7.5-9.5V6Z" />
    <path d="m9 12 2.2 2.2L15.5 10" />
  </svg>,
];

type Props = {
  copy?: Copy;
  langHrefs: Record<Locale, string>;
  homeHref?: string;
  ctaHref?: string;
};

export function Footer({ copy = content.en, langHrefs, homeHref = "#top", ctaHref = "#demo" }: Props) {
  const { footer: f, nav } = copy;
  return (
    <footer className={`${s.footer} on-chalk offscreen`}>
      <div className={s.stage} aria-hidden="true">
        <LazyVideo className={s.video} src={media.footerMeadow} poster={media.footerMeadowPoster} />
      </div>
      {/* Dotless ı plus our own round frosted tittle: the font's square dot
          floated far above the stem at this size and read as "m▫tra". */}
      <p className={s.wordmark} aria-hidden="true">
        m
        <span className={s.stem}>
          ı<span className={s.tittle} />
        </span>
        tra
      </p>
      <div className={s.fog} aria-hidden="true" />

      <div className={s.content}>
        <div className={s.brand}>
          <a href={homeHref} className={s.logo} aria-label={nav.home}>
            <Wordmark />
          </a>
          <h2 className={s.title}>{f.title}</h2>
          <p className={s.text}>{f.text}</p>
          <a href={ctaHref} className={s.cta}>
            <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
              <path d="M6.6 10.8a15.1 15.1 0 0 0 6.6 6.6l2.2-2.2a1 1 0 0 1 1-.25 11.4 11.4 0 0 0 3.6.57 1 1 0 0 1 1 1V20a1 1 0 0 1-1 1A17 17 0 0 1 3 4a1 1 0 0 1 1-1h3.5a1 1 0 0 1 1 1c0 1.25.2 2.45.57 3.57a1 1 0 0 1-.25 1Z" />
            </svg>
            {f.cta}
          </a>
          <p className={s.copy}>{f.copyright}</p>
          <p className={s.by}>
            <span className={s.ember} aria-hidden="true" />
            <a href="https://viduronai.in">{f.byline}</a>
          </p>
          <ul className={s.status} aria-label={f.statusLabel}>
            {f.status.map((label, i) => (
              <li key={label} className={s.chip}>
                {i === 0 ? <span className={s.dot} aria-hidden="true" /> : chipIcons[i]}
                {label}
              </li>
            ))}
          </ul>
          <LangSwitch className={s.lang} current={copy.locale} hrefs={langHrefs} label={nav.language} tone="light" />
        </div>
        {f.columns.map((col) => (
          <nav key={col.title} aria-label={col.title}>
            <h3 className={s.colTitle}>{col.title}</h3>
            <ul className={s.list}>
              {col.links.map((link) => (
                <li key={link.label}>
                  <a href={link.href}>{link.label}</a>
                </li>
              ))}
            </ul>
          </nav>
        ))}
      </div>
    </footer>
  );
}
