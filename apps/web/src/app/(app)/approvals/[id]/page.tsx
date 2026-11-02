import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { notFound, redirect } from "next/navigation";
import { getLocale, getTranslations } from "next-intl/server";
import { ApprovalReview } from "@/components/manager/approval-review";
import { PageHeader } from "@/components/shell/page-header";
import { ApiError } from "@/lib/api";
import { formatLongDate, formatTime } from "@/lib/format";
import { managerApi } from "@/lib/manager/api";
import { requireSession } from "@/lib/session";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export async function generateMetadata() {
  const t = await getTranslations("approvals");
  return { title: t("title") };
}

export default async function ApprovalPage({ params }: { params: Promise<{ id: string }> }) {
  const [{ id }, t, locale, { token }] = await Promise.all([
    params,
    getTranslations("approvals"),
    getLocale(),
    requireSession(),
  ]);
  if (!UUID.test(id)) notFound();
  let detail: Awaited<ReturnType<typeof managerApi.approval>>;
  try {
    detail = await managerApi.approval(token, id);
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) redirect("/login?expired=1");
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }
  const { approval, events } = detail;
  // Kinds/events come from other modules too: unknown ones show their raw name.
  const label = (key: string, fallback: string) => (t.has(key as never) ? t(key as never) : fallback);
  const when = (iso: string) => `${formatLongDate(new Date(iso), locale)} · ${formatTime(new Date(iso), locale)}`;

  return (
    <>
      <Link href="/approvals" className="focus-ring mb-4 inline-flex items-center gap-1.5 text-[14px] text-text-muted">
        <ArrowLeft className="size-4" aria-hidden />
        {t("back")}
      </Link>
      <PageHeader
        title={label(`kinds.${approval.kind}`, approval.kind)}
        subtitle={`${t(`status.${approval.status}`)} · ${when(approval.created_at)}`}
      />
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
        <ApprovalReview key={`${approval.id}:${approval.version}`} approval={approval} />
        <section aria-labelledby="events-title" className="rounded-xl border bg-card p-5 shadow-xs">
          <h2 id="events-title" className="text-lg leading-[26px] font-semibold">
            {t("eventsTitle")}
          </h2>
          <ol className="mt-3 flex flex-col gap-3">
            {events.map((e) => (
              <li key={e.id} className="flex flex-col">
                <span className="font-medium">
                  {label(`events.${e.event}`, e.event)}
                  {e.via && ` · ${label(`via.${e.via}`, e.via)}`}
                </span>
                <span className="text-[13px] text-text-muted">
                  {when(e.created_at)} · v{e.version}
                </span>
              </li>
            ))}
          </ol>
          {approval.apply_error && <p className="mt-3 text-[13px] text-danger-fg">{t("applyError")}</p>}
        </section>
      </div>
    </>
  );
}
