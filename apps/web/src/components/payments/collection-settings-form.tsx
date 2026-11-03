"use client";

import { Copy, Info } from "lucide-react";
import { useTranslations } from "next-intl";
import { useId, useState, useTransition } from "react";
import { toast } from "sonner";
import { saveCollectionSettings, type PaymentsErrorKey } from "@/app/(app)/payments/actions";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { CollectionMode, CollectionSettings } from "@/lib/payments/types";
import { cn } from "@/lib/utils";

const MODES: CollectionMode[] = ["razorpay", "upi", "none"];

/** How the business collects: its own Razorpay account, a plain UPI ID, or off. */
export function CollectionSettingsForm({ settings }: { settings: CollectionSettings }) {
  const t = useTranslations("payments.settings");
  const tErr = useTranslations("payments.errors");
  const id = useId();
  const [mode, setMode] = useState<CollectionMode>(settings.mode);
  const [keyId, setKeyId] = useState("");
  const [keySecret, setKeySecret] = useState("");
  const [hookSecret, setHookSecret] = useState("");
  const [vpa, setVpa] = useState(settings.upi_vpa ?? "");
  const [payee, setPayee] = useState(settings.payee_name ?? "");
  const [reminders, setReminders] = useState(settings.reminders_enabled);
  const [expiry, setExpiry] = useState(String(settings.link_expiry_days));
  const [lender, setLender] = useState(settings.is_lender);
  const [error, setError] = useState<PaymentsErrorKey | null>(null);
  const [pending, startTransition] = useTransition();
  const connected = settings.mode === "razorpay" && settings.has_key_secret;

  return (
    <form
      className="flex flex-col gap-5"
      onSubmit={(event) => {
        event.preventDefault();
        setError(null);
        startTransition(async () => {
          const result = await saveCollectionSettings({
            mode,
            // A blank key id keeps the connected account (its secrets stay stored).
            keyId: mode === "razorpay" ? keyId || undefined : undefined,
            keySecret: keySecret || undefined,
            webhookSecret: hookSecret || undefined,
            vpa,
            payeeName: payee,
            reminders,
            expiryDays: Number(expiry) || undefined,
            lender,
          });
          if (result.ok) {
            toast.success(t("saved"));
            setKeySecret("");
            setHookSecret("");
          } else setError(result.error);
        });
      }}
    >
      <fieldset>
        <legend className="font-semibold">{t("howTitle")}</legend>
        <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-3">
          {MODES.map((m) => (
            <label
              key={m}
              className={cn(
                "focus-within:ring-ring flex cursor-pointer flex-col gap-1 rounded-lg border p-3 focus-within:ring-2",
                mode === m ? "border-brand-500 bg-brand-50 dark:bg-surface-2" : "bg-surface hover:bg-surface-2",
              )}
            >
              <span className="flex items-center gap-2 font-medium">
                <input type="radio" name={`${id}-mode`} value={m} checked={mode === m} onChange={() => setMode(m)} />
                {t(`modes.${m}`)}
              </span>
              <span className="text-[13px] leading-5 text-text-muted">{t(`modeHints.${m}`)}</span>
            </label>
          ))}
        </div>
      </fieldset>

      {mode === "razorpay" && (
        <div className="flex flex-col gap-4">
          {settings.simulated && <p className="rounded-lg bg-info/12 p-3 text-sm text-info-fg">{t("simulated")}</p>}
          <div>
            <Label htmlFor={`${id}-key`}>{t("keyId")}</Label>
            <Input
              id={`${id}-key`}
              autoComplete="off"
              className="mt-1.5"
              placeholder={settings.razorpay_key_id ?? "rzp_live_…"}
              value={keyId}
              onChange={(event) => setKeyId(event.target.value.trim().slice(0, 64))}
              required={!connected}
            />
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <Label htmlFor={`${id}-secret`}>{t("keySecret")}</Label>
              <Input
                id={`${id}-secret`}
                type="password"
                autoComplete="new-password"
                className="mt-1.5"
                placeholder={settings.has_key_secret ? t("savedSecret") : ""}
                value={keySecret}
                onChange={(event) => setKeySecret(event.target.value.slice(0, 128))}
              />
            </div>
            <div>
              <Label htmlFor={`${id}-hook`}>{t("webhookSecret")}</Label>
              <Input
                id={`${id}-hook`}
                type="password"
                autoComplete="new-password"
                className="mt-1.5"
                placeholder={settings.has_webhook_secret ? t("savedSecret") : ""}
                value={hookSecret}
                onChange={(event) => setHookSecret(event.target.value.slice(0, 128))}
              />
            </div>
          </div>
          <div>
            <p className="text-sm font-medium">{t("webhookUrl")}</p>
            <div className="mt-1.5 flex items-center gap-2">
              <code className="min-w-0 flex-1 truncate rounded-md bg-surface-2 px-3 py-2 text-[13px]">{settings.webhook_url}</code>
              <Button
                type="button"
                size="icon-sm"
                variant="ghost"
                aria-label={t("copyUrl")}
                onClick={() => void navigator.clipboard?.writeText(settings.webhook_url).then(() => toast.success(t("copied")))}
              >
                <Copy aria-hidden />
              </Button>
            </div>
            <p className="mt-1.5 text-[13px] leading-5 text-text-muted">{t("webhookHelp")}</p>
          </div>
        </div>
      )}

      {mode === "upi" && (
        <div className="flex flex-col gap-4">
          <p className="flex gap-2 rounded-lg bg-warning/12 p-3 text-sm text-warning-fg">
            <Info className="mt-0.5 size-4 shrink-0" aria-hidden />
            {t("upiWarning")}
          </p>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <Label htmlFor={`${id}-vpa`}>{t("vpa")}</Label>
              <Input
                id={`${id}-vpa`}
                autoComplete="off"
                className="mt-1.5"
                placeholder="yourshop@okhdfcbank"
                value={vpa}
                onChange={(event) => setVpa(event.target.value.trim().slice(0, 100))}
                required
              />
            </div>
            <div>
              <Label htmlFor={`${id}-payee`}>{t("payee")}</Label>
              <Input id={`${id}-payee`} className="mt-1.5" value={payee} onChange={(event) => setPayee(event.target.value.slice(0, 100))} />
            </div>
          </div>
        </div>
      )}

      {mode !== "none" && (
        <>
          <label className="flex items-start gap-3">
            <input type="checkbox" className="mt-1" checked={reminders} onChange={(event) => setReminders(event.target.checked)} />
            <span>
              <span className="font-medium">{t("reminders")}</span>
              <span className="block text-[13px] leading-5 text-text-muted">{t("remindersHint")}</span>
            </span>
          </label>
          <div className="max-w-xs">
            <Label htmlFor={`${id}-expiry`}>{t("expiry")}</Label>
            <Input
              id={`${id}-expiry`}
              inputMode="numeric"
              className="mt-1.5 tabular-nums"
              value={expiry}
              onChange={(event) => setExpiry(event.target.value.replace(/\D/g, "").slice(0, 3))}
            />
            <p className="mt-1 text-[13px] leading-5 text-text-muted">{t("expiryHint")}</p>
          </div>
          <label className="flex items-start gap-3">
            <input type="checkbox" className="mt-1" checked={lender} onChange={(event) => setLender(event.target.checked)} />
            <span>
              <span className="font-medium">{t("lender")}</span>
              <span className="block text-[13px] leading-5 text-text-muted">{t("lenderHint")}</span>
            </span>
          </label>
        </>
      )}

      {error && (
        <p role="alert" className="text-sm text-danger-fg">
          {tErr(error)}
        </p>
      )}
      <div>
        <Button type="submit" disabled={pending}>
          {t("save")}
        </Button>
      </div>
    </form>
  );
}
