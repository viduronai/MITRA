import { ChevronRight, CircleCheckBig, CloudOff } from "lucide-react";
import Link from "next/link";
import { getLocale, getTranslations } from "next-intl/server";
import { redirect } from "next/navigation";
import { RulesForm } from "@/components/manager/rules-form";
import { EmptyState } from "@/components/mitra/empty-state";
import { PageHeader } from "@/components/shell/page-header";
import { ApiError } from "@/lib/api";
import { formatLongDate, formatTime } from "@/lib/format";
import { managerApi } from "@/lib/manager/api";
import type { Approval } from "@/lib/manager/types";
import { requireSession } from "@/lib/session";
import { cn } from "@/lib/utils";

export async function generateMetadata() {
  const t = await getTranslations("approvals");
  return { title: t("title") };
}

const statusTone: Record<string, string> = {
  pending: "bg-warning/15 text-warning-fg",
  approved: "bg-success/12 text-success-fg",
  declined: "bg-surface-2 text-text-muted",
  expired: "bg-surface-2 text-text-muted",
  cancelled: "bg-surface-2 text-text-muted",
};

export default async function ApprovalsPage() {
  const [t, locale, { token }] = await Promise.all([getTranslations("approvals"), getLocale(), requireSession()]);
  let data: [{ items: Approval[]; pending: number }, Approval[], Awaited<ReturnType<typeof managerApi.rules>>] | null = null;
  try {
    data = await Promise.all([
      managerApi.approvals(token, "pending"),
      managerApi.approvals(token, "decided").then((r) => r.items.slice(0, 20)),
      managerApi.rules(token),
    ]);
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) redirect("/login?expired=1");
  }
  if (!data) {
    return (
      <>
        <PageHeader title={t("title")} />
        <EmptyState icon={CloudOff} description={t("errors.unreachable")} />
      </>
    );
  }
  const [pending, decided, rules] = data;
  // Kinds/events come from other modules too: unknown ones show their raw name.
  const label = (key: string, fallback: string) => (t.has(key as never) ? t(key as never) : fallback);
  // Server-built summaries render in the viewer's language; the stored English is the fallback.
  const summaryOf = (a: Approval) =>
    a.summary_key && t.has(`summaries.${a.summary_key}` as never)
      ? t(`summaries.${a.summary_key}` as never, a.summary_params as never)
      : a.summary;
  const when = (iso: string) => `${formatLongDate(new Date(iso), locale)} · ${formatTime(new Date(iso), locale)}`;

  const row = (a: Approval) => (
    <li key={a.id}>
      <Link
        href={`/approvals/${a.id}`}
        className="group focus-ring flex min-h-[72px] items-center gap-4 px-4 py-3 transition-colors motion-fast hover:bg-surface-2 md:px-5"
      >
        <span className="flex min-w-0 flex-1 flex-col">
          <span className="leading-6 font-medium">{summaryOf(a)}</span>
          <span className="text-[13px] leading-5 text-text-muted">
            {label(`kinds.${a.kind}`, a.kind)} · {when(a.created_at)}
            {a.status === "pending" && a.expires_at && ` · ${t("expires", { time: formatTime(new Date(a.expires_at), locale) })}`}
          </span>
        </span>
        <span className={cn("rounded-full px-2.5 py-0.5 text-[12px] font-semibold", statusTone[a.status])}>
          {t(`status.${a.status}`)}
        </span>
        <ChevronRight className="size-4 shrink-0 text-text-subtle" aria-hidden />
      </Link>
    </li>
  );

  return (
    <>
      <PageHeader title={t("title")} subtitle={t("subtitle")} />
      <div className="flex flex-col gap-6">
        <section aria-labelledby="pending-title">
          <h2 id="pending-title" className="mb-3 text-lg leading-[26px] font-semibold">
            {t("pendingTitle", { count: pending.pending })}
          </h2>
          {pending.items.length === 0 ? (
            <EmptyState icon={CircleCheckBig} description={t("emptyPending")} />
          ) : (
            <ul className="divide-y overflow-hidden rounded-xl border bg-card shadow-xs">{pending.items.map(row)}</ul>
          )}
        </section>
        {decided.length > 0 && (
          <section aria-labelledby="log-title">
            <h2 id="log-title" className="mb-3 text-lg leading-[26px] font-semibold">
              {t("logTitle")}
            </h2>
            <ul className="divide-y overflow-hidden rounded-xl border bg-card shadow-xs">{decided.map(row)}</ul>
          </section>
        )}
        <RulesForm initial={rules} canEdit /* core refuses non-owners (403 → toast) */ />
      </div>
    </>
  );
}
