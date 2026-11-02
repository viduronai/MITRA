import { getLocale, getTranslations } from "next-intl/server";
import { formatLongDate, formatTime } from "@/lib/format";
import type { Lead } from "@/lib/leads/types";

/** Latest enquiries with what happened to each (called, scheduled, not called and why). */
export async function RecentLeads({ leads }: { leads: Lead[] }) {
  const [t, locale] = await Promise.all([getTranslations("leads"), getLocale()]);
  const when = (iso: string) => {
    const d = new Date(iso);
    return `${formatLongDate(d, locale)}, ${formatTime(d, locale)}`;
  };

  return (
    <div className="mt-5">
      <h3 className="font-semibold">{t("recentTitle")}</h3>
      {leads.length === 0 ? (
        <p className="mt-1 text-sm leading-5 text-text-muted">{t("recentEmpty")}</p>
      ) : (
        <ul className="mt-2 divide-y rounded-xl border">
          {leads.map((lead) => (
            <li key={lead.id} className="flex flex-col gap-0.5 px-4 py-3 sm:flex-row sm:items-center sm:gap-4">
              <div className="min-w-0 flex-1">
                <p className="truncate font-medium">
                  {lead.name ?? `••••${lead.phone_last4}`}
                  <span className="font-normal text-text-muted"> · {t(`sources.${lead.source}`)}</span>
                </p>
                <p className="text-sm leading-5 text-text-muted">{when(lead.received_at)}</p>
              </div>
              <p className="text-sm leading-5">
                {t(`status.${lead.status}`, {
                  time: lead.call_at ? formatTime(new Date(lead.call_at), locale) : "",
                  reason: lead.reason_text[0] ?? "",
                })}
              </p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
