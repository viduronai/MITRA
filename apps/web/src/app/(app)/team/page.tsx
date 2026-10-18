import { Sparkles } from "lucide-react";
import { getTranslations } from "next-intl/server";
import { EmployeeCard } from "@/components/mitra/employee-card";
import { PageHeader } from "@/components/shell/page-header";
import { getEmployee } from "@/lib/data";
// MOCK: today's counts are invented until calls exist in the API.
import { employee as mockEmployee } from "@/lib/mock-data";

export async function generateMetadata() {
  const t = await getTranslations("team");
  return { title: t("title") };
}

export default async function TeamPage() {
  const [t, tEmployee, employee] = await Promise.all([getTranslations("team"), getTranslations("employee"), getEmployee()]);
  const name = employee?.name ?? "Mitra";

  return (
    <>
      <PageHeader title={t("title")} subtitle={t("subtitle", { name })} />
      <div className="grid grid-cols-1 items-start gap-4 md:grid-cols-2">
        {employee && (
          <EmployeeCard
            name={employee.name}
            role={tEmployee(employee.role_template)}
            status={employee.status}
            summary={
              employee.status === "working"
                ? `${tEmployee("callsToday", { count: mockEmployee.callsToday })} · ${tEmployee("bookedToday", { count: mockEmployee.bookedToday })}`
                : undefined
            }
          />
        )}
        <div className="flex items-start gap-3 rounded-xl border border-dashed p-5 text-text-muted md:p-6">
          <Sparkles className="mt-0.5 size-5 shrink-0 text-sky-400" aria-hidden />
          <p>{t("moreSoon")}</p>
        </div>
      </div>
    </>
  );
}
