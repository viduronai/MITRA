import { ChevronRight, Webhook } from "lucide-react";
import Link from "next/link";
import { getLocale, getTranslations } from "next-intl/server";
import { api } from "@/lib/api";
import { formatLongDate, formatTime } from "@/lib/format";
import { leadsApi } from "@/lib/leads/api";
import type { Lead, LeadSetup } from "@/lib/leads/types";
import { LeadSourcesPanel } from "./lead-sources-panel";
import { RecentLeads } from "./recent-leads";

/** Server part of "Connect my leads": loads setup, recent leads and employees. */
export async function LeadsSection({ token }: { token: string }) {
  const [t, locale] = await Promise.all([getTranslations("leads"), getLocale()]);
  let setup: LeadSetup;
  let recent: Lead[] = [];
  let employees: { id: string; name: string }[] = [];
  try {
    [setup, recent, employees] = await Promise.all([
      leadsApi.setup(token),
      leadsApi.recent(token, 10).then((r) => r.items),
      api.listEmployees(token).then((list) => list.map((e) => ({ id: e.id, name: e.name }))),
    ]);
  } catch {
    return <p role="alert" className="mt-4 text-sm text-text-muted">{t("errors.generic")}</p>;
  }
  const lastLead: Record<string, string> = {};
  for (const s of setup.sources) {
    if (s.last_lead_at) {
      const d = new Date(s.last_lead_at);
      lastLead[s.kind] = `${formatLongDate(d, locale)}, ${formatTime(d, locale)}`;
    }
  }

  return (
    <>
      <LeadSourcesPanel setup={setup} employees={employees} lastLead={lastLead} />
      {setup.enabled && <RecentLeads leads={recent} />}
      <Link
        href="/more/connect/webhooks"
        className="focus-ring mt-5 flex items-center gap-3 rounded-xl border p-4 transition-colors motion-fast hover:bg-surface-2"
      >
        <Webhook aria-hidden className="size-5 shrink-0 text-text-muted" />
        <span className="min-w-0 flex-1">
          <span className="block font-medium">{t("developers")}</span>
          <span className="block text-sm leading-5 text-text-muted">{t("developersDesc")}</span>
        </span>
        <ChevronRight aria-hidden className="size-5 text-text-muted" />
      </Link>
    </>
  );
}
