import type { Metadata } from "next";
import { BrandPreview } from "@/components/agencies/BrandPreview";
import { MarginCalculator } from "@/components/agencies/MarginCalculator";
import { PartnerForm } from "@/components/agencies/PartnerForm";
import a from "@/components/agencies/agencies.module.css";
import { cssVars } from "@/components/page/Accented";
import { CtaBand } from "@/components/page/CtaBand";
import { Faq } from "@/components/page/Faq";
import { PageHero } from "@/components/page/PageHero";
import { PageShell } from "@/components/page/PageShell";
import { Cards, Section } from "@/components/page/Section";
import { agencies as t, wholesale } from "@/content/pages/agencies";
import { rates, type TierId } from "@/content/pricing";
import { pageMetadata } from "@/lib/seo";

export const metadata: Metadata = pageMetadata({ ...t.meta, path: "/agencies" });

const TIERS: [TierId, string][] = [
  ["smart", "Smart"],
  ["natural", "Natural"],
  ["signature", "Signature"],
];

export default function Page() {
  return (
    <PageShell path="/agencies">
      <PageHero
        eyebrow={t.hero.eyebrow}
        title={t.hero.title}
        accent={t.hero.accent}
        sub={t.hero.sub}
        actions={[
          { label: t.hero.primary, href: "#apply" },
          { label: t.hero.secondary, href: "#margin", kind: "ghost" },
        ]}
      />

      <Section id="rates" label={t.rates.label} title={t.rates.title} accent={t.rates.accent} lead={t.rates.lead} cis="700px">
        <ul className={a.rates} data-reveal>
          {TIERS.map(([id, name], i) => (
            <li key={id} className={`${a.rate} fade-in`} style={cssVars({ "--i": i })}>
              <span className={a.rateName}>{name}</span>
              <span className={a.rateNum}>
                ₹{wholesale[id]}
                <small>{t.rates.perMinute}</small>
              </span>
              <span className={a.rateHint}>{t.rates.retailHint.replace("{retail}", String(rates[id]))}</span>
            </li>
          ))}
        </ul>
      </Section>

      <Section id="margin" tone="ink" label={t.calc.label} title={t.calc.title} accent={t.calc.accent} cis="1000px">
        <MarginCalculator t={t.calc} />
      </Section>

      <Section id="white-label" label={t.brand.label} title={t.brand.title} accent={t.brand.accent} lead={t.brand.lead} cis="900px">
        <BrandPreview t={t.brand} />
      </Section>

      <Section id="how" tone="night" label={t.how.label} title={t.how.title} accent={t.how.accent} cis="800px">
        <Cards items={t.how.items} />
      </Section>

      <Section id="apply" label={t.form.label} title={t.form.title} accent={t.form.accent} lead={t.form.lead} cis="1100px">
        <PartnerForm t={t.form} />
      </Section>

      <Section id="faq" tone="chalk" label={t.faq.label} title={t.faq.title} accent={t.faq.accent} cis="700px">
        <Faq items={t.faq.items} />
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
