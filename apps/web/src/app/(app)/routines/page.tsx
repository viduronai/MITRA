import { getTranslations } from "next-intl/server";
import { RoutineBuilder } from "@/components/routines/routine-builder";
import { RoutineLibrary, RoutineList } from "@/components/routines/routine-list";
import { PageHeader } from "@/components/shell/page-header";
import { api } from "@/lib/api";
import type { Employee } from "@/lib/api/types";
import { requireSession } from "@/lib/session";
import { routinesApi } from "@/lib/team/api";
import type { LibraryRoutine, Routine } from "@/lib/team/types";

export async function generateMetadata() {
  const t = await getTranslations("routines");
  return { title: t("title") };
}

export default async function RoutinesPage() {
  const t = await getTranslations("routines");
  const { token } = await requireSession();
  const [routines, library, employees] = await Promise.all([
    routinesApi.list(token).catch((): Routine[] => []),
    routinesApi.library(token).catch((): LibraryRoutine[] => []),
    api.listEmployees(token).catch((): Employee[] => []),
  ]);
  const names = Object.fromEntries(employees.map((e) => [e.id, e.name]));

  return (
    <>
      <PageHeader title={t("title")} subtitle={t("subtitle")} />
      <div className="flex flex-col gap-6">
        <RoutineList routines={routines} employees={names} />
        <RoutineLibrary items={library} existing={routines.map((r) => r.library_id ?? "")} employees={names} />
        <RoutineBuilder employees={employees.map((e) => ({ id: e.id, name: e.name }))} />
      </div>
    </>
  );
}
