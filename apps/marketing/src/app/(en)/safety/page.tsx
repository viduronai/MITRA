import type { Metadata } from "next";
import { cssVars } from "@/components/page/Accented";
import b from "@/components/page/blocks.module.css";
import { CtaBand } from "@/components/page/CtaBand";
import { PageHero } from "@/components/page/PageHero";
import { PageShell } from "@/components/page/PageShell";
import { Cards, Checklist, Section } from "@/components/page/Section";
import { safety as t } from "@/content/pages/company";
import { pageMetadata } from "@/lib/seo";

export const metadata: Metadata = pageMetadata({ ...t.meta, path: "/safety" });

export default function Page() {
  return (
    <PageShell path="/safety">
      <PageHero eyebrow={t.hero.eyebrow} title={t.hero.title} accent={t.hero.accent} sub={t.hero.sub}>
        <nav aria-label={t.toc.label}>
          <ul className={b.toc}>
            {t.toc.items.map((item) => (
              <li key={item.id}>
                <a href={`#${item.id}`}>{item.label}</a>
              </li>
            ))}
          </ul>
        </nav>
      </PageHero>

      <Section id="disclosure" tone="night" label={t.disclosure.label} title={t.disclosure.title} accent={t.disclosure.accent} lead={t.disclosure.lead} cis="800px">
        <ul className={b.quotes} data-reveal>
          {t.disclosure.examples.map((ex, i) => (
            <li key={ex.lang} className="fade-in" style={cssVars({ "--i": i })}>
              <figure className={b.quote}>
                <blockquote lang={ex.lang}>“{ex.text}”</blockquote>
                <figcaption lang={ex.lang}>{ex.label}</figcaption>
              </figure>
            </li>
          ))}
        </ul>
      </Section>

      <Section id="consent" label={t.consent.label} title={t.consent.title} accent={t.consent.accent} lead={t.consent.lead} cis="900px">
        <Checklist items={t.consent.items} />
      </Section>

      <Section id="caller-id" tone="ink" label={t.callerId.label} title={t.callerId.title} accent={t.callerId.accent} lead={t.callerId.lead} cis="500px" />

      <Section id="data" label={t.data.label} title={t.data.title} accent={t.data.accent} cis="1000px">
        <Cards items={t.data.items} numbered={false} />
      </Section>

      <Section id="sensitive" tone="night" label={t.sensitive.label} title={t.sensitive.title} accent={t.sensitive.accent} cis="800px">
        <Checklist items={t.sensitive.items} />
      </Section>

      <Section id="controls" label={t.controls.label} title={t.controls.title} accent={t.controls.accent} cis="900px">
        <Cards items={t.controls.items} />
        <p className={b.note} style={{ marginTop: 40 }}>
          {t.note}{" "}
          {t.noteLinks.map((l, i) => (
            <span key={l.href}>
              {i > 0 && " · "}
              <a href={l.href}>{l.label}</a>
            </span>
          ))}
        </p>
      </Section>

      <CtaBand
        title={t.cta.title}
        accent={t.cta.accent}
        primary={{ label: t.cta.primary, href: "/#demo" }}
        secondary={{ label: t.cta.secondary, href: "/how-it-works" }}
      />
    </PageShell>
  );
}
