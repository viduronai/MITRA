import { ChevronRight, Megaphone, Plus } from "lucide-react";
import Link from "next/link";
import { getLocale, getTranslations } from "next-intl/server";
import { AutoRefresh } from "@/components/campaigns/auto-refresh";
import { CampaignStatusPill } from "@/components/campaigns/campaign-status";
import { ChannelsForm } from "@/components/campaigns/channels-form";
import { EmptyState } from "@/components/mitra/empty-state";
import { PageHeader } from "@/components/shell/page-header";
import { Button } from "@/components/ui/button";
import { campaignSession, campaignsApi, load } from "@/lib/campaigns/data";
import { formatLongDate, formatNumber } from "@/lib/format";

export async function generateMetadata() {
  const t = await getTranslations("campaigns");
  return { title: t("title") };
}

export default async function CampaignsPage() {
  const [t, locale, { token, canManage }] = await Promise.all([getTranslations("campaigns"), getLocale(), campaignSession()]);
  const [list, settings] = await Promise.all([
    load(() => campaignsApi.list(token)),
    load(() => campaignsApi.channels(token)),
  ]);
  const items = list?.items ?? [];
  const live = items.some((c) => c.status === "running");
  const newButton = canManage ? (
    <Button asChild>
      <Link href="/campaigns/new">
        <Plus aria-hidden />
        {t("new")}
      </Link>
    </Button>
  ) : undefined;

  return (
    <>
      <PageHeader title={t("title")} subtitle={t("subtitle")} actions={items.length > 0 ? newButton : undefined} />
      {live && <AutoRefresh seconds={8} />}
      {list === null ? (
        <EmptyState icon={Megaphone} title={t("unavailableTitle")} description={t("unavailable")} />
      ) : items.length === 0 ? (
        <EmptyState icon={Megaphone} title={t("emptyTitle")} description={t("empty")} action={newButton} />
      ) : (
        <ul className="flex flex-col gap-3">
          {items.map((c) => {
            const p = c.progress;
            const callable = Math.max(p.total - p.skipped, 0);
            const pct = callable ? Math.round((p.done / callable) * 100) : 0;
            return (
              <li key={c.id}>
                <Link
                  href={`/campaigns/${c.id}`}
                  className="group focus-ring flex flex-col gap-3 rounded-xl border bg-card p-4 shadow-xs transition-[box-shadow,transform] motion-fast hover:-translate-y-0.5 hover:shadow-sm md:p-5"
                >
                  <span className="flex items-start justify-between gap-3">
                    <span className="min-w-0">
                      <span className="block truncate text-base leading-6 font-semibold">{c.name}</span>
                      <span className="block text-[13px] leading-5 text-text-muted">
                        {t("meta", {
                          employee: c.employee_name ?? "—",
                          date: formatLongDate(new Date(c.created_at), locale),
                        })}
                      </span>
                    </span>
                    <span className="flex items-center gap-2">
                      <CampaignStatusPill status={c.status} />
                      <ChevronRight className="size-4 text-text-subtle" aria-hidden />
                    </span>
                  </span>
                  <span className="h-2 overflow-hidden rounded-full bg-surface-2" aria-hidden>
                    <span className="block h-full rounded-full bg-brand-500" style={{ width: `${pct}%` }} />
                  </span>
                  <span className="flex flex-wrap gap-x-4 gap-y-1 text-[13px] leading-5 text-text-muted">
                    <span>{t("progress", { done: formatNumber(p.called, locale), total: formatNumber(callable, locale) })}</span>
                    {p.blocked > 0 && <span>{t("blocked", { count: p.blocked })}</span>}
                    <span>{t("interested", { count: p.buckets.interested })}</span>
                    {c.status === "running" && p.eta_minutes !== null && <span>{t("eta", { minutes: p.eta_minutes })}</span>}
                  </span>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
      {settings && (
        <div className="mt-6">
          <ChannelsForm channels={settings.channels} canManage={canManage} />
        </div>
      )}
    </>
  );
}
