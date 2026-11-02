import { Download, PhoneOff, Search, SearchX } from "lucide-react";
import Link from "next/link";
import { getTranslations } from "next-intl/server";
import { CallRow } from "@/components/mitra/call-row";
import { EmptyState } from "@/components/mitra/empty-state";
import { PageHeader } from "@/components/shell/page-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { localeLabels, isLocale } from "@/i18n/config";
import type { ApiCallResult, CallFilters, CallSummaryRow } from "@/lib/api/types";
import { allResults, isApiResult, resultChips, toCallRow, uiResult } from "@/lib/calls";
import { getCalls } from "@/lib/calls-data";
import { getEmployee } from "@/lib/data";
import { cn } from "@/lib/utils";

export async function generateMetadata() {
  const t = await getTranslations("calls");
  return { title: t("title") };
}

type Search = Record<string, string | string[] | undefined>;

function one(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

function todayInIndia(): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" }).format(new Date());
}

interface Params {
  when?: "today";
  result?: ApiCallResult;
  language?: "en" | "te" | "hi";
  q?: string;
}

/** Validated filters from the URL (system boundary). */
function parse(search: Search): Params {
  const result = one(search.result);
  const language = one(search.language);
  const q = one(search.q)?.trim().slice(0, 100);
  return {
    when: one(search.when) === "today" ? "today" : undefined,
    result: result && isApiResult(result) ? result : undefined,
    language: isLocale(language) ? language : undefined,
    q: q || undefined,
  };
}

function href(params: Params): string {
  const query = new URLSearchParams(
    Object.entries(params).filter((entry): entry is [string, string] => Boolean(entry[1])),
  ).toString();
  return query ? `/calls?${query}` : "/calls";
}

function toApi(params: Params): CallFilters {
  const today = todayInIndia();
  return {
    result: params.result ? [params.result] : undefined,
    language: params.language,
    q: params.q,
    date_from: params.when === "today" ? today : undefined,
    date_to: params.when === "today" ? today : undefined,
    limit: 100,
  };
}

function Chip({ active, href: to, children }: { active: boolean; href: string; children: React.ReactNode }) {
  return (
    <Link
      href={to}
      aria-current={active ? "true" : undefined}
      className={cn(
        "focus-ring inline-flex h-9 shrink-0 items-center rounded-full border px-3.5 text-sm font-medium transition-colors motion-fast",
        active ? "border-brand-600 bg-brand-50 text-brand-700" : "bg-card text-text-muted hover:bg-surface-2",
      )}
    >
      {children}
    </Link>
  );
}

export default async function CallsPage({ searchParams }: { searchParams: Promise<Search> }) {
  const [t, tEmpty, tResults, tCall, employee, search] = await Promise.all([
    getTranslations("calls"),
    getTranslations("empty"),
    getTranslations("results"),
    getTranslations("call"),
    getEmployee(),
    searchParams,
  ]);
  const name = employee?.name ?? "Mitra";
  const params = parse(search);
  const filtered = Boolean(params.when || params.result || params.language || params.q);
  const data = await getCalls(toApi(params));
  const items = data?.items ?? [];
  const today = todayInIndia();
  const dayOf = (call: CallSummaryRow) =>
    new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" }).format(new Date(call.started_at));
  const groups = [
    { key: "today", title: t("today"), calls: items.filter((c) => dayOf(c) === today) },
    { key: "earlier", title: t("earlier"), calls: items.filter((c) => dayOf(c) !== today) },
  ].filter((g) => g.calls.length > 0);
  const exportQuery = href(params).replace(/^\/calls/, "");

  return (
    <>
      <PageHeader
        title={t("title")}
        subtitle={t("subtitle", { name })}
        actions={
          items.length > 0 ? (
            <Button asChild variant="secondary" size="sm">
              <a href={`/calls/export${exportQuery}`} download>
                <Download aria-hidden />
                {t("export")}
              </a>
            </Button>
          ) : undefined
        }
      />

      <section aria-label={t("filtersLabel")} className="mb-5 flex flex-col gap-3">
        <div className="-mx-1 flex gap-2 overflow-x-auto px-1 pb-1">
          <Chip active={!filtered} href="/calls">
            {t("chipAll")}
          </Chip>
          <Chip active={params.when === "today"} href={href({ ...params, when: params.when ? undefined : "today" })}>
            {t("chipToday")}
          </Chip>
          {resultChips.map((chip) => {
            const value = chip.results[0];
            const active = params.result === value;
            return (
              <Chip key={chip.key} active={active} href={href({ ...params, result: active ? undefined : value })}>
                {tResults(chip.key)}
              </Chip>
            );
          })}
        </div>
        <form action="/calls" method="get" className="flex flex-col gap-2 sm:flex-row sm:items-center">
          {params.when && <input type="hidden" name="when" value={params.when} />}
          <label className="relative flex-1">
            <span className="sr-only">{t("searchLabel")}</span>
            <Search className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-text-subtle" aria-hidden />
            <Input name="q" type="search" defaultValue={params.q} placeholder={t("searchPlaceholder")} className="pl-9" maxLength={100} />
          </label>
          <div className="grid grid-cols-2 gap-2 sm:flex">
            <select
              name="result"
              defaultValue={params.result ?? ""}
              aria-label={t("allResults")}
              className="focus-ring h-12 rounded-lg border border-input bg-surface px-3 text-[15px]"
            >
              <option value="">{t("allResults")}</option>
              {allResults.map((r) => (
                <option key={r} value={r}>
                  {tResults(uiResult(r))}
                </option>
              ))}
            </select>
            <select
              name="language"
              defaultValue={params.language ?? ""}
              aria-label={t("allLanguages")}
              className="focus-ring h-12 rounded-lg border border-input bg-surface px-3 text-[15px]"
            >
              <option value="">{t("allLanguages")}</option>
              {(["te", "hi", "en"] as const).map((l) => (
                <option key={l} value={l}>
                  {localeLabels[l].name}
                </option>
              ))}
            </select>
          </div>
          <Button type="submit" variant="secondary">
            {t("apply")}
          </Button>
        </form>
      </section>

      {items.length === 0 ? (
        filtered ? (
          <EmptyState
            icon={SearchX}
            title={t("noMatchTitle")}
            description={t("noMatch")}
            action={
              <Button asChild variant="secondary">
                <Link href="/calls">{t("clear")}</Link>
              </Button>
            }
          />
        ) : (
          <EmptyState
            icon={PhoneOff}
            title={tEmpty("callsTitle")}
            description={tEmpty("calls", { name })}
            action={
              <Button asChild>
                <Link href="/onboarding">{tEmpty("callsAction")}</Link>
              </Button>
            }
          />
        )
      ) : (
        <div className="flex flex-col gap-4">
          <p className="text-sm text-text-muted">{t("count", { count: data?.total ?? items.length })}</p>
          {groups.map((group) => (
            <section
              key={group.key}
              aria-labelledby={`calls-${group.key}`}
              className="rounded-xl border bg-card p-3 shadow-xs md:p-4"
            >
              <h2 id={`calls-${group.key}`} className="px-2 pt-2 pb-1 text-sm font-semibold text-text-muted md:px-3">
                {group.title}
              </h2>
              <ul>
                {group.calls.map((call) => (
                  <li key={call.id}>
                    <CallRow call={toCallRow(call, name, tCall("web"))} href={`/calls/${call.id}`} />
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}
    </>
  );
}
