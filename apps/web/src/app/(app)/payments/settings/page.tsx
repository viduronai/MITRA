import { AlertTriangle, ArrowLeft } from "lucide-react";
import Link from "next/link";
import { getTranslations } from "next-intl/server";
import { EmptyState } from "@/components/mitra/empty-state";
import { CollectionSettingsForm } from "@/components/payments/collection-settings-form";
import { PageHeader } from "@/components/shell/page-header";
import { ApiError } from "@/lib/api";
import { paymentsApi } from "@/lib/payments/api";
import { requireSession } from "@/lib/session";

export async function generateMetadata() {
  const t = await getTranslations("payments.settings");
  return { title: t("title") };
}

/** How you collect: the business's own Razorpay account or UPI ID (INT-08). Owner only to change. */
export default async function CollectionSettingsPage() {
  const { token } = await requireSession();
  const t = await getTranslations("payments");
  let settings;
  try {
    settings = await paymentsApi.settings(token);
  } catch (error) {
    const forbidden = error instanceof ApiError && error.status === 403;
    return <EmptyState icon={AlertTriangle} description={forbidden ? t("errors.forbidden") : t("loadError")} />;
  }
  return (
    <>
      <Link
        href="/payments"
        className="focus-ring mb-4 inline-flex items-center gap-1.5 rounded-md text-sm font-medium text-text-muted hover:text-foreground"
      >
        <ArrowLeft className="size-4" aria-hidden />
        {t("back")}
      </Link>
      <PageHeader title={t("settings.title")} subtitle={t("settings.subtitle")} />
      <section className="max-w-3xl rounded-xl border bg-card p-5 shadow-xs md:p-6">
        <CollectionSettingsForm settings={settings} />
      </section>
    </>
  );
}
