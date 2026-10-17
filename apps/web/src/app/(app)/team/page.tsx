import { Sparkles } from "lucide-react";
import { getTranslations } from "next-intl/server";
import { EmployeeCard } from "@/components/mitra/employee-card";
import { PageHeader } from "@/components/shell/page-header";
import { employee } from "@/lib/mock-data";

export async function generateMetadata() {
  const t = await getTranslations("team");
  return { title: t("title") };
}

export default async function TeamPage() {
  const [t, tEmployee] = await Promise.all([getTranslations("team"), getTranslations("employee")]);

  return (
    <>
      <PageHeader title={t("title")} subtitle={t("subtitle")} />
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <EmployeeCard
          name={employee.name}
          initials={employee.initials}
          role={tEmployee(employee.role)}
          status={employee.status}
          summary={`${tEmployee("callsToday", { count: employee.callsToday })} · ${tEmployee("bookedToday", { count: employee.bookedToday })}`}
        />
        <div className="flex items-start gap-3 rounded-xl border border-dashed p-5 text-text-muted md:p-6">
          <Sparkles className="mt-0.5 size-5 shrink-0 text-accent-400" aria-hidden />
          <p>{t("moreSoon")}</p>
        </div>
      </div>
    </>
  );
}
