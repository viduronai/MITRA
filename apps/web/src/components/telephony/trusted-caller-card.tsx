"use client";

import { BadgeCheck, CircleDashed, Clock, PlayCircle, ShieldCheck } from "lucide-react";
import { useTranslations } from "next-intl";
import { useId, useState, useTransition } from "react";
import { toast } from "sonner";
import { resumeNumber, showMyName } from "@/app/(app)/more/connect/actions";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { NumberHealth, PhoneNumber, VerificationStatus } from "@/lib/telephony/types";
import { cn } from "@/lib/utils";
import { CallerPreview } from "./caller-preview";
import { KycForm } from "./request-number";

const HEALTH_STYLE: Record<NumberHealth, string> = {
  healthy: "bg-success/15 text-success-fg",
  watch: "bg-warning/15 text-warning-fg",
  paused: "bg-danger/10 text-danger-fg",
};

export function HealthPill({ health }: { health: NumberHealth }) {
  const t = useTranslations("connect");
  return (
    <span className={cn("inline-flex h-6 items-center gap-1.5 rounded-full px-2.5 text-xs font-medium", HEALTH_STYLE[health])}>
      <span aria-hidden className="size-1.5 rounded-full bg-current" />
      {t(`health.${health}`)}
    </span>
  );
}

function Check({ label, status }: { label: string; status: VerificationStatus }) {
  const t = useTranslations("connect");
  const Icon = status === "verified" ? BadgeCheck : status === "pending" ? Clock : CircleDashed;
  return (
    <li className="flex items-center gap-2 text-sm leading-5">
      <Icon
        aria-hidden
        className={cn("size-4 shrink-0", status === "verified" ? "text-success-fg" : "text-text-subtle")}
      />
      <span className="flex-1">{label}</span>
      <span className="text-text-muted">{t(`verification.${status}`)}</span>
    </li>
  );
}

function CallerName({ number }: { number: PhoneNumber }) {
  const t = useTranslations("connect");
  const id = useId();
  const [name, setName] = useState(number.display_name ?? "");
  const [pending, startTransition] = useTransition();
  const verified = number.truecaller_status === "verified" && number.cnap_status === "verified";
  const inReview = number.truecaller_status === "pending" || number.cnap_status === "pending";
  if (verified) return null;

  return (
    <form
      className="mt-4 flex flex-col gap-3 rounded-lg bg-surface-2 p-4"
      onSubmit={(e) => {
        e.preventDefault();
        startTransition(async () => {
          const res = await showMyName(number.id, name);
          if (!res.ok) toast.error(t(`errors.${res.error}`));
          else toast.success(t("nameSubmitted"));
        });
      }}
    >
      <div>
        <p className="font-medium">{t("showName")}</p>
        <p className="text-sm leading-5 text-text-muted">{inReview ? t("nameInReview") : t("showNameDesc")}</p>
      </div>
      <div className="flex flex-col gap-2">
        <Label htmlFor={id}>{t("nameLabel")}</Label>
        <Input id={id} value={name} maxLength={60} required onChange={(e) => setName(e.target.value)} />
      </div>
      <Button type="submit" variant="secondary" className="w-full sm:w-fit" disabled={pending || !name.trim()} aria-busy={pending}>
        <ShieldCheck aria-hidden />
        {inReview ? t("updateName") : t("submitName")}
      </Button>
    </form>
  );
}

/** One business number on the "Trusted Caller ID" card (07 section 3.7). */
export function TrustedCallerCard({ number, businessName }: { number: PhoneNumber; businessName: string }) {
  const t = useTranslations("connect");
  const [pending, startTransition] = useTransition();
  const live = number.kyc_status === "approved" && Boolean(number.e164);
  const verified = number.truecaller_status === "verified" && number.cnap_status === "verified";
  const rate = number.answer_rate_7d;

  return (
    <article className="rounded-xl border bg-surface p-4 md:p-5">
      <div className="grid gap-5 md:grid-cols-[1fr_auto]">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="font-mono text-lg leading-7 font-semibold">{number.display ?? t("waitingNumber")}</h3>
            {live && <HealthPill health={number.health} />}
          </div>
          <p className="text-sm leading-5 text-text-muted">
            {t(`types.${number.type}`)}
            {number.city ? ` · ${number.city}` : ""} · {t(`kyc.${number.kyc_status}`)}
          </p>

          <dl className="mt-4 grid grid-cols-2 gap-3">
            <div className="rounded-lg bg-surface-2 px-3 py-2">
              <dt className="text-xs leading-4 text-text-muted">{t("answerRate")}</dt>
              <dd className="text-lg leading-7 font-semibold tabular-nums">
                {rate === null ? <span className="text-sm font-normal text-text-muted">{t("noCallsYet")}</span> : `${Math.round(rate * 100)}%`}
              </dd>
            </div>
            <div className="rounded-lg bg-surface-2 px-3 py-2">
              <dt className="text-xs leading-4 text-text-muted">{t("kycLabel")}</dt>
              <dd className="text-sm leading-7 font-medium">{t(`kyc.${number.kyc_status}`)}</dd>
            </div>
          </dl>

          <ul className="mt-4 flex flex-col gap-2">
            <Check label={t("truecaller")} status={number.truecaller_status} />
            <Check label={t("cnap")} status={number.cnap_status} />
          </ul>

          {number.health !== "healthy" && live && (
            <div className={cn("mt-4 rounded-lg px-4 py-3 text-sm leading-5", HEALTH_STYLE[number.health])}>
              {number.health_reasons.length > 0 && <p className="font-medium">{number.health_reasons.join(" · ")}</p>}
              <p className="mt-1 font-medium">{t("remediationTitle")}</p>
              <ul className="mt-1 list-disc pl-5">
                {number.remediation.map((step) => (
                  <li key={step}>{step}</li>
                ))}
              </ul>
              {number.health === "paused" && !number.spam_flag && (
                <Button
                  size="sm"
                  variant="secondary"
                  className="mt-3"
                  disabled={pending}
                  onClick={() =>
                    startTransition(async () => {
                      const res = await resumeNumber(number.id);
                      if (!res.ok) toast.error(t(`errors.${res.error}`));
                    })
                  }
                >
                  <PlayCircle aria-hidden />
                  {t("resume")}
                </Button>
              )}
            </div>
          )}

          {(number.kyc_status === "pending_kyc" || number.kyc_status === "rejected") && <KycForm number={number} />}
          {number.kyc_status === "submitted" && (
            <p className="mt-4 rounded-lg bg-sky-100 px-4 py-3 text-sm leading-5 text-sky-ink">{t("kycSubmitted")}</p>
          )}
          <CallerName number={number} />
        </div>

        <CallerPreview
          name={number.display_name ?? businessName}
          number={number.display}
          verified={verified}
          className="md:w-[220px]"
        />
      </div>
    </article>
  );
}
