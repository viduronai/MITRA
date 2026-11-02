import { ChevronRight, Search, SearchX, UserRound } from "lucide-react";
import Link from "next/link";
import { getLocale, getTranslations } from "next-intl/server";
import { ForgottenToast } from "@/components/customers/forgotten-toast";
import { EmptyState } from "@/components/mitra/empty-state";
import { ResultPill } from "@/components/mitra/result-pill";
import { PageHeader } from "@/components/shell/page-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { uiResult } from "@/lib/calls";
import { getCustomers } from "@/lib/calls-data";
import { getEmployee } from "@/lib/data";
import { formatLongDate, formatTime } from "@/lib/format";

export async function generateMetadata() {
  const t = await getTranslations("customers");
  return { title: t("title") };
}

type Search = Record<string, string | string[] | undefined>;

const tagTone: Record<string, string> = {
  hot_lead: "bg-brand-50 text-brand-700",
  booked: "bg-success/12 text-success-fg",
  call_back: "bg-info/12 text-info-fg",
  vip: "bg-sky-100 text-sky-ink",
  opted_out: "bg-surface-2 text-text-muted",
};

export default async function CustomersPage({ searchParams }: { searchParams: Promise<Search> }) {
  const [t, tCustomer, locale, employee, search] = await Promise.all([
    getTranslations("customers"),
    getTranslations("customer"),
    getLocale(),
    getEmployee(),
    searchParams,
  ]);
  const name = employee?.name ?? "Mitra";
  const rawQ = Array.isArray(search.q) ? search.q[0] : search.q;
  const q = rawQ?.trim().slice(0, 100) || undefined;
  const data = await getCustomers(q);
  const items = data?.items ?? [];

  return (
    <>
      <PageHeader title={t("title")} subtitle={t("subtitle", { name })} />
      {search.forgotten === "1" && <ForgottenToast message={tCustomer("forgottenDone")} />}

      {(items.length > 0 || q) && (
        <form action="/customers" method="get" className="mb-5 flex gap-2" role="search">
          <label className="relative flex-1">
            <span className="sr-only">{t("searchLabel")}</span>
            <Search className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-text-subtle" aria-hidden />
            <Input name="q" type="search" defaultValue={q} placeholder={t("searchPlaceholder")} className="pl-9" maxLength={100} />
          </label>
          <Button type="submit" variant="secondary">
            {t("search")}
          </Button>
        </form>
      )}

      {items.length === 0 ? (
        q ? (
          <EmptyState icon={SearchX} title={t("noMatchTitle")} description={t("noMatch")} />
        ) : (
          <EmptyState
            icon={UserRound}
            title={t("emptyTitle")}
            description={t("empty", { name })}
            action={
              <Button asChild variant="secondary">
                <Link href="/calls">{t("title")}</Link>
              </Button>
            }
          />
        )
      ) : (
        <section className="rounded-xl border bg-card p-3 shadow-xs md:p-4">
          <p className="px-2 pt-1 pb-2 text-sm text-text-muted md:px-3">{t("count", { count: data?.total ?? 0 })}</p>
          <ul>
            {items.map((c) => {
              const last = c.last_contact_at ? new Date(c.last_contact_at) : null;
              const label = c.name ?? `••••${c.phone_last4}`;
              return (
                <li key={c.id}>
                  <Link
                    href={`/customers/${c.id}`}
                    className="group focus-ring flex min-h-16 items-center gap-3 rounded-lg px-2 py-3 transition-colors motion-fast hover:bg-surface-2 md:gap-4 md:px-3"
                  >
                    <span
                      aria-hidden
                      className="inline-flex size-9 shrink-0 items-center justify-center rounded-full bg-surface-2 text-[13px] font-semibold text-text-muted"
                    >
                      {c.name ? [...c.name][0]?.toUpperCase() : <UserRound className="size-4" />}
                    </span>
                    <span className="flex min-w-0 flex-1 flex-col">
                      <span className="flex flex-wrap items-center gap-1.5">
                        <span className="truncate leading-6 font-medium">{label}</span>
                        {c.tags.map((tag) => (
                          <span
                            key={tag}
                            className={`inline-flex h-5 items-center rounded-full px-2 text-[12px] font-medium ${tagTone[tag] ?? ""}`}
                          >
                            {t(`tags.${tag}`)}
                          </span>
                        ))}
                      </span>
                      <span className="truncate text-[13px] leading-5 text-text-muted">
                        {last
                          ? t("lastContact", { when: `${formatLongDate(last, locale)}, ${formatTime(last, locale)}` })
                          : t("calls", { count: 0 })}
                        {c.next_step && ` · ${t("nextStep", { step: c.next_step })}`}
                      </span>
                    </span>
                    {c.last_result && <ResultPill result={uiResult(c.last_result)} className="hidden sm:inline-flex" />}
                    <ChevronRight className="hidden size-4 shrink-0 text-text-subtle sm:block" aria-hidden />
                  </Link>
                </li>
              );
            })}
          </ul>
        </section>
      )}
    </>
  );
}
