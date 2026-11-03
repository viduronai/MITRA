import {
  ArrowLeft,
  Clock3,
  PauseCircle,
  ShieldAlert,
  ShieldCheck,
  Users,
} from "lucide-react";
import Link from "next/link";
import { notFound } from "next/navigation";
import { getLocale, getTranslations } from "next-intl/server";
import { AutoRefresh } from "@/components/campaigns/auto-refresh";
import { BucketBars } from "@/components/campaigns/bucket-bars";
import { CampaignControls } from "@/components/campaigns/campaign-controls";
import { CampaignStatusPill } from "@/components/campaigns/campaign-status";
import { EmptyState } from "@/components/mitra/empty-state";
import { StatTile } from "@/components/mitra/stat-tile";
import { PageHeader } from "@/components/shell/page-header";
import { Button } from "@/components/ui/button";
import { campaignSession, campaignsApi, load } from "@/lib/campaigns/data";
import { BUCKETS, type Bucket } from "@/lib/campaigns/types";
import { formatLongDate, formatNumber, formatTime } from "@/lib/format";

type Search = Record<string, string | string[] | undefined>;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const PAGE = 50;
// Where the owner fixes what paused a campaign.
const PAUSE_LINKS: Record<
  string,
  { href: string; label: "connect" | "billing" }
> = {
  number: { href: "/more/connect", label: "connect" },
  carrier_rejected: { href: "/more/connect", label: "connect" },
  spam_flagged: { href: "/more/connect", label: "connect" },
  wallet: { href: "/more/billing", label: "billing" },
};

export async function generateMetadata({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const t = await getTranslations("campaigns");
  const { id } = await params;
  if (!UUID.test(id)) return { title: t("title") };
  const { token } = await campaignSession();
  const campaign = await campaignsApi.get(token, id).catch(() => null);
  return { title: campaign?.name ?? t("title") };
}

function first(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

export default async function CampaignPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<Search>;
}) {
  const [{ id }, search, t, locale, { token, canManage }] = await Promise.all([
    params,
    searchParams,
    getTranslations("campaigns"),
    getLocale(),
    campaignSession(),
  ]);
  if (!UUID.test(id)) notFound();
  const rawBucket = first(search.bucket);
  const bucket = BUCKETS.includes(rawBucket as Bucket)
    ? (rawBucket as Bucket)
    : undefined;
  const page = Math.max(
    0,
    Math.min(1000, Number.parseInt(first(search.page) ?? "0", 10) || 0),
  );
  const language = locale === "hi" || locale === "te" ? locale : "en";
  const [campaign, contacts] = await Promise.all([
    load(() => campaignsApi.get(token, id)),
    load(() => campaignsApi.contacts(token, id, bucket, page * PAGE)),
  ]);
  const consentText = campaign
    ? await load(() =>
        campaignsApi.consentText(
          token,
          campaign.purpose === "promotional" ? "promotional" : "service",
          language,
        ),
      )
    : null;
  if (!campaign) {
    return (
      <EmptyState
        icon={Users}
        title={t("unavailableTitle")}
        description={t("unavailable")}
      />
    );
  }
  const p = campaign.progress;
  // Codes come from the API; unknown ones show as-is rather than a missing-message error.
  const known = (key: string, fallback: string) =>
    t.has(key as never) ? t(key as never) : fallback;
  const live =
    campaign.status === "running" || campaign.status === "pending_approval";
  const hrefFor = (b: Bucket) =>
    b === bucket ? `/campaigns/${id}` : `/campaigns/${id}?bucket=${b}`;
  const total = contacts?.total ?? 0;
  const pageHref = (n: number) =>
    `/campaigns/${id}?${new URLSearchParams({ ...(bucket ? { bucket } : {}), page: String(n) })}`;

  return (
    <>
      {live && <AutoRefresh />}
      <Button asChild variant="ghost" size="sm" className="mb-2 -ml-2">
        <Link href="/campaigns">
          <ArrowLeft aria-hidden />
          {t("wizard.backToList")}
        </Link>
      </Button>
      <PageHeader
        title={campaign.name}
        subtitle={t("meta", {
          employee: campaign.employee_name ?? "—",
          date: formatLongDate(new Date(campaign.created_at), locale),
        })}
        actions={<CampaignStatusPill status={campaign.status} />}
      />

      <CampaignControls
        campaign={campaign}
        canManage={canManage}
        consentText={consentText?.text ?? ""}
        language={language}
      />

      {campaign.status === "paused" && campaign.pause_reason && (
        <p
          role="status"
          className="mt-4 flex items-start gap-2 rounded-lg bg-warning/14 px-4 py-3 text-sm leading-5 text-warning-fg"
        >
          <PauseCircle className="mt-0.5 size-4 shrink-0" aria-hidden />
          <span className="flex-1">
            {known(
              `pauseReasons.${campaign.pause_reason}`,
              campaign.pause_reason,
            )}
          </span>
          {PAUSE_LINKS[campaign.pause_reason] && (
            <Link
              href={PAUSE_LINKS[campaign.pause_reason].href}
              className="shrink-0 font-medium underline underline-offset-4"
            >
              {t(
                `detail.pauseLinks.${PAUSE_LINKS[campaign.pause_reason].label}`,
              )}
            </Link>
          )}
        </p>
      )}
      {campaign.status === "pending_approval" && (
        <p
          role="status"
          className="mt-4 flex items-start gap-2 rounded-lg bg-info/12 px-4 py-3 text-sm leading-5 text-info-fg"
        >
          <Clock3 className="mt-0.5 size-4 shrink-0" aria-hidden />
          {t("detail.pendingApproval")}
          {/* The approvals screen belongs to the manager module (/approvals). */}
          <Link
            href="/approvals"
            className="ml-auto shrink-0 font-medium underline underline-offset-4"
          >
            {t("detail.openApprovals")}
          </Link>
        </p>
      )}

      <div className="mt-6 grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatTile
          label={t("detail.total")}
          value={formatNumber(p.total - p.skipped, locale)}
        />
        {/* Called = really dialled; people stopped by compliance count as blocked, not called. */}
        <StatTile
          label={t("detail.doneCount")}
          value={formatNumber(p.called, locale)}
        />
        <StatTile
          label={t("detail.blocked")}
          value={formatNumber(p.blocked, locale)}
          href={hrefFor("blocked")}
        />
        <StatTile
          label={t("detail.remaining")}
          value={formatNumber(p.remaining, locale)}
        />
      </div>
      {p.remaining > 0 && (
        <p className="mt-3 flex items-center gap-1.5 text-sm leading-5 text-text-muted">
          <Clock3 className="size-4 shrink-0" aria-hidden />
          {campaign.status === "paused"
            ? t("detail.etaPaused")
            : p.starts_at
              ? t("detail.startsAt", {
                  day: formatLongDate(new Date(p.starts_at), locale),
                  time: formatTime(new Date(p.starts_at), locale),
                })
              : p.eta_minutes !== null
                ? t("detail.etaLine", {
                    minutes: p.eta_minutes,
                    channels: p.channels,
                    dialing: p.dialing,
                  })
                : null}
        </p>
      )}
      {campaign.consent && (
        <p className="mt-2 flex items-start gap-1.5 text-[13px] leading-5 text-text-muted">
          <ShieldCheck className="mt-0.5 size-3.5 shrink-0" aria-hidden />
          {campaign.consent.by_name
            ? t("detail.consentBy", {
                name: campaign.consent.by_name,
                date: formatLongDate(new Date(campaign.consent.at), locale),
              })
            : t("detail.consentByYou", {
                date: formatLongDate(new Date(campaign.consent.at), locale),
              })}
        </p>
      )}

      <section className="mt-6 rounded-xl border bg-card p-4 shadow-xs md:p-5">
        <h2 className="mb-4 text-lg leading-[26px] font-semibold">
          {t("detail.results")}
        </h2>
        <BucketBars progress={p} hrefFor={hrefFor} active={bucket ?? null} />
        {p.skipped > 0 && (
          <p className="mt-3 text-[13px] leading-5 text-text-muted">
            {t("detail.skipped", { count: p.skipped })}
          </p>
        )}
        {p.blocked_summary.length > 0 && (
          <ul className="mt-3 flex flex-col gap-1 text-[13px] leading-5 text-text-muted">
            {p.blocked_summary.map((line) => (
              <li key={line} className="flex items-start gap-1.5">
                <ShieldAlert className="mt-0.5 size-3.5 shrink-0" aria-hidden />
                {line}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="mt-6 rounded-xl border bg-card p-3 shadow-xs md:p-4">
        <h2 className="px-2 pt-1 pb-2 text-lg leading-[26px] font-semibold md:px-3">
          {bucket ? t(`buckets.${bucket}`) : t("detail.people")}
          <span className="ml-2 text-sm font-normal text-text-muted">
            {formatNumber(total, locale)}
          </span>
        </h2>
        {!contacts || contacts.items.length === 0 ? (
          <p className="px-2 py-6 text-center text-sm text-text-muted md:px-3">
            {t("detail.noPeople")}
          </p>
        ) : (
          <ul className="divide-y">
            {contacts.items.map((c) => (
              <li
                key={c.id}
                className="flex flex-col gap-1 px-2 py-3 sm:flex-row sm:items-center sm:justify-between md:px-3"
              >
                <span className="min-w-0">
                  <span className="block truncate font-medium">
                    {c.name ?? t("detail.noName")}
                  </span>
                  <span className="block text-[13px] leading-5 text-text-muted">
                    ••••{c.phone_last4}
                    {c.attempts > 0 &&
                      ` · ${t("detail.attempts", { count: c.attempts })}`}
                    {c.last_called_at &&
                      ` · ${formatLongDate(new Date(c.last_called_at), locale)} ${formatTime(new Date(c.last_called_at), locale)}`}
                  </span>
                  {c.summary && (
                    <span className="mt-1 block text-[13px] leading-5">
                      {c.summary}
                    </span>
                  )}
                </span>
                <span className="text-[13px] leading-5 font-medium sm:text-right">
                  {c.bucket
                    ? t(`buckets.${c.bucket}`)
                    : t(`contactStatus.${c.status}`)}
                  {c.reasons.length > 0 && (
                    <span className="block font-normal text-text-muted">
                      {c.reasons
                        .map((r) => known(`reasons.${r}`, r))
                        .join(", ")}
                    </span>
                  )}
                </span>
              </li>
            ))}
          </ul>
        )}
        {total > PAGE && (
          <nav
            className="flex justify-between px-2 pt-3 md:px-3"
            aria-label={t("detail.pages")}
          >
            {page > 0 ? (
              <Button asChild variant="ghost" size="sm">
                <Link href={pageHref(page - 1)}>{t("detail.prev")}</Link>
              </Button>
            ) : (
              <span />
            )}
            {(page + 1) * PAGE < total && (
              <Button asChild variant="ghost" size="sm">
                <Link href={pageHref(page + 1)}>{t("detail.next")}</Link>
              </Button>
            )}
          </nav>
        )}
      </section>
    </>
  );
}
