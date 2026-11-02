import type { Metadata } from "next";
import { cssVars } from "@/components/page/Accented";
import b from "@/components/page/blocks.module.css";
import { CtaBand } from "@/components/page/CtaBand";
import { Faq } from "@/components/page/Faq";
import { PageHero } from "@/components/page/PageHero";
import { PageShell } from "@/components/page/PageShell";
import { Cards, Checklist, Section } from "@/components/page/Section";
import { howItWorks as t } from "@/content/pages/company";
import { pageMetadata } from "@/lib/seo";

export const metadata: Metadata = pageMetadata({ ...t.meta, path: "/how-it-works" });

export default function Page() {
  return (
    <PageShell path="/how-it-works">
      <PageHero
        eyebrow={t.hero.eyebrow}
        title={t.hero.title}
        accent={t.hero.accent}
        sub={t.hero.sub}
        actions={[
          { label: t.hero.primary, href: "/#demo" },
          { label: t.hero.secondary, href: "/pricing", kind: "ghost" },
        ]}
      />

      <Section id="steps" label={t.steps.label} title={t.steps.title} accent={t.steps.accent} lead={t.steps.lead} cis="1100px">
        <ol className={b.steps} data-reveal>
          {t.steps.items.map((step, i) => (
            <li key={step.n} className={`${b.step} fade-in`} style={cssVars({ "--i": i })}>
              <span className={b.stepNum} aria-hidden="true">
                {step.n}
              </span>
              <h3 className={b.stepTitle}>{step.title}</h3>
              <p className={b.stepText}>{step.text}</p>
              <ul className={b.ui} aria-label={`${step.title}: example`}>
                {step.ui.map((row) => (
                  <li key={row}>{row}</li>
                ))}
              </ul>
            </li>
          ))}
        </ol>
      </Section>

      <Section id="call" tone="night" label={t.call.label} title={t.call.title} accent={t.call.accent} cis="1000px">
        <ol className={b.timeline} data-reveal>
          {t.call.items.map((item, i) => (
            <li key={item.title} className={`${b.tItem} fade-in`} style={cssVars({ "--i": i })}>
              <span className={b.tDot} aria-hidden="true">
                {i + 1}
              </span>
              <div>
                <h3 className={b.tTitle}>{item.title}</h3>
                <p className={b.tText}>{item.text}</p>
              </div>
            </li>
          ))}
        </ol>
      </Section>

      <Section id="team" label={t.team.label} title={t.team.title} accent={t.team.accent} lead={t.team.lead} cis="900px">
        <Cards items={t.team.items} />
      </Section>

      <Section id="control" tone="ink" label={t.control.label} title={t.control.title} accent={t.control.accent} cis="800px">
        <Checklist items={t.control.items} />
      </Section>

      <Section id="faq" label={t.faqHead.label} title={t.faqHead.title} accent={t.faqHead.accent} cis="700px">
        <Faq items={t.faq} />
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
