import { ArrowRight, CircleHelp, Frown, MessageSquareWarning, type LucideIcon } from "lucide-react";
import Link from "next/link";
import { getLocale, getTranslations } from "next-intl/server";
import { CallRow } from "@/components/mitra/call-row";
import { SetupChecklist } from "@/components/mitra/setup-checklist";
import { StatTile, type TrendDirection } from "@/components/mitra/stat-tile";
import { MockActionButton } from "@/components/mitra/mock-action-button";
import { PageHeader } from "@/components/shell/page-header";
import { Button } from "@/components/ui/button";
import type { OnboardingStepKey } from "@/lib/api/types";
import { getEmployee, getMe, getProgress } from "@/lib/data";
import { formatLongDate, formatNumber, hourInIndia } from "@/lib/format";
// MOCK: call stats, "needs you" and recent calls stay invented until calls exist in the API.
import { mockCallDate, mockCallsSoFar, needs, requestTime, stats, type NeedKind } from "@/lib/mock-data";

export async function generateMetadata() {
  const t = await getTranslations("nav");
  return { title: t("home") };
}

const needIcons: Record<NeedKind, LucideIcon> = {
  unknownQuestion: CircleHelp,
  upsetCaller: Frown,
  failedMessage: MessageSquareWarning,
};

/** Home checklist (max 5 rows, docs/06 §8) folded from the six onboarding steps. */
const checklist: { key: "business" | "teach" | "voice" | "testCall" | "forward"; steps: OnboardingStepKey[] }[] = [
  { key: "business", steps: ["business", "role"] },
  { key: "teach", steps: ["teach"] },
  { key: "voice", steps: ["voice"] },
  { key: "testCall", steps: ["test_call"] },
  { key: "forward", steps: ["go_live"] },
];

function trendOf(change: number): TrendDirection {
  return change > 0 ? "up" : change < 0 ? "down" : "flat";
}

export default async function HomePage() {
  const [t, tNeeds, tSetup, tEmpty, locale, me, employee, progress] = await Promise.all([
    getTranslations("home"),
    getTranslations("needs"),
    getTranslations("setup"),
    getTranslations("empty"),
    getLocale(),
    getMe(),
    getEmployee(),
    getProgress(),
  ]);
  const now = requestTime();
  const hour = hourInIndia(now);
  const greetingKey = hour < 12 ? "greetingMorning" : hour < 17 ? "greetingAfternoon" : "greetingEvening";
  const ownerName = me.user.name?.trim();
  const greeting = ownerName ? t(greetingKey, { name: ownerName }) : t(`${greetingKey}Plain`);
  const employeeName = employee?.name ?? "Mitra";
  const doneSteps = new Set(progress?.steps.filter((step) => step.done).map((step) => step.key));
  const setupSteps = checklist.map((row) => ({
    id: row.key,
    label: tSetup(row.key, { name: employeeName }),
    done: row.steps.every((step) => doneSteps.has(step)),
  }));
  // go_live can't be done until numbers + wallet exist (later step), so it doesn't hold the card open.
  const setupComplete = setupSteps.every((step) => step.done || step.id === "forward");
  const recentCalls = mockCallsSoFar(now).slice(0, 5);

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
      <PageHeader title={greeting} subtitle={formatLongDate(now, locale)} />

      {/* Two real columns on desktop, so neither side is left with a tall empty gap. */}
      <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-[minmax(0,1fr)_400px] lg:gap-8">
        <div className="flex min-w-0 flex-col gap-6 lg:gap-8">
          <section aria-label={t("statsLabel")} className="grid grid-cols-2 gap-3 md:gap-4">
            <p className="col-span-2 -mb-1 text-[13px] leading-5 text-text-muted">{t("sampleNote")}</p>
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
              <p className="mt-4 text-text-muted">{t("allClear", { employee: employeeName })}</p>
            ) : (
              <ul className="mt-4 flex flex-col divide-y">
                {needs.map((need) => {
                  const Icon = needIcons[need.kind];
                  return (
                    <li
                      key={need.id}
                      className="flex flex-col gap-3 py-4 first:pt-0 last:pb-0 sm:flex-row sm:items-center"
                    >
                      <div className="flex flex-1 items-start gap-3">
                        <span className="inline-flex size-9 shrink-0 items-center justify-center rounded-full bg-sky-100 text-sky-ink">
                          <Icon className="size-[18px]" aria-hidden />
                        </span>
                        <p className="pt-1.5 leading-6">
                          {tNeeds(need.kind, { name: need.name, employee: employeeName })}
                        </p>
                      </div>
                      <div className="pl-12 sm:pl-0">
                        {need.kind === "failedMessage" ? (
                          <MockActionButton toastMessage={tNeeds("sentAgain", { name: need.name })}>
                            {tNeeds(`${need.kind}Action`)}
                          </MockActionButton>
                        ) : (
                          <Button asChild variant="secondary" size="sm">
                            <Link href={need.kind === "unknownQuestion" ? "/team" : "/customers"}>
                              {tNeeds(`${need.kind}Action`, { employee: employeeName })}
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
        </div>

        <div className="flex min-w-0 flex-col gap-6 lg:gap-8">
          {!setupComplete && (
            <div>
              <SetupChecklist
                title={tSetup("title")}
                steps={setupSteps}
                action={
                  <Button asChild size="lg" className="w-full">
                    <Link href="/onboarding">
                      {tSetup("continue")}
                      <ArrowRight aria-hidden />
                    </Link>
                  </Button>
                }
              />
            </div>
          )}

          <section aria-labelledby="recent-calls-title" className="rounded-xl border bg-card p-3 shadow-xs md:p-4">
            <div className="flex items-center justify-between gap-3 px-2 pt-2 pb-1 md:px-3">
              <h2 id="recent-calls-title" className="text-lg leading-[26px] font-semibold">
                {t("recentCalls")}
              </h2>
              <Button asChild variant="link" size="sm">
                <Link href="/calls">{t("seeAllCalls")}</Link>
              </Button>
            </div>
            {recentCalls.length === 0 ? (
              <p className="px-2 pt-1 pb-3 text-text-muted md:px-3">{tEmpty("calls", { name: employeeName })}</p>
            ) : (
              <ul>
                {recentCalls.map((call) => (
                  <li key={call.id}>
                    <CallRow call={{ ...call, employeeName, at: mockCallDate(call.at, now) }} href="/calls" />
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      </div>
    </>
  );
}
