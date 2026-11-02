"use client";

import { ArrowRight, Sparkles } from "lucide-react";
import { useTranslations } from "next-intl";
import { useTransition } from "react";
import { toast } from "sonner";
import { activateTeam, hireTeam } from "@/app/(app)/team/actions";
import { Button } from "@/components/ui/button";
import type { TeamTemplate } from "@/lib/team/types";
import { label } from "@/lib/team/i18n";

/** TEAM-01 / ONB-14: one tap hires a whole team for the industry. */
export function HireTeam({ templates }: { templates: TeamTemplate[] }) {
  const t = useTranslations("teamMap");
  const [pending, start] = useTransition();
  const ordered = [...templates].sort((a, b) => Number(b.recommended) - Number(a.recommended));

  const hire = (id: string) =>
    start(async () => {
      const result = await hireTeam(id);
      if (result.ok) toast.success(t("hired"));
      else toast.error(t(result.error === "conflict" ? "alreadyHired" : "error"));
    });

  return (
    <section aria-labelledby="hire-title" className="flex flex-col gap-3">
      <h2 id="hire-title" className="text-lg font-semibold">
        {t("hireTitle")}
      </h2>
      <p className="text-sm text-text-muted">{t("hireHint")}</p>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        {ordered.map((tpl) => (
          <article key={tpl.id} className="flex flex-col gap-3 rounded-xl border bg-card p-5 shadow-xs">
            <div className="flex items-center justify-between gap-2">
              <h3 className="font-semibold">{t(`templates.${tpl.id}`)}</h3>
              {tpl.recommended && (
                <span className="inline-flex items-center gap-1 rounded-full bg-sky-100 px-2 py-0.5 text-xs font-semibold text-sky-ink">
                  <Sparkles className="size-3" aria-hidden />
                  {t("recommended")}
                </span>
              )}
            </div>
            <ol className="flex flex-wrap items-center gap-1 text-sm text-text-muted">
              {tpl.roles.map((role, i) => (
                <li key={role.id} className="flex items-center gap-1">
                  <span className="rounded-md bg-surface-2 px-2 py-0.5">{label(t, `roles.${role.id}`, role.title)}</span>
                  {i < tpl.roles.length - 1 && <ArrowRight className="size-3.5" aria-hidden />}
                </li>
              ))}
            </ol>
            <Button className="mt-auto" disabled={pending} onClick={() => hire(tpl.id)}>
              {t("hire")}
            </Button>
          </article>
        ))}
      </div>
    </section>
  );
}

export function ActivateTeam({ teamId }: { teamId: string }) {
  const t = useTranslations("teamMap");
  const [pending, start] = useTransition();
  return (
    <Button
      disabled={pending}
      onClick={() =>
        start(async () => {
          const result = await activateTeam(teamId);
          if (result.ok) toast.success(t("activated"));
          else toast.error(t("error"));
        })
      }
    >
      {t("activate")}
    </Button>
  );
}
