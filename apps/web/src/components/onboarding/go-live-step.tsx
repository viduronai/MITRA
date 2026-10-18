"use client";

import { Check, Copy, Hash, PhoneForwarded, Plug, type LucideIcon } from "lucide-react";
import { useTranslations } from "next-intl";
import { useId, useState, useTransition } from "react";
import { toast } from "sonner";
import { finishOnboarding, type StepErrorKey } from "@/app/onboarding/actions";
import { Button } from "@/components/ui/button";
import { FORWARD_CODES, OPERATORS, type ForwardWhen, type Operator } from "@/lib/onboarding";
import { cn } from "@/lib/utils";
import { StepFooter } from "./step-footer";

const WHEN: ForwardWhen[] = ["busy", "noAnswer", "unreachable"];

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

function CopyCode({ code, label }: { code: string; label: string }) {
  const tl = useTranslations("onboarding.live");
  const [copied, setCopied] = useState(false);

  return (
    <div className="flex items-center gap-3 py-2.5">
      <div className="min-w-0 flex-1">
        <p className="text-sm leading-5 text-text-muted">{label}</p>
        <p className="font-mono text-[15px] leading-6 font-medium tracking-wide break-all">{code}</p>
      </div>
      <Button
        variant="secondary"
        size="sm"
        aria-label={tl("copyCode", { label })}
        onClick={async () => {
          try {
            await navigator.clipboard.writeText(code);
            setCopied(true);
            toast.success(tl("copied"));
            window.setTimeout(() => setCopied(false), 2000);
          } catch {
            // Clipboard can be blocked; the code stays visible to type by hand.
          }
        }}
      >
        {copied ? <Check aria-hidden /> : <Copy aria-hidden />}
        <span aria-hidden>{copied ? tl("copied") : tl("copyShort")}</span>
      </Button>
    </div>
  );
}

export function GoLiveStep({ employeeName }: { employeeName: string }) {
  const t = useTranslations("onboarding");
  const tl = useTranslations("onboarding.live");
  const group = useId();
  const [operator, setOperator] = useState<Operator>("jio");
  const [error, setError] = useState<StepErrorKey | null>(null);
  const [pending, startTransition] = useTransition();

  return (
    <div className="flex flex-col gap-4">
      <section className="rounded-xl border bg-card p-5 shadow-xs md:p-6">
        <CardHead icon={PhoneForwarded} title={tl("forwardTitle")} description={tl("forwardDesc", { name: employeeName })} />

        <fieldset className="mt-5">
          <legend className="mb-2 text-sm leading-5 font-medium">{tl("network")}</legend>
          <div className="grid grid-cols-4 gap-1 rounded-xl bg-surface-2 p-1">
            {OPERATORS.map(({ id, name }) => (
              <label
                key={id}
                className={cn(
                  "flex h-11 cursor-pointer items-center justify-center rounded-lg text-sm font-medium text-text-muted transition-colors motion-fast has-focus-visible:outline-2 has-focus-visible:outline-offset-2 has-focus-visible:outline-ring",
                  operator === id && "bg-surface text-foreground shadow-xs",
                )}
              >
                <input type="radio" name={group} value={id} checked={operator === id} onChange={() => setOperator(id)} className="sr-only" />
                {name}
              </label>
            ))}
          </div>
        </fieldset>

        <div className="mt-3 divide-y">
          {WHEN.map((when) => (
            <CopyCode key={when} code={FORWARD_CODES[operator][when]} label={tl(when)} />
          ))}
        </div>
        <p className="mt-2 text-sm leading-5 text-text-muted">{tl("dialHint")}</p>
        <p className="mt-3 rounded-lg bg-sky-100 px-4 py-3 text-sm leading-5 text-sky-ink">{tl("forwardSoon")}</p>
      </section>

      <section className="rounded-xl border border-dashed bg-card/60 p-5 md:p-6">
        <CardHead icon={Hash} title={tl("numberTitle")} description={tl("numberDesc")} badge={tl("comingSoon")} />
      </section>
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
