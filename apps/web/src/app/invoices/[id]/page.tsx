import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { notFound, redirect } from "next/navigation";
import { getLocale, getTranslations } from "next-intl/server";
import { PrintButton } from "@/components/billing/print-button";
import { formatLocales, isLocale, TIME_ZONE } from "@/i18n/config";
import { ApiError } from "@/lib/api";
import { billingApi } from "@/lib/billing/api";
import { formatPaise } from "@/lib/billing/money";
import type { Invoice, InvoiceParty } from "@/lib/billing/types";
import { requireSession } from "@/lib/session";

/** Printable GST tax invoice. Outside the app shell so "Print / Save as PDF" is just the invoice. */

export async function generateMetadata() {
  const t = await getTranslations("billing.invoice");
  return { title: t("title") };
}

function Party({ heading, party, gstinLabel, unregistered }: { heading: string; party: InvoiceParty; gstinLabel: string; unregistered: string }) {
  return (
    <div>
      <h2 className="text-[12px] font-medium tracking-wide text-text-muted uppercase">{heading}</h2>
      <p className="mt-1 font-semibold">{party.name}</p>
      {party.address && <p className="text-sm">{party.address}</p>}
      <p className="text-sm">
        {gstinLabel}: {party.gstin ?? unregistered}
      </p>
    </div>
  );
}

export default async function InvoicePage({ params }: PageProps<"/invoices/[id]">) {
  const { id } = await params;
  const { token } = await requireSession();
  const [t, locale] = await Promise.all([getTranslations("billing.invoice"), getLocale()]);
  if (!/^[0-9a-f-]{36}$/i.test(id)) notFound();

  let invoice: Invoice;
  try {
    invoice = await billingApi.invoice(token, id);
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) redirect("/login?expired=1");
    if (error instanceof ApiError && (error.status === 404 || error.status === 403)) notFound();
    throw error;
  }
  const money = (paise: number) => formatPaise(paise, locale, { exact: true });
  const issued = new Intl.DateTimeFormat(isLocale(locale) ? formatLocales[locale] : "en-IN", {
    timeZone: TIME_ZONE,
    day: "numeric",
    month: "long",
    year: "numeric",
  }).format(new Date(invoice.issued_at));
  const half = invoice.gst_rate_pct / 2;
  const taxes = invoice.intra_state
    ? [
        [t("cgst", { pct: half }), invoice.cgst_paise],
        [t("sgst", { pct: half }), invoice.sgst_paise],
      ]
    : [[t("igst", { pct: invoice.gst_rate_pct }), invoice.igst_paise]];

  return (
    <main className="mx-auto w-full max-w-3xl px-4 py-6 md:py-10 print:max-w-none print:p-0">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3 print:hidden">
        <Link href="/more/billing" className="focus-ring inline-flex min-h-11 items-center gap-2 text-sm font-medium text-brand-600">
          <ArrowLeft className="size-4" aria-hidden /> {t("back")}
        </Link>
        <PrintButton label={t("print")} />
      </div>

      <article className="rounded-xl border bg-card p-5 shadow-xs md:p-8 print:border-0 print:shadow-none">
        <header className="flex flex-wrap items-start justify-between gap-4 border-b pb-5">
          <h1 className="text-2xl font-semibold tracking-tight">{t("title")}</h1>
          <dl className="text-sm">
            <div className="flex gap-2">
              <dt className="text-text-muted">{t("number")}</dt>
              <dd className="font-semibold tabular-nums">{invoice.number}</dd>
            </div>
            <div className="flex gap-2">
              <dt className="text-text-muted">{t("date")}</dt>
              <dd>{issued}</dd>
            </div>
          </dl>
        </header>

        <div className="grid grid-cols-1 gap-5 border-b py-5 sm:grid-cols-2">
          <Party heading={t("supplier")} party={invoice.supplier} gstinLabel={t("gstin")} unregistered={t("unregistered")} />
          <Party heading={t("buyer")} party={invoice.buyer} gstinLabel={t("gstin")} unregistered={t("unregistered")} />
          <p className="text-sm sm:col-span-2">
            <span className="text-text-muted">{t("placeOfSupply")}: </span>
            {invoice.place_of_supply ?? "—"}
          </p>
        </div>

        <div className="overflow-x-auto">
          <table className="mt-4 w-full text-sm">
            <thead>
              <tr className="border-b text-left text-text-muted">
                <th className="py-2 pr-3 font-medium">{t("description")}</th>
                <th className="py-2 pr-3 font-medium">{t("sac")}</th>
                <th className="py-2 text-right font-medium">{t("taxable")}</th>
              </tr>
            </thead>
            <tbody>
              <tr className="border-b">
                <td className="py-3 pr-3">{invoice.description}</td>
                <td className="py-3 pr-3 tabular-nums">{invoice.sac_code}</td>
                <td className="py-3 text-right tabular-nums">{money(invoice.taxable_paise)}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <dl className="mt-4 ml-auto w-full max-w-xs space-y-1.5 text-sm tabular-nums">
          <div className="flex justify-between gap-4">
            <dt className="text-text-muted">{t("taxable")}</dt>
            <dd>{money(invoice.taxable_paise)}</dd>
          </div>
          {taxes.map(([label, amount]) => (
            <div key={label} className="flex justify-between gap-4">
              <dt className="text-text-muted">{label}</dt>
              <dd>{money(Number(amount))}</dd>
            </div>
          ))}
          <div className="flex justify-between gap-4 border-t pt-2 text-base font-semibold">
            <dt>{t("total")}</dt>
            <dd>{money(invoice.total_paise)}</dd>
          </div>
        </dl>

        <p className="mt-8 text-[12px] text-text-muted">{t("footer")}</p>
      </article>
    </main>
  );
}
