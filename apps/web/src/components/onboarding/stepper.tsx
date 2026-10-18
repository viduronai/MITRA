import { Check } from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import type { OnboardingStepKey } from "@/lib/api/types";
import { ONBOARDING_STEPS } from "@/lib/onboarding";
import { cn } from "@/lib/utils";

interface StepperProps {
  current: OnboardingStepKey;
  done: Partial<Record<OnboardingStepKey, boolean>>;
  /** Steps the owner may jump back to. */
  reachable: Partial<Record<OnboardingStepKey, boolean>>;
}

/** "STEP 2 OF 6" + bar on mobile; labelled steps on desktop. */
export function Stepper({ current, done, reachable }: StepperProps) {
  const t = useTranslations("onboarding");
  const index = ONBOARDING_STEPS.indexOf(current);
  const total = ONBOARDING_STEPS.length;

  return (
    <nav aria-label={t("progressLabel")} className="mb-8 md:mb-10">
      <div className="flex items-center justify-between gap-3 md:hidden">
        <p className="eyebrow text-text-muted">{t("stepOf", { current: index + 1, total })}</p>
        <p className="text-sm font-medium text-text-muted">{t(`steps.${current}`)}</p>
      </div>
      <div className="mt-3 flex gap-1.5 md:hidden" aria-hidden>
        {ONBOARDING_STEPS.map((step, i) => (
          <span
            key={step}
            className={cn("h-1.5 flex-1 rounded-full bg-surface-2", (i < index || done[step]) && "bg-brand-600/50", i === index && "bg-brand-600")}
          />
        ))}
      </div>

      <ol className="hidden items-center gap-2 md:flex">
        {ONBOARDING_STEPS.map((step, i) => {
          const isCurrent = step === current;
          const isDone = Boolean(done[step]) && !isCurrent;
          const label = (
            <>
              <span
                aria-hidden
                className={cn(
                  "inline-flex size-7 shrink-0 items-center justify-center rounded-full text-[13px] font-semibold tabular-nums",
                  isCurrent && "bg-brand-600 text-on-brand",
                  isDone && "bg-success/12 text-success-fg",
                  !isCurrent && !isDone && "border-2 border-border text-text-muted",
                )}
              >
                {isDone ? <Check className="size-4" strokeWidth={2.5} /> : i + 1}
              </span>
              <span
                className={cn("text-sm font-medium whitespace-nowrap", isCurrent ? "text-foreground" : "sr-only text-text-muted lg:not-sr-only lg:whitespace-nowrap")}
              >
                {t(`steps.${step}`)}
              </span>
            </>
          );
          return (
            <li key={step} className="flex min-w-0 flex-1 items-center gap-2 last:flex-none">
              {reachable[step] && !isCurrent ? (
                <Link href={`/onboarding?step=${step}`} className="focus-ring flex h-11 items-center gap-2 rounded-lg pr-1 hover:text-foreground">
                  {label}
                </Link>
              ) : (
                <span className="flex h-11 items-center gap-2" aria-current={isCurrent ? "step" : undefined}>
                  {label}
                </span>
              )}
              {i < total - 1 && <span aria-hidden className="h-px min-w-3 flex-1 bg-border" />}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

/** Title block for a step: H1 and a one-line subtitle. */
export function StepHeader({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div className="mb-6 md:mb-8">
      <h1 className="text-[28px] leading-[34px] font-semibold tracking-tight md:text-4xl md:leading-[42px]">{title}</h1>
      {subtitle && <p className="mt-2 max-w-2xl text-[17px] leading-[26px] text-text-muted">{subtitle}</p>}
    </div>
  );
}
