"use client";

import { useLocale, useTranslations } from "next-intl";
import { useId, useState, useTransition } from "react";
import { toast } from "sonner";
import { setAutopay, setMonthlyCap, type BillingErrorKey } from "@/app/(app)/more/billing/actions";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { formatPaise } from "@/lib/billing/money";
import { cn } from "@/lib/utils";

const AUTOPAY_CHOICES_RUPEES = [1_000, 2_000, 5_000, 10_000];

interface SpendControlsProps {
  capPaise: number | null;
  capRemainingPaise: number | null;
  autopayEnabled: boolean;
  autopayAmountPaise: number;
  thresholdPaise: number;
}

/** Monthly spend cap + auto top-up (docs/07 §3.8, BILL-04 / BILL-08). */
export function SpendControls({ capPaise, capRemainingPaise, autopayEnabled, autopayAmountPaise, thresholdPaise }: SpendControlsProps) {
  const t = useTranslations("billing");
  const locale = useLocale();
  const capId = useId();
  const [cap, setCap] = useState(capPaise === null ? "" : String(capPaise / 100));
  const [error, setError] = useState<BillingErrorKey | null>(null);
  const [pending, startTransition] = useTransition();
  const money = (paise: number) => formatPaise(paise, locale);

  const save = (action: () => Promise<{ ok: boolean; error?: BillingErrorKey }>) => {
    setError(null);
    startTransition(async () => {
      const result = await action();
      if (result.ok) toast.success(t("saved"));
      else setError(result.error ?? "generic");
    });
  };

  return (
    <div className="flex flex-col gap-6">
      <section aria-labelledby={`${capId}-title`}>
        <h3 id={`${capId}-title`} className="font-semibold">
          {t("capTitle")}
        </h3>
        <p className="mt-1 text-sm text-text-muted">{t("capHint")}</p>
        <p className="mt-2 text-sm font-medium tabular-nums">
          {capPaise === null
            ? t("capNone")
            : t("capSet", { amount: money(capPaise), remaining: money(capRemainingPaise ?? 0) })}
        </p>
        <form
          className="mt-3 flex flex-wrap items-end gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            const rupees = Number(cap);
            if (!cap || !Number.isInteger(rupees)) return setError("invalid");
            save(() => setMonthlyCap(rupees));
          }}
        >
          <div className="min-w-0 flex-1 basis-40">
            <Label htmlFor={capId}>{t("capInput")}</Label>
            <Input
              id={capId}
              inputMode="numeric"
              className="mt-1.5"
              placeholder="5000"
              value={cap}
              onChange={(event) => setCap(event.target.value.replace(/\D/g, "").slice(0, 7))}
            />
          </div>
          <Button type="submit" variant="secondary" disabled={pending}>
            {t("capSave")}
          </Button>
          {capPaise !== null && (
            <Button
              type="button"
              variant="ghost"
              disabled={pending}
              onClick={() => {
                setCap("");
                save(() => setMonthlyCap(null));
              }}
            >
              {t("capRemove")}
            </Button>
          )}
        </form>
      </section>

      <section aria-labelledby={`${capId}-autopay`} className="border-t pt-5">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h3 id={`${capId}-autopay`} className="font-semibold">
              {t("autopayTitle")}
            </h3>
            <p className="mt-1 text-sm text-text-muted">
              {t("autopayHint", { threshold: money(thresholdPaise), amount: money(autopayAmountPaise) })}
            </p>
          </div>
          <button
            type="button"
            role="switch"
            aria-checked={autopayEnabled}
            aria-labelledby={`${capId}-autopay`}
            disabled={pending}
            onClick={() => save(() => setAutopay(!autopayEnabled))}
            className={cn(
              "focus-ring relative mt-1 inline-flex h-7 w-12 shrink-0 items-center rounded-full transition-colors motion-fast disabled:opacity-60",
              autopayEnabled ? "bg-primary" : "bg-border",
            )}
          >
            <span
              className={cn(
                "inline-block size-5 rounded-full bg-white shadow-xs transition-transform motion-fast",
                autopayEnabled ? "translate-x-6" : "translate-x-1",
              )}
            />
          </button>
        </div>
        {autopayEnabled && (
          <div role="group" aria-label={t("autopayAmount")} className="mt-3 flex flex-wrap gap-2">
            {AUTOPAY_CHOICES_RUPEES.map((rupees) => (
              <button
                key={rupees}
                type="button"
                aria-pressed={autopayAmountPaise === rupees * 100}
                disabled={pending}
                onClick={() => save(() => setAutopay(true, rupees))}
                className={cn(
                  "focus-ring min-h-10 rounded-lg border px-3 text-sm font-medium tabular-nums",
                  autopayAmountPaise === rupees * 100 ? "border-brand-500 bg-brand-50 text-brand-700" : "bg-surface hover:bg-surface-2",
                )}
              >
                {money(rupees * 100)}
              </button>
            ))}
          </div>
        )}
      </section>

      {error && (
        <p role="alert" className="text-sm text-danger-fg">
          {t(`errors.${error}`)}
        </p>
      )}
    </div>
  );
}
