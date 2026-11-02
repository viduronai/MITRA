import { CloudOff } from "lucide-react";
import { getTranslations } from "next-intl/server";
import { redirect } from "next/navigation";
import { ManagerSettingsForm } from "@/components/manager/settings-form";
import { EmptyState } from "@/components/mitra/empty-state";
import { PageHeader } from "@/components/shell/page-header";
import { ApiError } from "@/lib/api";
import { managerApi } from "@/lib/manager/api";
import type { ManagerSettings } from "@/lib/manager/types";
import { requireSession } from "@/lib/session";

export async function generateMetadata() {
  const t = await getTranslations("managerSettings");
  return { title: t("title") };
}

export default async function ManagerSettingsPage() {
  const [t, { token }] = await Promise.all([getTranslations("managerSettings"), requireSession()]);
  let settings: ManagerSettings | null = null;
  try {
    settings = await managerApi.settings(token);
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) redirect("/login?expired=1");
  }
  return (
    <>
      <PageHeader title={t("title")} subtitle={t("subtitle")} />
      {settings ? <ManagerSettingsForm initial={settings} /> : <EmptyState icon={CloudOff} description={t("errors.unreachable")} />}
    </>
  );
}
