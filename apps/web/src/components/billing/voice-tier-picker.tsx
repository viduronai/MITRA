"use client";

import { useLocale, useTranslations } from "next-intl";
import { useOptimistic, useState, useTransition } from "react";
import { toast } from "sonner";
import { setVoiceTier, type BillingErrorKey } from "@/app/(app)/more/billing/actions";
import type { VoiceTier } from "@/lib/api/types";
import { formatRate } from "@/lib/format";
import { cn } from "@/lib/utils";

const TIERS: VoiceTier[] = ["smart", "natural", "signature"];

interface VoiceTierPickerProps {
  employeeId: string;
  employeeName: string;
  tier: VoiceTier;
  /** Paise per connected minute, by tier (from the billing summary or GET /v1/catalog/rates). */
  rates: Partial<Record<VoiceTier, number>>;
  /** Current voice's name; a tier change switches to the closest voice in that tier. */
  voiceName?: string | null;
  canEdit?: boolean;
}

/** Per-employee voice tier with ₹/min (BILL-06). Usable on any page: billing or employee detail. */
export function VoiceTierPicker({ employeeId, employeeName, tier, rates, voiceName = null, canEdit = true }: VoiceTierPickerProps) {
  const t = useTranslations("billing");
  const locale = useLocale();
  const [current, setCurrent] = useOptimistic(tier);
  const [voice, setVoice] = useState(voiceName);
  const [error, setError] = useState<BillingErrorKey | null>(null);
  const [pending, startTransition] = useTransition();

  const choose = (next: VoiceTier) => {
    if (next === current || !canEdit) return;
    setError(null);
    startTransition(async () => {
      setCurrent(next);
      const result = await setVoiceTier(employeeId, next);
      if (!result.ok) return setError(result.error);
      if (result.data) setVoice(result.data);
      toast.success(result.data ? t("voiceSwitched", { name: result.data }) : t("saved"));
    });
  };

  return (
    <div>
      <div role="radiogroup" aria-label={t("tierGroup", { name: employeeName })} className="grid grid-cols-1 gap-2 sm:grid-cols-3">
        {TIERS.map((option) => {
          const selected = option === current;
          const rate = rates[option];
          return (
            <button
              key={option}
              type="button"
              role="radio"
              aria-checked={selected}
              disabled={pending || !canEdit}
              onClick={() => choose(option)}
              className={cn(
                "focus-ring flex flex-col items-start rounded-lg border p-3 text-left transition-colors motion-fast disabled:cursor-default",
                selected ? "border-brand-500 bg-brand-50" : "bg-surface hover:bg-surface-2",
              )}
            >
              <span className="flex w-full items-baseline justify-between gap-2">
                <span className={cn("font-semibold", selected && "text-brand-700")}>{t(`tier.${option}`)}</span>
                {rate !== undefined && (
                  <span className="text-sm font-semibold tabular-nums">
                    {t("perMin", { rate: formatRate(rate / 100, locale) })}
                  </span>
                )}
              </span>
              <span className="mt-1 text-[13px] leading-5 text-text-muted">{t(`tierDesc.${option}`)}</span>
            </button>
          );
        })}
      </div>
      {voice && <p className="mt-2 text-[13px] text-text-muted">{t("voiceLabel", { name: voice })}</p>}
      {error && (
        <p role="alert" className="mt-2 text-sm text-danger-fg">
          {t(`errors.${error}`)}
        </p>
      )}
    </div>
  );
}
