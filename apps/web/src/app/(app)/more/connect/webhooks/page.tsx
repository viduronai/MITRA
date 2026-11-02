import { ChevronLeft } from "lucide-react";
import Link from "next/link";
import { redirect } from "next/navigation";
import { getTranslations } from "next-intl/server";
import { WebhooksManager } from "@/components/leads/webhooks-manager";
import { PageHeader } from "@/components/shell/page-header";
import { ApiError } from "@/lib/api";
import { webhooksApi } from "@/lib/leads/api";
import type { WebhookDelivery } from "@/lib/leads/types";
import { requireSession } from "@/lib/session";

export async function generateMetadata() {
  const t = await getTranslations("webhooks");
  return { title: t("title") };
}

export default async function WebhooksPage() {
  const { token } = await requireSession();
  const [t, tl] = await Promise.all([getTranslations("webhooks"), getTranslations("leads")]);

  let hooks;
  const deliveries: Record<string, WebhookDelivery[]> = {};
  try {
    hooks = (await webhooksApi.list(token)).items;
    const logs = await Promise.all(hooks.map((h) => webhooksApi.deliveries(token, h.id, 10)));
    hooks.forEach((h, i) => (deliveries[h.id] = logs[i].items));
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) redirect("/login?expired=1");
    const key = error instanceof ApiError && error.status === 403 ? "forbidden" : "generic";
    return (
      <>
        <PageHeader title={t("title")} />
        <p role="alert" className="rounded-xl border border-dashed px-5 py-8 text-center text-text-muted">
          {tl(`errors.${key}`)}
        </p>
      </>
    );
  }

  return (
    <>
      <Link href="/more/connect" className="focus-ring -mt-1 mb-2 inline-flex items-center gap-1 rounded-md text-sm font-medium text-text-muted hover:text-foreground">
        <ChevronLeft aria-hidden className="size-4" />
        {t("back")}
      </Link>
      <PageHeader title={t("title")} />
      <p className="-mt-2 mb-5 text-text-muted">{t("subtitle")}</p>
      <WebhooksManager hooks={hooks} deliveries={deliveries} />
    </>
  );
}
