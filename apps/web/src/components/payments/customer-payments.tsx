import Link from "next/link";
import { getLocale, getTranslations } from "next-intl/server";
import { PaymentStatusPill } from "@/components/payments/payment-status";
import { Button } from "@/components/ui/button";
import { formatPaise } from "@/lib/billing/money";
import { paymentsApi } from "@/lib/payments/api";
import { requireSession } from "@/lib/session";

/** Payment links for one customer, on their page. Hidden for staff (they cannot see money). */
export async function CustomerPayments({ customerId, name }: { customerId: string; name: string | null }) {
  const { token } = await requireSession();
  const [t, locale] = await Promise.all([getTranslations("payments"), getLocale()]);
  const [settings, list] = await Promise.all([
    paymentsApi.settings(token).catch(() => null),
    paymentsApi.list(token, { contactId: customerId }).catch(() => null),
  ]);
  if (!settings || !list) return null;
  const query = new URLSearchParams({ contact: customerId, ...(name ? { name } : {}) });

  return (
    <section aria-labelledby="payments-title" className="order-3 rounded-xl border bg-card p-5 shadow-xs lg:col-start-2">
      <div className="flex items-center justify-between gap-3">
        <h2 id="payments-title" className="text-lg leading-[26px] font-semibold">
          {t("customerTitle")}
        </h2>
        {settings.mode !== "none" && (
          <Button asChild size="sm" variant="secondary">
            <Link href={`/payments?${query.toString()}`}>{t("sendLink")}</Link>
          </Button>
        )}
      </div>
      {list.items.length === 0 ? (
        <p className="mt-3 text-sm text-text-muted">{t("customerEmpty")}</p>
      ) : (
        <ul className="mt-3 divide-y">
          {list.items.slice(0, 10).map((p) => (
            <li key={p.id} className="flex items-center justify-between gap-3 py-2.5">
              <span className="min-w-0">
                <span className="block font-medium tabular-nums">{formatPaise(p.amount_paise, locale, { exact: true })}</span>
                <span className="block truncate text-sm text-text-muted">{p.purpose}</span>
              </span>
              <PaymentStatusPill status={p.status} />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
