import {
  BellRing,
  Building2,
  ChevronRight,
  CircleCheckBig,
  IndianRupee,
  LifeBuoy,
  Megaphone,
  MessageCircle,
  Palette,
  ShieldCheck,
  Sparkles,
  UsersRound,
  Wallet,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { getLocale, getTranslations } from "next-intl/server";
import { PageHeader } from "@/components/shell/page-header";
import { billingApi } from "@/lib/billing/api";
import { formatPaise } from "@/lib/billing/money";
import { formatNumber } from "@/lib/format";
import { requireSession } from "@/lib/session";

export async function generateMetadata() {
  const t = await getTranslations("more");
  return { title: t("title") };
}

type RowKey = "billing" | "payments" | "campaigns" | "ask" | "approvals" | "manager" | "whatsapp" | "profile" | "people" | "compliance" | "appearance" | "help";

// Only billing has a sub-page so far; the other rows point at /more until theirs exist.
const rows: { key: RowKey; icon: LucideIcon; href: string }[] = [
  { key: "billing", icon: Wallet, href: "/more/billing" },
  { key: "payments", icon: IndianRupee, href: "/payments" },
  { key: "campaigns", icon: Megaphone, href: "/campaigns" },
  { key: "ask", icon: Sparkles, href: "/ask" },
  { key: "approvals", icon: CircleCheckBig, href: "/approvals" },
  { key: "manager", icon: BellRing, href: "/more/manager" },
  { key: "whatsapp", icon: MessageCircle, href: "/more/whatsapp" },
  { key: "profile", href: "/more", icon: Building2 },
  { key: "people", href: "/more", icon: UsersRound },
  { key: "compliance", href: "/more", icon: ShieldCheck },
  { key: "appearance", href: "/more", icon: Palette },
  { key: "help", href: "/more", icon: LifeBuoy },
];

export default async function MorePage() {
  const [t, locale, { token }] = await Promise.all([getTranslations("more"), getLocale(), requireSession()]);
  // The wallet hint is a nice-to-have: fall back to the plain label if billing is unavailable.
  const wallet = await billingApi.summary(token).catch(() => null);
  const natural = wallet?.rates.find((r) => r.tier === "natural");

  const hint = (key: RowKey) =>
    key === "billing" && wallet && natural
      ? t("billingHint", {
          amount: formatPaise(wallet.available_paise, locale),
          minutes: formatNumber(natural.minutes_left, locale),
        })
      : key === "billing"
        ? ""
        : t(`${key}Hint`);

  return (
    <>
      <PageHeader title={t("title")} />
      <nav aria-label={t("title")} className="overflow-hidden rounded-xl border bg-card shadow-xs">
        <ul className="divide-y">
          {rows.map(({ key, icon: Icon, href }) => (
            <li key={key}>
              <Link
                href={href}
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
