import { UserRound } from "lucide-react";
import { getTranslations } from "next-intl/server";
import { EmptyState } from "@/components/mitra/empty-state";
import { PageHeader } from "@/components/shell/page-header";
import { Button } from "@/components/ui/button";
import { getEmployee } from "@/lib/data";

export async function generateMetadata() {
  const t = await getTranslations("customers");
  return { title: t("title") };
}

// Placeholder: the customer list and timeline arrive with the API (docs/07 §3.6).
export default async function CustomersPage() {
  const [t, employee] = await Promise.all([getTranslations("customers"), getEmployee()]);
  const name = employee?.name ?? "Mitra";

  return (
    <>
      <PageHeader title={t("title")} subtitle={t("subtitle", { name })} />
      <EmptyState
        icon={UserRound}
        title={t("emptyTitle")}
        description={t("empty", { name })}
        action={<Button>{t("emptyAction")}</Button>}
      />
    </>
  );
}
