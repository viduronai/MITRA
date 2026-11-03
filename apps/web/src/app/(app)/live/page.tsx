import Link from "next/link";
import { getLocale, getTranslations } from "next-intl/server";
import { AutoRefresh } from "@/components/live/live-call";
import { LiveDot } from "@/components/mitra/live-dot";
import { PageHeader } from "@/components/shell/page-header";
import { ApiError } from "@/lib/api";
import { formatTime } from "@/lib/format";
import { requireSession } from "@/lib/session";
import { liveApi } from "@/lib/team/api";
import type { LiveCall } from "@/lib/team/types";
import { label } from "@/lib/team/i18n";

export async function generateMetadata() {
  const t = await getTranslations("live");
  return { title: t("title") };
}

export default async function LiveCallsPage() {
  const [t, locale] = await Promise.all([getTranslations("live"), getLocale()]);
  const { token } = await requireSession();
  let calls: LiveCall[] = [];
  let forbidden = false;
  try {
    calls = await liveApi.list(token);
  } catch (error) {
    forbidden = error instanceof ApiError && error.status === 403;
  }

  return (
    <>
      <PageHeader title={t("title")} subtitle={t("subtitle")} />
      <AutoRefresh />
      {forbidden ? (
        <p className="text-text-muted">{t("forbidden")}</p>
      ) : calls.length === 0 ? (
        <p className="text-text-muted">{t("none")}</p>
      ) : (
        <ul className="flex flex-col gap-3">
          {calls.map((call) => (
            <li key={call.id}>
              <Link
                href={`/live/${call.id}`}
                className="flex items-center gap-3 rounded-xl border bg-card p-4 shadow-xs hover:bg-surface-2"
              >
                <LiveDot />
                <div className="min-w-0 flex-1">
                  <p className="truncate font-semibold">
                    {call.customer_name ?? (call.phone_last4 ? `••••${call.phone_last4}` : t("caller"))}
                  </p>
                  <p className="text-sm text-text-muted">
                    {t("withEmployee", { name: call.employee_name ?? t("employee") })} ·{" "}
                    {label(t, `direction.${call.direction}`, call.direction)} · {t("since", { time: formatTime(new Date(call.started_at), locale) })}
                  </p>
                </div>
                <span className="text-sm font-medium text-brand-700">{t("listen")}</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
