import type { Metadata } from "next";
import b from "@/components/page/blocks.module.css";
import { CtaBand } from "@/components/page/CtaBand";
import { PageHero } from "@/components/page/PageHero";
import { PageShell } from "@/components/page/PageShell";
import { Cards, Section } from "@/components/page/Section";
import s from "@/components/page/page.module.css";
import { about as t } from "@/content/pages/company";
import { pageMetadata } from "@/lib/seo";

export const metadata: Metadata = pageMetadata({ ...t.meta, path: "/about" });

export default function Page() {
  return (
    <PageShell path="/about">
      <PageHero eyebrow={t.hero.eyebrow} title={t.hero.title} accent={t.hero.accent} sub={t.hero.sub} />

      <Section id="why" label={t.why.label} title={t.why.title} accent={t.why.accent} cis="800px">
        <div className={b.prose} data-reveal>
          {t.why.paragraphs.map((p) => (
            <p key={p.slice(0, 24)} className="fade-in">
              {p}
            </p>
          ))}
        </div>
      </Section>

      <Section id="principles" tone="ink" label={t.principles.label} title={t.principles.title} accent={t.principles.accent} cis="800px">
        <Cards items={t.principles.items} />
      </Section>

      <Section id="company" tone="night" label={t.company.label} title={t.company.title} accent={t.company.accent} cis="600px">
        <div data-reveal>
          <p className={`${s.lead} fade-in`}>
            <span className={b.ember} aria-hidden="true" />
            {t.company.text}
          </p>
          <ul className={b.facts}>
            {t.company.facts.map((f) => (
              <li key={f}>{f}</li>
            ))}
          </ul>
          <a href="https://viduronai.in" className={s.textLink}>
            {t.company.link} <span aria-hidden="true">↗</span>
          </a>
        </div>
      </Section>

      <CtaBand
        title={t.cta.title}
        accent={t.cta.accent}
        primary={{ label: t.cta.primary, href: "/#demo" }}
        secondary={{ label: t.cta.secondary, href: "/pricing" }}
      />
    </PageShell>
  );
}
