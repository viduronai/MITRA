"use client";

import { Check, Gift } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useId, useState, useTransition } from "react";
import { toast } from "sonner";
import { confirmTopUp, topUp, type BillingErrorKey } from "@/app/(app)/more/billing/actions";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { formatPaise, nextSlab, PRESET_TOPUPS_RUPEES, topupPreview } from "@/lib/billing/money";
import type { Topup, TopupRules } from "@/lib/billing/types";
import { cn } from "@/lib/utils";

interface RazorpayHandlerArgs {
  razorpay_payment_id: string;
  razorpay_signature: string;
}
declare global {
  interface Window {
    Razorpay?: new (options: Record<string, unknown>) => { open(): void };
  }
}

const CHECKOUT_JS = "https://checkout.razorpay.com/v1/checkout.js";

function loadCheckout(): Promise<boolean> {
  if (window.Razorpay) return Promise.resolve(true);
  return new Promise((resolve) => {
    const script = document.createElement("script");
    script.src = CHECKOUT_JS;
    script.onload = () => resolve(true);
    script.onerror = () => resolve(false);
    document.body.appendChild(script);
  });
}

export function TopupCard({ rules, businessName }: { rules: TopupRules; businessName: string }) {
  const t = useTranslations("billing");
  const locale = useLocale();
  const inputId = useId();
  const [rupees, setRupees] = useState<number>(2_000);
  const [custom, setCustom] = useState("");
  const [error, setError] = useState<BillingErrorKey | null>(null);
  const [pending, startTransition] = useTransition();

  const amount = rupees * 100;
  const tooSmall = amount < rules.min_paise;
  const preview = topupPreview(amount, rules.bonus_slabs, rules.gst_rate_pct);
  const upsell = nextSlab(amount, rules.bonus_slabs);
  const money = (paise: number) => formatPaise(paise, locale);

  const credited = (order: Topup) => {
    toast.success(t("topupDone", { amount: money(order.amount_paise + order.bonus_paise) }));
  };

  const openCheckout = async (order: Topup) => {
    const checkout = order.checkout;
    if (!checkout || !(await loadCheckout()) || !window.Razorpay) {
      setError("unreachable");
      return;
    }
    toast.message(t("topupPending"));
    new window.Razorpay({
      key: checkout.key_id,
      order_id: checkout.order_id,
      amount: checkout.amount,
      currency: checkout.currency,
      name: "Mitra",
      description: businessName,
      handler: (response: RazorpayHandlerArgs) => {
        startTransition(async () => {
          const result = await confirmTopUp(order.id, response.razorpay_payment_id, response.razorpay_signature);
          if (result.ok) credited(result.data);
          else setError(result.error);
        });
      },
    }).open();
  };

  const submit = () => {
    if (tooSmall || pending) return;
    setError(null);
    const key = crypto.randomUUID();
    startTransition(async () => {
      const result = await topUp(rupees, key);
      if (!result.ok) return setError(result.error);
      if (result.data.status === "paid") credited(result.data);
      else await openCheckout(result.data);
    });
  };

  return (
    <section aria-labelledby="topup-title" className="flex flex-col rounded-xl border bg-card p-5 shadow-xs md:p-6">
      <h2 id="topup-title" className="text-lg leading-[26px] font-semibold md:text-xl">
        {t("topupTitle")}
      </h2>
      <p className="mt-1 text-sm text-text-muted">{t("topupHint", { min: money(rules.min_paise) })}</p>

      <div role="group" aria-label={t("topupTitle")} className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
        {PRESET_TOPUPS_RUPEES.map((value) => {
          const selected = custom === "" && rupees === value;
          const pct = topupPreview(value * 100, rules.bonus_slabs, rules.gst_rate_pct).pct;
          return (
            <button
              key={value}
              type="button"
              aria-pressed={selected}
              onClick={() => {
                setCustom("");
                setRupees(value);
              }}
              className={cn(
                "focus-ring flex min-h-14 flex-col items-center justify-center rounded-lg border px-2 py-2 font-semibold tabular-nums transition-colors motion-fast",
                selected ? "border-brand-500 bg-brand-50 text-brand-700" : "bg-surface hover:bg-surface-2",
              )}
            >
              {money(value * 100)}
              {pct > 0 && <span className="text-xs font-medium text-success-fg">{t("bonusBadge", { pct })}</span>}
            </button>
          );
        })}
      </div>

      <div className="mt-3">
        <Label htmlFor={inputId}>{t("customAmount")}</Label>
        <Input
          id={inputId}
          inputMode="numeric"
          className="mt-1.5"
          placeholder="5000"
          value={custom}
          aria-invalid={custom !== "" && tooSmall}
          aria-describedby={`${inputId}-hint`}
          onChange={(event) => {
            const digits = event.target.value.replace(/\D/g, "").slice(0, 7);
            setCustom(digits);
            setRupees(digits ? Number(digits) : 2_000);
          }}
        />
        <p id={`${inputId}-hint`} className={cn("mt-1 text-[13px]", tooSmall ? "text-danger-fg" : "text-text-muted")}>
          {tooSmall ? t("minTopup", { min: money(rules.min_paise) }) : upsell ? t("nextBonus", { amount: money(upsell.min_paise - amount), pct: upsell.pct }) : " "}
        </p>
      </div>

      {!tooSmall && (
        <dl className="mt-3 grid grid-cols-2 gap-3 rounded-lg bg-surface-2 p-4 text-sm">
          <div>
            <dt className="text-text-muted">{t("youPay")}</dt>
            <dd className="mt-0.5 text-lg font-semibold tabular-nums">{money(preview.total)}</dd>
            <dd className="text-[13px] text-text-muted">{t("inclGst", { pct: rules.gst_rate_pct })}</dd>
          </div>
          <div>
            <dt className="text-text-muted">{t("youGet")}</dt>
            <dd className="mt-0.5 text-lg font-semibold tabular-nums">{money(preview.credits)}</dd>
            {preview.pct > 0 && (
              <dd className="inline-flex items-center gap-1 text-[13px] font-medium text-success-fg">
                <Gift className="size-3.5" aria-hidden /> {t("bonusBadge", { pct: preview.pct })}
              </dd>
            )}
          </div>
        </dl>
      )}

      {error && (
        <p role="alert" className="mt-3 text-sm text-danger-fg">
          {t(`errors.${error}`)}
        </p>
      )}
      <Button className="mt-4 w-full" disabled={tooSmall || pending} onClick={submit}>
        {pending ? <span className="animate-pulse">…</span> : t("topupCta", { amount: money(preview.total) })}
      </Button>

      <details className="mt-4 text-sm">
        <summary className="cursor-pointer font-medium text-text-muted">{t("bonusTable")}</summary>
        <ul className="mt-2 space-y-1">
          {rules.bonus_slabs.map((slab) => (
            <li key={slab.min_paise} className="flex items-center justify-between gap-3">
              <span>{t("bonusRow", { amount: money(slab.min_paise) })}</span>
              <span className="inline-flex items-center gap-1 font-medium text-success-fg">
                <Check className="size-3.5" aria-hidden /> {t("bonusBadge", { pct: slab.pct })}
              </span>
            </li>
          ))}
        </ul>
      </details>
    </section>
  );
}
