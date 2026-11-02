import { content, localePath, type Locale } from "@/content";
import { pricingContent, rates } from "@/content/pricing";
import { cssVars } from "../page/Accented";
import { CtaBand } from "../page/CtaBand";
import { Faq } from "../page/Faq";
import { PageHero } from "../page/PageHero";
import { PageShell } from "../page/PageShell";
import { Section } from "../page/Section";
import { RupeeDots } from "../RupeeDots";
import { CostCalculator } from "./CostCalculator";
import { SampleChip } from "./SampleChip";
import s from "./pricing-page.module.css";

/** /pricing in any locale (07-SCREENS §2.4, facts from 09 §3). */
export function PricingPage({ locale }: { locale: Locale }) {
  const t = pricingContent[locale];
  const home = content[locale].homeHref;
  const path = localePath(locale, "/pricing");
  return (
    <PageShell path={path} locale={locale} localised="/pricing">
      <PageHero
        eyebrow={t.hero.eyebrow}
        title={t.hero.title}
        accent={t.hero.accent}
        sub={t.hero.sub}
        actions={[
          { label: t.hero.primary, href: "#calculator" },
          { label: t.hero.secondary, href: `${home}#demo`, kind: "ghost" },
        ]}
      />

      <Section id="tiers" label={t.tiers.label} title={t.tiers.title} accent={t.tiers.accent} lead={t.tiers.lead} cis="1200px">
        <ul className={s.tiers} data-reveal>
          {t.tiers.items.map((tier, i) => {
            const featured = tier.id === "natural";
            return (
              <li
                key={tier.id}
                className={`${s.tier} fade-in`}
                data-featured={featured ? "" : undefined}
                style={cssVars({ "--i": i })}
              >
                {featured && <span className={s.badge}>{t.tiers.featured}</span>}
                <h3 className={s.tierName}>{tier.name}</h3>
                <p className={s.price}>
                  <span className="sr-only">₹</span>
                  <RupeeDots className={s.priceRupee} />
                  {rates[tier.id]}
                  <span className={s.per}>{t.tiers.perMinute}</span>
                </p>
                <p className={s.tierLine}>{tier.line}</p>
                <ul className={s.tierList}>
                  {tier.changes.map((c) => (
                    <li key={c}>{c}</li>
                  ))}
                </ul>
                <p className={s.best}>
                  <b>{t.tiers.bestFor}</b>
                  {tier.bestFor}
                </p>
                <SampleChip label={t.tiers.sample} tier={tier.name} soon={t.tiers.sampleSoon} />
              </li>
            );
          })}
        </ul>
        <div className={s.included} data-reveal>
          <p className={`${s.includedLabel} fade-in`}>{t.tiers.includedLabel}</p>
          <ul className={`${s.includedList} fade-in`} style={cssVars({ "--i": 1 })}>
            {t.tiers.included.map((f) => (
              <li key={f}>{f}</li>
            ))}
          </ul>
        </div>
        <p className={s.free}>{t.tiers.free}</p>
      </Section>

      <Section id="calculator" tone="ink" label={t.calc.label} title={t.calc.title} accent={t.calc.accent} lead={t.calc.lead} cis="1000px">
        <CostCalculator t={t.calc} tiers={t.tiers.items} />
      </Section>

      <Section id="wallet" label={t.bonus.label} title={t.bonus.title} accent={t.bonus.accent} lead={t.bonus.lead} cis="760px">
        <table className="sr-only">
          <thead>
            <tr>
              <th scope="col">{t.bonus.head[0]}</th>
              <th scope="col">{t.bonus.head[1]}</th>
            </tr>
          </thead>
          <tbody>
            {t.bonus.rows.map(([at, pct]) => (
              <tr key={at}>
                <td>{at}</td>
                <td>{pct}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <ul className={s.bonus} aria-hidden="true" data-reveal>
          {t.bonus.rows.map(([at, pct], i) => (
            <li key={at} className={`${s.bonusRow} fade-in`} style={cssVars({ "--i": i })}>
              <span className={s.bonusPct}>{pct}</span>
              <span className={s.bonusAt}>{at}</span>
            </li>
          ))}
        </ul>
        <ul className={s.facts}>
          {t.bonus.facts.map((f) => (
            <li key={f}>{f}</li>
          ))}
        </ul>
      </Section>

      <Section id="extras" tone="night" label={t.extras.label} title={t.extras.title} accent={t.extras.accent} lead={t.extras.lead} cis="900px">
        <ul className={s.extras} data-reveal>
          {t.extras.items.map((x, i) => (
            <li key={x.name} className={`${s.extra} fade-in`} style={cssVars({ "--i": i })}>
              <span className={s.extraName}>{x.name}</span>
              <span className={s.extraPrice}>{x.price}</span>
              <span className={s.extraNote}>{x.note}</span>
            </li>
          ))}
        </ul>
        <div className={s.volume}>
          <p>
            {t.extras.volume}
            <small>{t.extras.concurrency}</small>
          </p>
          <a href="/agencies" className="btn btn-ghost">
            {t.extras.volumeLink}
          </a>
        </div>
      </Section>

      <Section id="faq" label={t.faq.label} title={t.faq.title} accent={t.faq.accent} cis="900px">
        <Faq items={t.faq.items} />
      </Section>

      <CtaBand
        title={t.cta.title}
        accent={t.cta.accent}
        text={t.cta.text}
        primary={{ label: t.cta.primary, href: `${home}#demo` }}
        secondary={{ label: t.cta.secondary, href: "/how-it-works" }}
      />
    </PageShell>
  );
}
