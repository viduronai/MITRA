"use client";

import { useTranslations } from "next-intl";
import { useState, useTransition } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { saveRules } from "@/lib/manager/actions";
import type { ApprovalRule } from "@/lib/manager/types";

/** APPR-01: "Ask me first when…" as plain sentences with one number each. */
export function RulesForm({ initial, canEdit }: { initial: ApprovalRule[]; canEdit: boolean }) {
  const t = useTranslations("approvals.rules");
  const [rules, setRules] = useState(initial);
  const [pending, start] = useTransition();

  const update = (kind: ApprovalRule["kind"], patch: Partial<ApprovalRule>) =>
    setRules((list) => list.map((r) => (r.kind === kind ? { ...r, ...patch } : r)));

  const save = () =>
    start(async () => {
      const result = await saveRules(rules);
      if (result.ok) toast.success(t("saved"));
      else toast.error(t("error"));
    });

  return (
    <section aria-labelledby="rules-title" className="rounded-xl border bg-card p-5 shadow-xs md:p-6">
      <h2 id="rules-title" className="text-lg leading-[26px] font-semibold">
        {t("title")}
      </h2>
      <ul className="mt-4 flex flex-col divide-y">
        {rules.map((rule) => (
          <li key={rule.kind} className="flex flex-col gap-2 py-3 sm:flex-row sm:items-center sm:justify-between">
            <label className="flex items-center gap-3">
              <input
                type="checkbox"
                className="size-5"
                checked={rule.enabled}
                disabled={!canEdit || pending}
                onChange={(event) => update(rule.kind, { enabled: event.target.checked })}
              />
              <span>{t(`kinds.${rule.kind}`)}</span>
            </label>
            {rule.threshold !== null && (
              <label className="flex items-center gap-2 text-[14px] text-text-muted">
                {t(`above.${rule.kind}`)}
                <Input
                  type="number"
                  min={0}
                  className="w-28"
                  value={rule.threshold}
                  disabled={!canEdit || pending || !rule.enabled}
                  onChange={(event) => update(rule.kind, { threshold: Math.max(0, Math.floor(Number(event.target.value) || 0)) })}
                />
              </label>
            )}
          </li>
        ))}
      </ul>
      {canEdit && (
        <Button className="mt-4" disabled={pending} onClick={save}>
          {t("save")}
        </Button>
      )}
    </section>
  );
}
