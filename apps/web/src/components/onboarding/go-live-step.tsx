"use client";

import { Hash, PhoneForwarded, Plug, type LucideIcon } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState, useTransition } from "react";
import { finishOnboarding, type StepErrorKey } from "@/app/onboarding/actions";
import { ForwardingCodes } from "@/components/telephony/forwarding-codes";
import { RequestNumberForm } from "@/components/telephony/request-number";
import { TrustedCallerCard } from "@/components/telephony/trusted-caller-card";
import { Button } from "@/components/ui/button";
import type { Forwarding, PhoneNumberList } from "@/lib/telephony/types";
import { StepFooter } from "./step-footer";

function SoonBadge({ label }: { label: string }) {
  return (
    <span className="inline-flex h-6 shrink-0 items-center rounded-full bg-sky-100 px-2.5 text-xs font-medium whitespace-nowrap text-sky-ink">
      {label}
    </span>
  );
}

function CardHead({ icon: Icon, title, description, badge }: { icon: LucideIcon; title: string; description: string; badge?: string }) {
  return (
    <div className="flex items-start gap-4">
      <span aria-hidden className="inline-flex size-11 shrink-0 items-center justify-center rounded-full bg-brand-50 text-brand-700">
        <Icon className="size-5" strokeWidth={1.75} />
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <h2 className="text-lg leading-[26px] font-semibold">{title}</h2>
          {badge && <SoonBadge label={badge} />}
        </div>
        <p className="mt-0.5 text-text-muted">{description}</p>
      </div>
    </div>
  );
}

export function GoLiveStep({
  employeeName,
  numbers,
  forwarding,
  defaultCity,
}: {
  employeeName: string;
  numbers: PhoneNumberList | null;
  forwarding: Forwarding | null;
  defaultCity: string;
}) {
  const t = useTranslations("onboarding");
  const tl = useTranslations("onboarding.live");
  const tc = useTranslations("connect");
  const [error, setError] = useState<StepErrorKey | null>(null);
  const [pending, startTransition] = useTransition();
  const live = numbers?.items.find((n) => n.id === forwarding?.phone_number_id) ?? null;
  const first = numbers?.items[0] ?? null;

  return (
    <div className="flex flex-col gap-4">
      <section className="rounded-xl border bg-card p-5 shadow-xs md:p-6">
        <CardHead icon={PhoneForwarded} title={tl("forwardTitle")} description={tl("forwardDesc", { name: employeeName })} />
        <div className="mt-5">
          <ForwardingCodes codes={forwarding?.operators ?? null} numberId={live?.id ?? null} testedAt={live?.forwarding_tested_at ?? null} />
        </div>
      </section>

      {numbers ? (
        <section className="rounded-xl border bg-card p-5 shadow-xs md:p-6">
          <CardHead icon={Hash} title={tl("numberTitle")} description={tl("numberDesc")} />
          {numbers.simulated && <p className="mt-4 rounded-lg bg-sky-100 px-4 py-3 text-sm leading-5 text-sky-ink">{tc("simulated")}</p>}
          {first ? (
            <div className="mt-4">
              <TrustedCallerCard number={first} businessName={numbers.business_name} />
            </div>
          ) : (
            <RequestNumberForm defaultCity={defaultCity} />
          )}
        </section>
      ) : (
        <section className="rounded-xl border border-dashed bg-card/60 p-5 md:p-6">
          <CardHead icon={Hash} title={tl("numberTitle")} description={tl("numberDesc")} badge={tl("comingSoon")} />
        </section>
      )}
      <section className="rounded-xl border border-dashed bg-card/60 p-5 md:p-6">
        <CardHead icon={Plug} title={tl("leadsTitle")} description={tl("leadsDesc")} badge={tl("comingSoon")} />
      </section>

      {error && (
        <p role="alert" className="rounded-lg bg-danger/10 px-4 py-3 text-sm leading-5 font-medium text-danger-fg">
          {t(`errors.${error}`)}
        </p>
      )}

      <StepFooter backHref="/onboarding?step=test_call">
        <Button
          size="lg"
          className="w-full md:w-auto md:min-w-48"
          disabled={pending}
          aria-busy={pending}
          onClick={() =>
            startTransition(async () => {
              const result = await finishOnboarding();
              if (result && !result.ok) setError(result.error);
            })
          }
        >
          {pending ? t("saving") : tl("finish")}
        </Button>
      </StepFooter>
    </div>
  );
}
