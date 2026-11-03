import { AlertTriangle, Info, Settings } from "lucide-react";
import Link from "next/link";
import { getLocale, getTranslations } from "next-intl/server";
import { EmptyState } from "@/components/mitra/empty-state";
import { CreateLinkForm } from "@/components/payments/create-link-form";
import { PaymentActions } from "@/components/payments/payment-actions";
import { PaymentStatusPill } from "@/components/payments/payment-status";
import { PageHeader } from "@/components/shell/page-header";
import { Button } from "@/components/ui/button";
import { formatLocales, isLocale, TIME_ZONE } from "@/i18n/config";
import { ApiError } from "@/lib/api";
import { formatPaise } from "@/lib/billing/money";
import { paymentsApi } from "@/lib/payments/api";
import { PAYMENT_STATUSES, type PaymentStatus } from "@/lib/payments/types";
import { requireSession } from "@/lib/session";
import { cn } from "@/lib/utils";

export async function generateMetadata() {
  const t = await getTranslations("payments");
  return { title: t("title") };
}

type Search = { status?: string; contact?: string; name?: string };

/** Payments (ACT-05/11): links sent to customers, what came in this month, create / resend / mark paid. */
export default async function PaymentsPage({ searchParams }: { searchParams: Promise<Search> }) {
  const { token } = await requireSession();
  const [t, locale, search] = await Promise.all([getTranslations("payments"), getLocale(), searchParams]);
  const status = PAYMENT_STATUSES.includes(search.status as PaymentStatus) ? (search.status as PaymentStatus) : undefined;
  const contactId = search.contact && /^[0-9a-f-]{36}$/i.test(search.contact) ? search.contact : undefined;
  const tag = isLocale(locale) ? formatLocales[locale] : "en-IN";
  const date = (iso: string) => new Intl.DateTimeFormat(tag, { timeZone: TIME_ZONE, day: "numeric", month: "short" }).format(new Date(iso));
  const money = (paise: number) => formatPaise(paise, locale, { exact: true });

  let data;
  try {
    data = await Promise.all([paymentsApi.settings(token), paymentsApi.list(token, { status, contactId })]);
  } catch (error) {
    const forbidden = error instanceof ApiError && error.status === 403;
    return <EmptyState icon={AlertTriangle} description={forbidden ? t("errors.forbidden") : t("loadError")} />;
  }
  const [settings, { items, totals }] = data;
  const settingsButton = (
    <Button asChild variant="secondary" size="sm">
      <Link href="/payments/settings">
        <Settings aria-hidden />
        {t("settingsLink")}
      </Link>
    </Button>
  );

  if (settings.mode === "none") {
    return (
      <>
        <PageHeader title={t("title")} subtitle={t("subtitle")} />
        <section className="rounded-xl border bg-card p-6 shadow-xs">
          <h2 className="text-lg font-semibold">{t("setupTitle")}</h2>
          <p className="mt-1 max-w-xl text-text-muted">{t("setupBody")}</p>
          <Button asChild className="mt-4">
            <Link href="/payments/settings">{t("setupCta")}</Link>
          </Button>
        </section>
      </>
    );
  }

  const tiles = [
    { label: t("collected"), value: money(totals.collected_this_month_paise), hint: t("paidCount", { count: totals.paid_this_month }) },
    { label: t("waiting"), value: money(totals.pending_paise), hint: t("openCount", { count: totals.pending_count }) },
    { label: t("failedTitle"), value: String(totals.failed_count), hint: t("failedHint") },
  ];
  const manual = settings.mode === "upi";

  return (
    <>
      <PageHeader title={t("title")} subtitle={t("subtitle")} actions={settingsButton} />

      <div className="mb-6 grid grid-cols-1 gap-3 sm:grid-cols-3">
        {tiles.map((tile) => (
          <div key={tile.label} className="rounded-xl border bg-card p-4 shadow-xs">
            <p className="text-sm text-text-muted">{tile.label}</p>
            <p className="mt-1 text-2xl font-semibold tabular-nums">{tile.value}</p>
            <p className="mt-0.5 text-[13px] text-text-subtle">{tile.hint}</p>
          </div>
        ))}
      </div>

      {(manual || settings.simulated) && (
        <p className="mb-6 flex gap-2 rounded-lg bg-info/12 p-3 text-sm text-info-fg">
          <Info className="mt-0.5 size-4 shrink-0" aria-hidden />
          {manual ? t("manualNote") : t("simulatedNote")}
        </p>
      )}

      <section aria-labelledby="new-link" className="mb-6 rounded-xl border bg-card p-5 shadow-xs md:p-6">
        <h2 id="new-link" className="text-lg font-semibold">
          {t("newTitle")}
        </h2>
        <CreateLinkForm contact={contactId ? { id: contactId, name: search.name?.slice(0, 120) ?? null } : undefined} />
      </section>

      <section aria-labelledby="requests" className="rounded-xl border bg-card p-5 shadow-xs md:p-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 id="requests" className="text-lg font-semibold">
            {t("listTitle")}
          </h2>
          <nav aria-label={t("filter")} className="flex flex-wrap gap-1.5">
            {([undefined, "sent", "failed", "paid", "awaiting_approval"] as const).map((s) => (
              <Link
                key={s ?? "all"}
                href={s ? `/payments?status=${s}` : "/payments"}
                aria-current={status === s ? "page" : undefined}
                className={cn(
                  "focus-ring inline-flex h-8 items-center rounded-full border px-3 text-[13px] font-medium",
                  status === s ? "border-brand-500 bg-brand-50 text-brand-700" : "bg-surface hover:bg-surface-2",
                )}
              >
                {s ? t(`status.${s}`) : t("all")}
              </Link>
            ))}
          </nav>
        </div>
        {items.length === 0 ? (
          <p className="mt-4 text-text-muted">{t("empty")}</p>
        ) : (
          <ul className="mt-4 divide-y">
            {items.map((p) => (
              <li key={p.id} className="flex flex-col gap-2 py-3 sm:flex-row sm:items-center sm:justify-between">
                <div className="min-w-0">
                  <p className="flex flex-wrap items-center gap-2">
                    <span className="font-semibold tabular-nums">{money(p.amount_paise)}</span>
                    <PaymentStatusPill status={p.status} />
                    {p.discount_percent > 0 && <span className="text-[13px] text-text-muted">{t("discount", { pct: p.discount_percent })}</span>}
                    {p.customer_says_paid_at && (p.status === "sent" || p.status === "failed") && (
                      <span className="inline-flex h-6 items-center rounded-full bg-info/12 px-2.5 text-[13px] font-medium text-info-fg">
                        {t("customerSaysPaid")}
                      </span>
                    )}
                  </p>
                  <p className="mt-0.5 truncate text-sm">
                    {p.contact_id ? (
                      <Link href={`/customers/${p.contact_id}`} className="font-medium hover:underline">
                        {p.customer_name ?? `••••${p.phone_last4 ?? ""}`}
                      </Link>
                    ) : (
                      <span className="font-medium">{p.customer_name ?? t("forgotten")}</span>
                    )}{" "}
                    · {p.purpose}
                  </p>
                  <p className="mt-0.5 text-[13px] text-text-subtle">
                    {t(`source.${p.source}`)} · {date(p.created_at)}
                    {p.due_date && ` · ${t("dueOn", { date: date(`${p.due_date}T00:00:00Z`) })}`}
                    {p.paid_at && ` · ${t("paidOn", { date: date(p.paid_at) })}`}
                    {p.expires_at && (p.status === "sent" || p.status === "failed") && ` · ${t("expiresOn", { date: date(p.expires_at) })}`}
                    {p.failure_reason && p.status === "failed" && ` · ${p.failure_reason}`}
                    {p.send_error && ` · ${t(`sendError.${p.send_error === "no_phone" ? "no_phone" : "whatsapp_failed"}`)}`}
                  </p>
                  {p.status === "awaiting_approval" && p.approval_id && (
                    <Link href={`/approvals/${p.approval_id}`} className="mt-1 inline-block text-sm font-medium text-brand-600 hover:underline">
                      {t("reviewApproval")}
                    </Link>
                  )}
                </div>
                <PaymentActions id={p.id} status={p.status} link={p.short_url} manual={manual} />
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  );
}
