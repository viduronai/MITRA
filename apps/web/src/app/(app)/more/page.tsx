import {
  Building2,
  ChevronRight,
  LifeBuoy,
  Palette,
  ShieldCheck,
  UsersRound,
  Wallet,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { getLocale, getTranslations } from "next-intl/server";
import { PageHeader } from "@/components/shell/page-header";
import { formatNumber, formatRupees } from "@/lib/format";
import { business } from "@/lib/mock-data";

export async function generateMetadata() {
  const t = await getTranslations("more");
  return { title: t("title") };
}

type RowKey = "billing" | "profile" | "people" | "compliance" | "appearance" | "help";

// Sub-pages don't exist yet; every row points at /more until they do.
const rows: { key: RowKey; icon: LucideIcon }[] = [
  { key: "billing", icon: Wallet },
  { key: "profile", icon: Building2 },
  { key: "people", icon: UsersRound },
  { key: "compliance", icon: ShieldCheck },
  { key: "appearance", icon: Palette },
  { key: "help", icon: LifeBuoy },
];

export default async function MorePage() {
  const [t, locale] = await Promise.all([getTranslations("more"), getLocale()]);

  const hint = (key: RowKey) =>
    key === "billing"
      ? t("billingHint", {
          amount: formatRupees(business.walletRupees, locale),
          minutes: formatNumber(business.minutesLeft, locale),
        })
      : t(`${key}Hint`);

  return (
    <>
      <PageHeader title={t("title")} />
      <nav aria-label={t("title")} className="overflow-hidden rounded-xl border bg-card shadow-xs">
        <ul className="divide-y">
          {rows.map(({ key, icon: Icon }) => (
            <li key={key}>
              <Link
                href="/more"
                className="group focus-ring flex min-h-[72px] items-center gap-4 px-4 py-3 transition-colors motion-fast hover:bg-surface-2 focus-visible:-outline-offset-2 md:px-5"
              >
                <span className="inline-flex size-10 shrink-0 items-center justify-center rounded-lg bg-surface-2 text-text-muted">
                  <Icon className="size-5" strokeWidth={1.75} aria-hidden />
                </span>
                <span className="flex min-w-0 flex-1 flex-col">
                  <span className="leading-6 font-medium">{t(key)}</span>
                  <span className="text-[13px] leading-5 text-text-muted">{hint(key)}</span>
                </span>
                <ChevronRight
                  className="size-4 shrink-0 text-text-subtle transition-transform motion-fast group-hover:translate-x-0.5"
                  aria-hidden
                />
              </Link>
            </li>
          ))}
        </ul>
      </nav>
    </>
  );
}
