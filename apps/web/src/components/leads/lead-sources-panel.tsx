"use client";

import { KeyRound, Plug } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState, useTransition } from "react";
import { toast } from "sonner";
import { enableLeads, rotateLeadSecret } from "@/app/(app)/more/connect/lead-actions";
import { Button } from "@/components/ui/button";
import type { LeadSetup } from "@/lib/leads/types";
import { CopyBlock } from "./copy-block";
import { SourceCard, type EmployeeOption } from "./source-card";

/**
 * "Connect my leads" (INT-01/02/03/06/12/14). The secret key is shown only in the response that
 * created or rotated it, so it lives in client state until the page is left.
 */
export function LeadSourcesPanel({
  setup: initial,
  businessName,
  employees,
  lastLead,
}: {
  setup: LeadSetup;
  businessName: string;
  employees: EmployeeOption[];
  lastLead: Record<string, string>;
}) {
  const t = useTranslations("leads");
  const [secret, setSecret] = useState<string | null>(null);
  const [created, setCreated] = useState<LeadSetup | null>(null);
  const [pending, startTransition] = useTransition();
  const setup = initial.enabled ? initial : (created ?? initial);

  const withSecret = (action: typeof enableLeads, message?: string) =>
    startTransition(async () => {
      const res = await action();
      if (!res.ok) {
        toast.error(t(`errors.${res.error}`));
        return;
      }
      if (!initial.enabled) setCreated(res.data);
      if (res.data.secret) setSecret(res.data.secret);
      if (message) toast.success(message);
    });

  if (!setup.enabled || !setup.urls) {
    return (
      <div className="mt-4">
        <p className="text-sm leading-5 text-text-muted">{t("enableHint")}</p>
        <Button className="mt-3 w-full sm:w-fit" disabled={pending} aria-busy={pending} onClick={() => withSecret(enableLeads)}>
          <Plug aria-hidden />
          {t("enableCta")}
        </Button>
      </div>
    );
  }

  return (
    <div className="mt-4 flex flex-col gap-4">
      <div className="rounded-xl border p-4">
        <div className="flex items-center gap-2">
          <KeyRound aria-hidden className="size-4 text-text-muted" />
          <h3 className="font-semibold">{t("secretTitle")}</h3>
        </div>
        {secret ? (
          <>
            <p role="status" className="mt-2 rounded-lg bg-warning/10 px-3 py-2 text-sm leading-5 font-medium text-warning-fg">
              {t("secretOnce")}
            </p>
            <CopyBlock className="mt-3" label={t("secretTitle")} value={secret} />
          </>
        ) : (
          <p className="mt-1 text-sm leading-5 text-text-muted">{t("secretHidden", { hint: `${setup.secret_hint}…` })}</p>
        )}
        <Button variant="secondary" size="sm" className="mt-3" disabled={pending} onClick={() => withSecret(rotateLeadSecret, t("rotated"))}>
          {t("rotate")}
        </Button>
        <p className="mt-2 text-xs leading-5 text-text-muted">{t("rotateHint")}</p>
      </div>

      <ul className="flex flex-col gap-3">
        {setup.sources.map((source) => (
          <SourceCard
            key={source.kind}
            source={source}
            urls={setup.urls!}
            secret={secret}
            businessName={businessName}
            employees={employees}
            lastLeadText={lastLead[source.kind] ?? null}
          />
        ))}
      </ul>
      <p className="text-sm leading-5 text-text-muted">{t("consentNote")}</p>
    </div>
  );
}
