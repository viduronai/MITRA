import { AlertTriangle, ChevronRight, FileText, PauseCircle } from "lucide-react";
import Link from "next/link";
import { redirect } from "next/navigation";
import { getLocale, getTranslations } from "next-intl/server";
import { SpendControls } from "@/components/billing/spend-controls";
import { TopupCard } from "@/components/billing/topup-card";
import { UsageBars } from "@/components/billing/usage-bars";
import { VoiceTierPicker } from "@/components/billing/voice-tier-picker";
import { PageHeader } from "@/components/shell/page-header";
import { formatLocales, isLocale, TIME_ZONE } from "@/i18n/config";
import { api, ApiError } from "@/lib/api";
import type { VoiceTier } from "@/lib/api/types";
import { billingApi } from "@/lib/billing/api";
import { formatDuration, formatPaise } from "@/lib/billing/money";
import type { Txn } from "@/lib/billing/types";
import { getBusiness } from "@/lib/data";
import { requireSession } from "@/lib/session";
import { cn } from "@/lib/utils";

export async function generateMetadata() {
  const t = await getTranslations("billing");
  return { title: t("title") };
}

const CHART_DAYS = 14;

/** Last `n` calendar days in India, oldest first, as YYYY-MM-DD. */
function lastDays(n: number): string[] {
  const iso = new Intl.DateTimeFormat("en-CA", { timeZone: TIME_ZONE, year: "numeric", month: "2-digit", day: "2-digit" });
  const today = new Date(`${iso.format(new Date())}T00:00:00Z`);
  return Array.from({ length: n }, (_, i) => {
    const d = new Date(today);
    d.setUTCDate(d.getUTCDate() - (n - 1 - i));
    return d.toISOString().slice(0, 10);
  });
}

function Card({ title, id, children, className }: { title: string; id: string; children: React.ReactNode; className?: string }) {
  return (
    <section aria-labelledby={id} className={cn("rounded-xl border bg-card p-5 shadow-xs md:p-6", className)}>
      <h2 id={id} className="text-lg leading-[26px] font-semibold md:text-xl">
        {title}
      </h2>
      {children}
    </section>
  );
}

export default async function BillingPage() {
  const { token } = await requireSession();
  const [t, locale, business] = await Promise.all([getTranslations("billing"), getLocale(), getBusiness()]);
  const tag = isLocale(locale) ? formatLocales[locale] : "en-IN";
  const money = (paise: number, exact = false) => formatPaise(paise, locale, { exact });
  const date = (iso: string, opts: Intl.DateTimeFormatOptions) =>
    new Intl.DateTimeFormat(tag, { timeZone: TIME_ZONE, ...opts }).format(new Date(iso));

  let data;
  try {
    data = await Promise.all([
      billingApi.summary(token),
      billingApi.usage(token, 30),
      billingApi.transactions(token, 15),
      billingApi.invoices(token),
      api.listEmployees(token),
      api.voices(token),
    ]);
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) redirect("/login?expired=1");
    const forbidden = error instanceof ApiError && error.status === 403;
    return (
      <>
        <PageHeader title={t("title")} />
        <p role="alert" className="rounded-xl border border-dashed px-5 py-8 text-center text-text-muted">
          {forbidden ? t("errors.forbidden") : t("loadError")}
        </p>
      </>
    );
  }
  const [summary, usage, txns, invoices, employees, voices] = data;
  const voiceName = (id: string | null) => voices.find((v) => v.id === id)?.name ?? null;

  const rates = Object.fromEntries(summary.rates.map((r) => [r.tier, r.paise_per_min])) as Record<VoiceTier, number>;
  const natural = summary.rates.find((r) => r.tier === "natural");
  const debt = summary.balance_paise < 0 ? -summary.balance_paise : 0;
  const byDay = new Map(usage.by_day.map((d) => [d.day, d]));
  const bars = lastDays(CHART_DAYS).map((day) => {
    const row = byDay.get(day);
    const label = date(`${day}T12:00:00Z`, { day: "numeric", month: "short" });
    return {
      key: day,
      label: date(`${day}T12:00:00Z`, { day: "numeric" }),
      value: row?.amount_paise ?? 0,
      tooltip: t("dayTooltip", { day: label, amount: money(row?.amount_paise ?? 0, true), calls: row?.calls ?? 0 }),
    };
  });
  const maxDay = Math.max(0, ...bars.map((b) => b.value));
  const rental = summary.number_rental;
  const delta = (txn: Txn) => txn.paid_delta_paise + txn.bonus_delta_paise;

  return (
    <>
      <PageHeader title={t("title")} subtitle={t("subtitle")} />

      {summary.outbound_paused && (
        <div role="status" className="mb-4 flex items-start gap-3 rounded-xl border border-danger/40 bg-danger/10 p-4 text-sm">
          <PauseCircle className="mt-0.5 size-5 shrink-0 text-danger-fg" aria-hidden />
          <p>
            {summary.pause_reason === "spend_cap"
              ? t("pausedCap")
              : t("pausedZero", { minutes: Math.floor(summary.grace_seconds_left_today / 60) })}
          </p>
        </div>
      )}
      {!summary.outbound_paused && summary.low_balance && (
        <div role="status" className="mb-4 flex items-start gap-3 rounded-xl border border-warning/50 bg-warning/10 p-4 text-sm">
          <AlertTriangle className="mt-0.5 size-5 shrink-0 text-warning-fg" aria-hidden />
          <p>{t("lowBalance")}</p>
        </div>
      )}

      <div className="grid grid-cols-1 items-start gap-4 lg:grid-cols-[1.1fr_1fr]">
        <div className="flex flex-col gap-4">
          <Card title={t("balanceLabel")} id="wallet-title">
            <p className="mt-3 text-[44px] leading-[48px] font-semibold tracking-tight tabular-nums md:text-[56px] md:leading-[60px]">
              {money(summary.available_paise)}
            </p>
            {natural && (
              <p className="mt-2 font-medium">
                {t("minutesHeadline", { minutes: natural.minutes_left.toLocaleString(tag), tier: t("tier.natural") })}
              </p>
            )}
            <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-sm text-text-muted tabular-nums">
              {summary.rates.map((r) => (
                <li key={r.tier}>{t("minutesShort", { tier: t(`tier.${r.tier}`), minutes: r.minutes_left.toLocaleString(tag) })}</li>
              ))}
            </ul>
            <div className="mt-4 space-y-1 border-t pt-3 text-[13px] text-text-muted">
              {summary.bonus_paise > 0 && <p>{t("bonusIncluded", { amount: money(summary.bonus_paise) })}</p>}
              {summary.credits_expire_at && (
                <p>{t("validTill", { date: date(summary.credits_expire_at, { day: "numeric", month: "short", year: "numeric" }) })}</p>
              )}
              {debt > 0 && <p className="text-danger-fg">{t("debt", { amount: money(debt, true) })}</p>}
            </div>
          </Card>

          <Card title={t("monthTitle")} id="month-title">
            <p className="mt-3 text-[32px] leading-9 font-semibold tracking-tight tabular-nums">
              {money(summary.month_usage_paise + summary.month_extras_paise, true)}
            </p>
            <dl className="mt-2 flex flex-wrap gap-x-6 gap-y-1 text-sm">
              <div className="flex gap-1.5">
                <dt className="text-text-muted">{t("monthCalls")}</dt>
                <dd className="font-medium tabular-nums">{money(summary.month_usage_paise, true)}</dd>
              </div>
              <div className="flex gap-1.5">
                <dt className="text-text-muted">{t("monthExtras")}</dt>
                <dd className="font-medium tabular-nums">{money(summary.month_extras_paise, true)}</dd>
              </div>
            </dl>
            <div className="mt-5 border-t pt-5">
              <SpendControls
                capPaise={summary.monthly_cap_paise}
                capRemainingPaise={summary.cap_remaining_paise}
                autopayEnabled={summary.autopay_enabled}
                autopayAmountPaise={summary.autopay_amount_paise}
                thresholdPaise={summary.low_balance_threshold_paise}
              />
            </div>
          </Card>
        </div>

        <TopupCard rules={summary.topup_rules} businessName={business?.name ?? "Mitra"} />
      </div>

      <Card title={t("tiersTitle")} id="tiers-title" className="mt-4">
        <p className="mt-1 text-sm text-text-muted">{t("tiersHint")}</p>
        {employees.length === 0 ? (
          <p className="mt-4 text-text-muted">{t("tiersEmpty")}</p>
        ) : (
          <ul className="mt-4 space-y-5">
            {employees.map((e) => (
              <li key={e.id}>
                <p className="mb-2 font-medium">{e.name}</p>
                <VoiceTierPicker
                  employeeId={e.id}
                  employeeName={e.name}
                  tier={e.voice_tier}
                  rates={rates}
                  voiceName={voiceName(e.voice_id)}
                />
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card title={t("usageTitle")} id="usage-title" className="mt-4">
        {usage.by_employee.length === 0 ? (
          <p className="mt-3 text-text-muted">{t("usageEmpty")}</p>
        ) : (
          <div className="mt-4 grid grid-cols-1 gap-6 lg:grid-cols-2">
            <div>
              <h3 className="mb-3 text-sm font-medium text-text-muted">{t("usageByDay")}</h3>
              <UsageBars bars={bars} maxLabel={money(maxDay, true)} />
            </div>
            <div className="min-w-0">
              <h3 className="mb-3 text-sm font-medium text-text-muted">{t("usageByEmployee")}</h3>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="text-left text-text-muted">
                    <tr className="border-b">
                      <th className="py-2 pr-2 font-medium">{t("colEmployee")}</th>
                      <th className="py-2 pr-2 text-right font-medium">{t("colCalls")}</th>
                      <th className="py-2 pr-2 text-right font-medium">{t("colTalkTime")}</th>
                      <th className="py-2 text-right font-medium">{t("colAmount")}</th>
                    </tr>
                  </thead>
                  <tbody className="tabular-nums">
                    {usage.by_employee.map((row) => (
                      <tr key={`${row.employee_id}-${row.tier}`} className="border-b last:border-0">
                        <td className="py-2 pr-2">
                          {row.employee_name}
                          <span className="ml-1.5 text-[12px] text-text-muted">{t(`tier.${row.tier}`)}</span>
                        </td>
                        <td className="py-2 pr-2 text-right">{row.calls}</td>
                        <td className="py-2 pr-2 text-right">{formatDuration(row.billable_seconds)}</td>
                        <td className="py-2 text-right font-medium">{money(row.amount_paise, true)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}
      </Card>

      <div className="mt-4 grid grid-cols-1 items-start gap-4 lg:grid-cols-2">
        <Card title={t("extrasTitle")} id="extras-title">
          <p className="mt-1 text-sm text-text-muted">{t("extrasHint")}</p>
          <ul className="mt-3 divide-y text-sm">
            <li className="py-3">
              <div className="flex justify-between gap-3">
                <span className="font-medium">{t("extraNumber")}</span>
                <span className="shrink-0 tabular-nums">{t("extraNumberPrice", { fee: money(rental.fee_paise) })}</span>
              </div>
              <p className={cn("mt-0.5 text-[13px]", rental.remaining_to_waive_paise === 0 ? "text-success-fg" : "text-text-muted")}>
                {rental.remaining_to_waive_paise === 0
                  ? t("extraNumberWaived", { threshold: money(rental.waiver_usage_paise) })
                  : t("extraNumberToGo", {
                      threshold: money(rental.waiver_usage_paise),
                      amount: money(rental.remaining_to_waive_paise, true),
                    })}
              </p>
            </li>
            {(
              [
                ["extraWhatsapp", "extraWhatsappPrice"],
                ["extraSms", "extraSmsPrice"],
                ["extraVerify", "extraVerifyPrice"],
              ] as const
            ).map(([name, price]) => (
              <li key={name} className="flex justify-between gap-3 py-3">
                <span className="font-medium">{t(name)}</span>
                <span className="shrink-0 text-text-muted">{t(price)}</span>
              </li>
            ))}
          </ul>
        </Card>

        <Card title={t("invoicesTitle")} id="invoices-title">
          {invoices.length === 0 ? (
            <p className="mt-3 text-text-muted">{t("invoicesEmpty")}</p>
          ) : (
            <ul className="mt-3 divide-y">
              {invoices.map((inv) => (
                <li key={inv.id}>
                  <Link
                    href={`/invoices/${inv.id}`}
                    aria-label={t("viewInvoice", { number: inv.number })}
                    className="group focus-ring flex min-h-14 items-center gap-3 py-2"
                  >
                    <FileText className="size-5 shrink-0 text-text-muted" aria-hidden />
                    <span className="flex min-w-0 flex-1 flex-col">
                      <span className="font-medium tabular-nums">{inv.number}</span>
                      <span className="text-[13px] text-text-muted">
                        {date(inv.issued_at, { day: "numeric", month: "short", year: "numeric" })}
                      </span>
                    </span>
                    <span className="font-medium tabular-nums">{money(inv.total_paise, true)}</span>
                    <ChevronRight className="size-4 text-text-subtle" aria-hidden />
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      <Card title={t("historyTitle")} id="history-title" className="mt-4">
        {txns.length === 0 ? (
          <p className="mt-3 text-text-muted">{t("historyEmpty")}</p>
        ) : (
          <ul className="mt-3 divide-y text-sm">
            {txns.map((txn) => (
              <li key={txn.id} className="flex items-center gap-3 py-2.5">
                <span className="w-16 shrink-0 text-[12px] font-medium tracking-wide text-text-muted uppercase">
                  {t(`kind.${txn.kind}`)}
                </span>
                <span className="flex min-w-0 flex-1 flex-col">
                  <span className="truncate">{txn.description}</span>
                  <span className="text-[12px] text-text-subtle">
                    {date(txn.created_at, { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" })}
                  </span>
                </span>
                <span className={cn("shrink-0 font-medium tabular-nums", delta(txn) > 0 && "text-success-fg")}>
                  {delta(txn) > 0 ? "+" : "−"}
                  {money(Math.abs(delta(txn)), true)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </>
  );
}
