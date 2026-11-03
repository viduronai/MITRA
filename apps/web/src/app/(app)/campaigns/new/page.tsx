import { ArrowLeft, CloudOff, UserRound } from "lucide-react";
import Link from "next/link";
import { redirect } from "next/navigation";
import { getLocale, getTranslations } from "next-intl/server";
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
  const [t, tList, raw, { token, canManage }] = await Promise.all([
    getTranslations("campaigns.wizard"),
    getTranslations("campaigns"),
    getLocale(),
    campaignSession(),
  ]);
  if (!canManage) redirect("/campaigns");
  const language = raw === "hi" || raw === "te" ? raw : "en";
  const [employees, settings, service, promotional] = await Promise.all([
    employeeOptions(token),
    load(() => campaignsApi.channels(token)),
    load(() => campaignsApi.consentText(token, "service", language)),
    load(() => campaignsApi.consentText(token, "promotional", language)),
  ]);
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
      ) : !service || !promotional ? (
        <EmptyState icon={CloudOff} title={tList("unavailableTitle")} description={tList("unavailable")} />
      ) : (
        <CampaignWizard
          employees={employees}
          channels={settings?.channels ?? 5}
          consentTexts={{ service: service.text, promotional: promotional.text }}
          language={language}
        />
      )}
    </>
  );
}
