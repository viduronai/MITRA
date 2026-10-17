import { ArrowRight, CircleHelp, Frown, MessageSquareWarning, type LucideIcon } from "lucide-react";
import Link from "next/link";
import { getLocale, getTranslations } from "next-intl/server";
import { CallRow } from "@/components/mitra/call-row";
import { SetupChecklist } from "@/components/mitra/setup-checklist";
import { StatTile, type TrendDirection } from "@/components/mitra/stat-tile";
import { MockActionButton } from "@/components/mitra/mock-action-button";
import { PageHeader } from "@/components/shell/page-header";
import { Button } from "@/components/ui/button";
import { formatLongDate, formatNumber, hourInIndia } from "@/lib/format";
import {
  business,
  calls,
  minutesAgoToDate,
  needs,
  requestTime,
  setupSteps,
  stats,
  type NeedKind,
} from "@/lib/mock-data";

export async function generateMetadata() {
  const t = await getTranslations("nav");
  return { title: t("home") };
}

const needIcons: Record<NeedKind, LucideIcon> = {
  unknownQuestion: CircleHelp,
  upsetCaller: Frown,
  failedMessage: MessageSquareWarning,
};

function trendOf(change: number): TrendDirection {
  return change > 0 ? "up" : change < 0 ? "down" : "flat";
}

export default async function HomePage() {
  const [t, tNeeds, tSetup, locale] = await Promise.all([
    getTranslations("home"),
    getTranslations("needs"),
    getTranslations("setup"),
    getLocale(),
  ]);
  const now = requestTime();
  const hour = hourInIndia(now);
  const greetingKey = hour < 12 ? "greetingMorning" : hour < 17 ? "greetingAfternoon" : "greetingEvening";

  const trend = (change: number) => {
    const direction = trendOf(change);
    const value = formatNumber(Math.abs(change), locale);
    const label =
      direction === "up" ? t("trendUp", { value }) : direction === "down" ? t("trendDown", { value }) : t("trendSame");
    return { direction, label };
  };

  const tiles = [
    { label: t("callsToday"), stat: stats.callsToday, href: "/calls" },
    { label: t("booked"), stat: stats.booked, href: "/calls?result=booked" },
    { label: t("rescued"), stat: stats.rescued, href: "/calls?result=missed" },
    { label: t("needsYou"), stat: stats.needsYou, href: "#needs-you", highlight: stats.needsYou.value > 0 },
  ];

  return (
    <>
      <PageHeader title={t(greetingKey, { name: business.ownerName })} subtitle={formatLongDate(now, locale)} />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_360px] lg:gap-8">
        <section aria-label={t("statsLabel")} className="grid grid-cols-2 gap-3 md:gap-4">
          {tiles.map((tile) => (
            <StatTile
              key={tile.label}
              label={tile.label}
              value={formatNumber(tile.stat.value, locale)}
              trend={trend(tile.stat.change)}
              href={tile.href}
              highlight={tile.highlight}
            />
          ))}
        </section>

        <section
          id="needs-you"
          aria-labelledby="needs-you-title"
          className="scroll-mt-24 rounded-xl border bg-card p-5 shadow-xs md:p-6"
        >
          <h2 id="needs-you-title" className="text-lg leading-[26px] font-semibold">
            {t("needsYou")}
          </h2>
          <p className="text-sm leading-5 text-text-muted">{t("needsYouCount", { count: needs.length })}</p>
          {needs.length === 0 ? (
            <p className="mt-4 text-text-muted">{t("allClear")}</p>
          ) : (
            <ul className="mt-4 flex flex-col divide-y">
              {needs.map((need) => {
                const Icon = needIcons[need.kind];
                return (
                  <li key={need.id} className="flex flex-col gap-3 py-4 first:pt-0 last:pb-0 sm:flex-row sm:items-center">
                    <div className="flex flex-1 items-start gap-3">
                      <span className="inline-flex size-9 shrink-0 items-center justify-center rounded-full bg-accent-100 text-on-accent-100">
                        <Icon className="size-[18px]" aria-hidden />
                      </span>
                      <p className="pt-1.5 leading-6">{tNeeds(need.kind, { name: need.name })}</p>
                    </div>
                    <div className="pl-12 sm:pl-0">
                      {need.kind === "failedMessage" ? (
                        <MockActionButton toastMessage={tNeeds("sentAgain", { name: need.name })}>
                          {tNeeds(`${need.kind}Action`)}
                        </MockActionButton>
                      ) : (
                        <Button asChild variant="secondary" size="sm">
                          <Link href={need.kind === "unknownQuestion" ? "/team" : "/customers"}>
                            {tNeeds(`${need.kind}Action`)}
                          </Link>
                        </Button>
                      )}
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </section>

        <div className="lg:sticky lg:top-24 lg:col-start-2 lg:row-span-3 lg:row-start-1 lg:self-start">
          <SetupChecklist
            title={tSetup("title")}
            steps={setupSteps.map((step) => ({ id: step.key, label: tSetup(step.key), done: step.done }))}
            action={
              <Button asChild size="lg" className="w-full">
                <Link href="/team">
                  {tSetup("continue")}
                  <ArrowRight aria-hidden />
                </Link>
              </Button>
            }
          />
        </div>

        <section aria-labelledby="recent-calls-title" className="rounded-xl border bg-card p-3 shadow-xs md:p-4">
          <div className="flex items-center justify-between gap-3 px-2 pt-2 pb-1 md:px-3">
            <h2 id="recent-calls-title" className="text-lg leading-[26px] font-semibold">
              {t("recentCalls")}
            </h2>
            <Button asChild variant="link" size="sm">
              <Link href="/calls">{t("seeAllCalls")}</Link>
            </Button>
          </div>
          <ul>
            {calls.slice(0, 5).map((call) => (
              <li key={call.id}>
                <CallRow call={{ ...call, at: minutesAgoToDate(call.minutesAgo, now) }} href="/calls" />
              </li>
            ))}
          </ul>
        </section>
      </div>
    </>
  );
}
