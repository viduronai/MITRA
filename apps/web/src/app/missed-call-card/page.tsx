import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { redirect } from "next/navigation";
import { getTranslations } from "next-intl/server";
import QRCode from "qrcode";
import { PrintButton } from "@/components/billing/print-button";
import { ApiError } from "@/lib/api";
import { getBusiness } from "@/lib/data";
import { requireSession } from "@/lib/session";
import { telephonyApi } from "@/lib/telephony/api";
import type { MissedCallSetup } from "@/lib/telephony/types";

/** Shop-counter card for the missed-call number (CALL-20). Outside the app shell so it prints alone. */

export async function generateMetadata() {
  const t = await getTranslations("missedCall");
  return { title: t("cardTitle") };
}

export default async function MissedCallCardPage() {
  const { token } = await requireSession();
  const [t, business] = await Promise.all([getTranslations("missedCall"), getBusiness()]);
  let setup: MissedCallSetup;
  try {
    setup = await telephonyApi.missedCall(token);
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) redirect("/login?expired=1");
    throw error;
  }
  if (!setup.tel_uri || !setup.poster || !setup.display) redirect("/more/connect#missed-call");
  // The QR code dials the number (tel: URI); rendered on the server as an inline SVG.
  const qr = await QRCode.toString(setup.tel_uri, { type: "svg", margin: 1, errorCorrectionLevel: "M" });

  return (
    <main className="mx-auto w-full max-w-md px-4 py-6 md:py-10 print:max-w-none print:p-0">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3 print:hidden">
        <Link href="/more/connect#missed-call" className="focus-ring inline-flex min-h-11 items-center gap-2 text-sm font-medium text-brand-600">
          <ArrowLeft className="size-4" aria-hidden /> {t("back")}
        </Link>
        <PrintButton label={t("print")} />
      </div>

      <article className="rounded-2xl border-2 border-foreground bg-white p-6 text-center text-black shadow-xs print:shadow-none">
        {business?.name && <p className="text-lg font-semibold">{business.name}</p>}
        <p className="mt-1 text-sm tracking-wide uppercase">{t("cardKicker")}</p>
        <p className="mt-3 text-3xl font-bold tabular-nums">{setup.display}</p>
        <div
          className="mx-auto mt-4 size-48 [&_svg]:size-full"
          role="img"
          aria-label={t("qrLabel", { number: setup.display })}
          dangerouslySetInnerHTML={{ __html: qr }}
        />
        <p className="mt-2 text-xs">{t("scanHint")}</p>
        <div className="mt-4 space-y-2 border-t border-black/20 pt-4 text-[15px] leading-6">
          <p lang="te">{setup.poster.te}</p>
          <p lang="hi">{setup.poster.hi}</p>
          <p lang="en">{setup.poster.en}</p>
        </div>
        <p className="mt-3 text-xs">{t("free")}</p>
      </article>
    </main>
  );
}
