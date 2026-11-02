import { MessageCircleOff } from "lucide-react";
import { getTranslations } from "next-intl/server";
import { redirect } from "next/navigation";
import { WhatsAppSim } from "@/components/manager/whatsapp-sim";
import { EmptyState } from "@/components/mitra/empty-state";
import { PageHeader } from "@/components/shell/page-header";
import { ApiError } from "@/lib/api";
import { managerApi } from "@/lib/manager/api";
import type { WaMessage } from "@/lib/manager/types";
import { requireSession } from "@/lib/session";

export async function generateMetadata() {
  const t = await getTranslations("waSim");
  return { title: t("title") };
}

/** Dev tool: core answers 404 here unless the WhatsApp provider is the simulator. */
export default async function WhatsAppSimPage() {
  const [t, { token }] = await Promise.all([getTranslations("waSim"), requireSession()]);
  let messages: WaMessage[] | null = null;
  try {
    messages = await managerApi.simMessages(token);
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) redirect("/login?expired=1");
  }
  return (
    <>
      <PageHeader title={t("title")} subtitle={t("subtitle")} />
      {messages ? <WhatsAppSim messages={messages} /> : <EmptyState icon={MessageCircleOff} description={t("unavailable")} />}
    </>
  );
}
