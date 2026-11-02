import { legalShared as sh, type LegalPageCopy } from "@/content/pages/legal";
import { PageHero } from "./PageHero";
import { PageShell } from "./PageShell";
import l from "./legal.module.css";

/** Privacy / Terms: a clearly marked draft, with contents and numbered sections. */
export function LegalPage({ t, path }: { t: LegalPageCopy; path: string }) {
  return (
    <PageShell path={path}>
      <PageHero eyebrow={t.eyebrow} title={t.title} accent={t.accent} sub={t.intro}>
        <p className={l.draft} role="note">
          <span className={l.draftTag}>{sh.draftLabel}</span>
          {sh.draft}
        </p>
      </PageHero>
      <section className={`${l.body} on-chalk`} aria-label={t.eyebrow}>
        <div className={l.grid}>
          <nav className={l.toc} aria-label={sh.tocLabel}>
            <p className={l.tocLabel}>{sh.tocLabel}</p>
            <ol>
              {t.sections.map((sec) => (
                <li key={sec.id}>
                  <a href={`#${sec.id}`}>{sec.title}</a>
                </li>
              ))}
            </ol>
            <p className={l.updated}>{t.updated}</p>
          </nav>
          <div className={l.sections}>
            {t.sections.map((sec, i) => (
              <section key={sec.id} id={sec.id} className={l.section} aria-labelledby={`${sec.id}-h`}>
                <h2 id={`${sec.id}-h`}>
                  <span aria-hidden="true">{String(i + 1).padStart(2, "0")}</span>
                  {sec.title}
                </h2>
                {sec.body.map((p) => (
                  <p key={p.slice(0, 32)}>{p}</p>
                ))}
              </section>
            ))}
            <p className={l.contact}>{sh.contact}</p>
          </div>
        </div>
      </section>
    </PageShell>
  );
}
