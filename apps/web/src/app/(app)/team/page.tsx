import { Sparkles } from "lucide-react";
import { getTranslations } from "next-intl/server";
import { VoiceTierPicker } from "@/components/billing/voice-tier-picker";
import { EmployeeCard } from "@/components/mitra/employee-card";
import { PageHeader } from "@/components/shell/page-header";
import { api } from "@/lib/api";
import type { CatalogVoice, Rate } from "@/lib/api/types";
import { getEmployee } from "@/lib/data";
import { requireSession } from "@/lib/session";
// MOCK: today's counts are invented until calls exist in the API.
import { employee as mockEmployee } from "@/lib/mock-data";

export async function generateMetadata() {
  const t = await getTranslations("team");
  return { title: t("title") };
}

export default async function TeamPage() {
  const [t, tEmployee, employee] = await Promise.all([getTranslations("team"), getTranslations("employee"), getEmployee()]);
  const name = employee?.name ?? "Mitra";
  // The tier picker is optional chrome: if the catalog can't load, the page still renders.
  const { token } = await requireSession();
  const [rates, voices] = employee
    ? await Promise.all([api.rates(token), api.voices(token)]).catch((): [Rate[], CatalogVoice[]] => [[], []])
    : [[], []];
  const tBilling = await getTranslations("billing");

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
        {employee && rates.length > 0 && (
          <section aria-labelledby="tier-title" className="rounded-xl border bg-card p-5 shadow-xs md:p-6">
            <h2 id="tier-title" className="font-semibold">
              {tBilling("tiersTitle")}
            </h2>
            <p className="mt-1 mb-3 text-sm text-text-muted">{tBilling("tiersHint")}</p>
            <VoiceTierPicker
              employeeId={employee.id}
              employeeName={employee.name}
              tier={employee.voice_tier}
              rates={Object.fromEntries(rates.map((r) => [r.tier, Math.round(r.inr_per_min * 100)]))}
              voiceName={voices.find((v) => v.id === employee.voice_id)?.name ?? null}
            />
          </section>
        )}
        <div className="flex items-start gap-3 rounded-xl border border-dashed p-5 text-text-muted md:p-6">
          <Sparkles className="mt-0.5 size-5 shrink-0 text-sky-400" aria-hidden />
          <p>{t("moreSoon")}</p>
        </div>
      </div>
    </>
  );
}
