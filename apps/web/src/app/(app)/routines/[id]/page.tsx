import Link from "next/link";
import { notFound } from "next/navigation";
import { getTranslations } from "next-intl/server";
import { RunHistory } from "@/components/routines/run-history";
import { PageHeader } from "@/components/shell/page-header";
import { requireSession } from "@/lib/session";
import { routinesApi } from "@/lib/team/api";
import { routineName } from "@/lib/team/i18n";
import { ID_RE } from "@/lib/team/run";

export async function generateMetadata() {
  const t = await getTranslations("routines");
  return { title: t("historyTitle") };
}

export default async function RoutineHistoryPage({ params }: PageProps<"/routines/[id]">) {
  const { id } = await params;
  if (!ID_RE.test(id)) notFound();
  const t = await getTranslations("routines");
  const { token } = await requireSession();
  const [routines, runs] = await Promise.all([routinesApi.list(token), routinesApi.runs(token, id).catch(() => null)]);
  const routine = routines.find((r) => r.id === id);
  if (!routine || runs === null) notFound();

  return (
    <>
      <Link href="/routines" className="mb-3 inline-block text-sm text-text-muted hover:underline">
        ← {t("title")}
      </Link>
      <PageHeader title={routineName(t, routine)} subtitle={t("historyTitle")} />
      <RunHistory runs={runs} />
    </>
  );
}
