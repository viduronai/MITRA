import Link from "next/link";
import { notFound } from "next/navigation";
import { getTranslations } from "next-intl/server";
import { LiveCallView } from "@/components/live/live-call";
import { PageHeader } from "@/components/shell/page-header";
import { ApiError } from "@/lib/api";
import { requireSession } from "@/lib/session";
import { liveApi } from "@/lib/team/api";
import { ID_RE } from "@/lib/team/run";
import type { LiveDetail } from "@/lib/team/types";

export async function generateMetadata() {
  const t = await getTranslations("live");
  return { title: t("title") };
}

export default async function LiveCallPage({ params }: PageProps<"/live/[id]">) {
  const { id } = await params;
  if (!ID_RE.test(id)) notFound();
  const t = await getTranslations("live");
  const { token } = await requireSession();
  let detail: LiveDetail;
  try {
    detail = await liveApi.detail(token, id); // opening the page is logged as "listened"
  } catch (error) {
    if (error instanceof ApiError && error.status === 403) {
      return <p className="text-text-muted">{t("forbidden")}</p>;
    }
    notFound();
  }
  const who = detail.call.customer_name ?? (detail.call.phone_last4 ? `…${detail.call.phone_last4}` : t("caller"));

  return (
    <>
      <Link href="/live" className="mb-3 inline-block text-sm text-text-muted hover:underline">
        ← {t("title")}
      </Link>
      <PageHeader title={who} subtitle={t("withEmployee", { name: detail.call.employee_name ?? t("employee") })} />
      <LiveCallView initial={detail} />
    </>
  );
}
