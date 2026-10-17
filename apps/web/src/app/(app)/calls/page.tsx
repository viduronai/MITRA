import { PhoneOff } from "lucide-react";
import { getTranslations } from "next-intl/server";
import { CallRow } from "@/components/mitra/call-row";
import { EmptyState } from "@/components/mitra/empty-state";
import { PageHeader } from "@/components/shell/page-header";
import { Button } from "@/components/ui/button";
import { calls, minutesAgoToDate, requestTime } from "@/lib/mock-data";

export async function generateMetadata() {
  const t = await getTranslations("calls");
  return { title: t("title") };
}

// Light preview with mock data. Filters, search and call detail come next (docs/07 §3.4).
export default async function CallsPage() {
  const [t, tEmpty] = await Promise.all([getTranslations("calls"), getTranslations("empty")]);
  const now = requestTime();

  return (
    <>
      <PageHeader title={t("title")} subtitle={t("subtitle")} />
      {calls.length === 0 ? (
        <EmptyState
          icon={PhoneOff}
          title={tEmpty("callsTitle")}
          description={tEmpty("calls")}
          action={<Button>{tEmpty("callsAction")}</Button>}
        />
      ) : (
        <section aria-labelledby="calls-today" className="rounded-xl border bg-card p-3 shadow-xs md:p-4">
          <h2 id="calls-today" className="px-2 pt-2 pb-1 text-sm font-semibold text-text-muted md:px-3">
            {t("today")}
          </h2>
          <ul>
            {calls.map((call) => (
              <li key={call.id}>
                <CallRow call={{ ...call, at: minutesAgoToDate(call.minutesAgo, now) }} href="/calls" />
              </li>
            ))}
          </ul>
        </section>
      )}
    </>
  );
}
