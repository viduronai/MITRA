"use client";

import { useLocale, useTranslations } from "next-intl";
import { useTransition } from "react";
import { toast } from "sonner";
import { decideRun } from "@/app/(app)/routines/actions";
import { Button } from "@/components/ui/button";
import { formatLongDate, formatTime } from "@/lib/format";
import type { RoutineRun } from "@/lib/team/types";
import { label } from "@/lib/team/i18n";

/** AUTO-05: what ran, who was contacted, and how each one went. */
export function RunHistory({ runs }: { runs: RoutineRun[] }) {
  const t = useTranslations("routines");
  const locale = useLocale();
  const [pending, start] = useTransition();
  if (runs.length === 0) return <p className="text-text-muted">{t("noRuns")}</p>;

  const decide = (id: string, approved: boolean) =>
    start(async () => {
      const res = await decideRun(id, approved);
      if (!res.ok) toast.error(t("error"));
    });

  return (
    <ol className="flex flex-col gap-3">
      {runs.map((run) => {
        const at = new Date(run.started_at);
        return (
          <li key={run.id} className="rounded-xl border bg-card p-4 shadow-xs">
            <div className="flex flex-wrap items-center gap-2">
              <p className="font-semibold">
                {formatLongDate(at, locale)}, {formatTime(at, locale)}
              </p>
              <span className="rounded-full bg-surface-2 px-2 py-0.5 text-xs">{t(`triggers.${run.trigger}`)}</span>
              <span className="rounded-full bg-surface-2 px-2 py-0.5 text-xs">{t(`runStatus.${run.status}`)}</span>
              <span className="ms-auto text-sm text-text-muted">
                {t("contactedOf", { n: run.contacted_count, total: run.audience_count })}
              </span>
            </div>
            {run.status === "awaiting_approval" && (
              <div className="mt-3 flex flex-wrap items-center gap-2 rounded-lg bg-amber-50 p-3 text-sm dark:bg-amber-950/30">
                <p className="flex-1">{t("askFirst", { n: run.contacts.filter((c) => c.status === "waiting").length })}</p>
                <Button size="sm" disabled={pending} onClick={() => decide(run.id, true)}>
                  {t("approve")}
                </Button>
                <Button size="sm" variant="secondary" disabled={pending} onClick={() => decide(run.id, false)}>
                  {t("decline")}
                </Button>
              </div>
            )}
            <ul className="mt-3 flex flex-wrap gap-2 text-sm">
              {run.contacts.map((c) => (
                <li key={c.contact_id} className="rounded-md border px-2 py-0.5">
                  {c.name ?? t("customer")} · …{c.last4} ·{" "}
                  <span className="text-text-muted">{label(t, `outcomes.${c.status}`, c.status)}</span>
                </li>
              ))}
            </ul>
          </li>
        );
      })}
    </ol>
  );
}
