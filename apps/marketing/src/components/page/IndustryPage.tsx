import { industryPages, industryShared as sh } from "@/content/pages/industries";
import { rates } from "@/content/pricing";
import { cssVars } from "./Accented";
import { CallCard } from "./CallCard";
import { CtaBand } from "./CtaBand";
import { Faq } from "./Faq";
import { PageHero } from "./PageHero";
import { PageShell } from "./PageShell";
import { Cards, Checklist, Section, Stats } from "./Section";
import s from "./page.module.css";

const inr = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });

/** /clinics, /real-estate, /education: one story, told per industry. */
export function IndustryPage({ slug }: { slug: keyof typeof industryPages }) {
  const t = industryPages[slug];
  const monthly = t.cost.calls * t.cost.minutes * rates.daysPerMonth * rates.natural;
  return (
    <PageShell path={`/${slug}`}>
      <PageHero
        eyebrow={t.hero.eyebrow}
        title={t.hero.title}
        accent={t.hero.accent}
        sub={t.hero.sub}
        actions={[
          { label: sh.primary, href: "/#demo" },
          { label: t.hero.sample, href: "#sample", kind: "ghost" },
        ]}
      />

      <Section tone="chalk" tight cis="420px">
        <Stats items={t.stats} />
      </Section>

      <Section id="jobs" label={t.jobs.label} title={t.jobs.title} accent={t.jobs.accent} lead={t.jobs.lead} cis="1000px">
        <Cards items={t.jobs.items} />
      </Section>

      <Section id="sample" tone="night" cis="900px">
        <div className={s.split}>
          <div className={s.sticky} data-reveal>
            <p className={`${s.label} fade-in`}>{t.call.label}</p>
            <h2 className={s.h2}>
              {t.call.title.map((line, i) => (
                <span key={line} className="mask">
                  <span className="mask-in" style={cssVars({ "--i": i })}>
                    {i === t.call.title.length - 1 ? <em className="accent">{line}</em> : line}
                  </span>
                </span>
              ))}
            </h2>
            <p className={`${s.lead} fade-in`} style={cssVars({ "--i": 2, marginTop: "24px" })}>
              {t.call.lead}
            </p>
          </div>
          <CallCard
            business={t.call.business}
            meta={t.call.meta}
            liveLabel={sh.live}
            lines={t.call.lines}
            speakers={sh.speakers}
            outcomes={t.call.outcomes}
            outcomesLabel={sh.outcomesLabel}
          />
        </div>
      </Section>

      <Section id="guardrails" tone="ink" label={t.guardrails.label} title={t.guardrails.title} accent={t.guardrails.accent} lead={t.guardrails.lead} cis="900px">
        <Checklist items={t.guardrails.items} />
        <a href="/safety" className={s.textLink}>
          {sh.safetyLink} <span aria-hidden="true">→</span>
        </a>
      </Section>

      <Section id="cost" label={t.cost.label} title={t.cost.title} accent={t.cost.accent} lead={`${t.cost.text} ${sh.costVs}`} cis="600px">
        <div className={s.costRow} data-reveal>
          <p className={`${s.costNum} fade-in`}>
            ₹{inr.format(monthly)}
            <span>{sh.costPerMonth}</span>
          </p>
          <a href="/pricing#calculator" className="btn btn-blue fade-in" style={cssVars({ "--i": 1 })}>
            {sh.pricingLink}
          </a>
        </div>
      </Section>

      <Section id="faq" label={sh.faqLabel} title={sh.faqTitle} accent={sh.faqAccent} cis="800px">
        <Faq items={t.faq} />
      </Section>

      <CtaBand
        title={sh.cta.title}
        accent={sh.cta.accent}
        primary={{ label: sh.primary, href: "/#demo" }}
        secondary={{ label: sh.cta.secondary, href: "/pricing" }}
      />
    </PageShell>
  );
}
