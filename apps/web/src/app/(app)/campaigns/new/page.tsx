import { ArrowLeft, UserRound } from "lucide-react";
import Link from "next/link";
import { redirect } from "next/navigation";
import { getTranslations } from "next-intl/server";
import { CampaignWizard } from "@/components/campaigns/campaign-wizard";
import { EmptyState } from "@/components/mitra/empty-state";
import { PageHeader } from "@/components/shell/page-header";
import { Button } from "@/components/ui/button";
import { campaignSession, campaignsApi, employeeOptions, load } from "@/lib/campaigns/data";

export async function generateMetadata() {
  const t = await getTranslations("campaigns.wizard");
  return { title: t("title") };
}

export default async function NewCampaignPage() {
  const [t, { token, canManage }] = await Promise.all([getTranslations("campaigns.wizard"), campaignSession()]);
  if (!canManage) redirect("/campaigns");
  const [employees, settings] = await Promise.all([employeeOptions(token), load(() => campaignsApi.channels(token))]);
  return (
    <>
      <Button asChild variant="ghost" size="sm" className="mb-2 -ml-2">
        <Link href="/campaigns">
          <ArrowLeft aria-hidden />
          {t("backToList")}
        </Link>
      </Button>
      <PageHeader title={t("title")} subtitle={t("subtitle")} />
      {employees.length === 0 ? (
        <EmptyState icon={UserRound} title={t("noEmployeeTitle")} description={t("noEmployee")} />
      ) : (
        <CampaignWizard employees={employees} channels={settings?.channels ?? 5} />
      )}
    </>
  );
}
