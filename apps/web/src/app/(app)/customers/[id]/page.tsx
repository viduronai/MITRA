import { AlertTriangle, ArrowLeft, CalendarClock, PhoneCall, Zap, type LucideIcon } from "lucide-react";
import Link from "next/link";
import { getLocale, getTranslations } from "next-intl/server";
import { ForgetCustomer, MemoryList } from "@/components/customers/memory-list";
import { EmptyState } from "@/components/mitra/empty-state";
import { ResultPill } from "@/components/mitra/result-pill";
import { localeLabels } from "@/i18n/config";
import type { TimelineEvent } from "@/lib/api/types";
import { uiResult } from "@/lib/calls";
import { getCustomer, validId } from "@/lib/calls-data";
import { getEmployee } from "@/lib/data";
import { formatLongDate, formatTime } from "@/lib/format";

export async function generateMetadata() {
  const t = await getTranslations("customers");
  return { title: t("title") };
}

const eventIcons: Record<TimelineEvent["kind"], LucideIcon> = {
  call: PhoneCall,
  action: Zap,
  commitment: CalendarClock,
};

export default async function CustomerPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const [t, tList, locale, employee, customer] = await Promise.all([
    getTranslations("customer"),
    getTranslations("customers"),
    getLocale(),
    getEmployee(),
    getCustomer(validId(id)),
  ]);
  if (!customer) return <EmptyState icon={AlertTriangle} description={t("error")} />;
  const employeeName = employee?.name ?? "Mitra";
  const name = customer.name ?? tList("unknownName");

  return (
    <>
      <Link
        href="/customers"
        className="focus-ring mb-4 inline-flex items-center gap-1.5 rounded-md text-sm font-medium text-text-muted hover:text-foreground"
      >
        <ArrowLeft className="size-4" aria-hidden />
        {t("back")}
      </Link>

      <header className="mb-6 flex flex-col gap-3 md:mb-8 md:flex-row md:items-end md:justify-between">
        <div className="min-w-0">
          <h1 className="text-[28px] leading-[34px] font-semibold tracking-tight md:text-4xl md:leading-[42px]">
            {name}
          </h1>
          <p className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-text-muted">
            <span>
              {t("phone")}: <span className="tabular-nums">••••{customer.phone_last4}</span>
            </span>
            {customer.language && (
              <span>
                · {t("language")}: {localeLabels[customer.language].name}
              </span>
            )}
            <span>· {tList("calls", { count: customer.calls })}</span>
          </p>
          {customer.tags.length > 0 && (
            <p className="mt-2 flex flex-wrap gap-1.5">
              {customer.tags.map((tag) => (
                <span key={tag} className="inline-flex h-6 items-center rounded-full bg-surface-2 px-2.5 text-[13px] font-medium">
                  {tList(`tags.${tag}`)}
                </span>
              ))}
            </p>
          )}
        </div>
        <ForgetCustomer customerId={customer.id} customerName={name} employeeName={employeeName} />
      </header>

      <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-[minmax(0,1fr)_400px] lg:gap-8">
        <section aria-labelledby="timeline-title" className="order-2 rounded-xl border bg-card p-5 shadow-xs lg:order-1">
          <h2 id="timeline-title" className="text-lg leading-[26px] font-semibold">
            {t("timeline")}
          </h2>
          {customer.timeline.length === 0 ? (
            <p className="mt-3 text-text-muted">{t("noTimeline")}</p>
          ) : (
            <ol className="mt-4 flex flex-col">
              {customer.timeline.map((event, index) => {
                const Icon = eventIcons[event.kind];
                const at = new Date(event.at);
                const body = (
                  <>
                    <span className="flex flex-wrap items-center gap-2">
                      <span className="font-medium">{event.title}</span>
                      {event.kind === "call" && event.result && <ResultPill result={uiResult(event.result)} />}
                    </span>
                    {event.detail && event.kind === "call" && (
                      <span className="mt-0.5 block text-sm leading-5 text-text-muted">{event.detail}</span>
                    )}
                    <span className="mt-0.5 block text-[13px] text-text-subtle">
                      {formatLongDate(at, locale)}, {formatTime(at, locale)}
                    </span>
                  </>
                );
                return (
                  <li key={`${event.kind}-${index}`} className="relative flex gap-3 pb-5 last:pb-0">
                    <span className="relative z-10 inline-flex size-8 shrink-0 items-center justify-center rounded-full bg-surface-2 text-text-muted">
                      <Icon className="size-4" aria-hidden />
                    </span>
                    {index < customer.timeline.length - 1 && (
                      <span aria-hidden className="absolute top-8 bottom-0 left-4 w-px bg-border" />
                    )}
                    {event.kind === "call" && event.call_id ? (
                      <Link href={`/calls/${event.call_id}`} className="focus-ring -m-1 min-w-0 flex-1 rounded-md p-1 hover:bg-surface-2">
                        {body}
                      </Link>
                    ) : (
                      <div className="min-w-0 flex-1 pt-1">{body}</div>
                    )}
                  </li>
                );
              })}
            </ol>
          )}
        </section>

        <section aria-labelledby="memory-title" className="order-1 rounded-xl border bg-card p-5 shadow-xs lg:order-2">
          <h2 id="memory-title" className="text-lg leading-[26px] font-semibold">
            {t("memory", { name: employeeName })}
          </h2>
          <p className="mt-1 mb-4 text-sm leading-5 text-text-muted">{t("memoryHelp", { name: employeeName })}</p>
          <MemoryList customerId={customer.id} memory={customer.memory} />
        </section>
      </div>
    </>
  );
}
