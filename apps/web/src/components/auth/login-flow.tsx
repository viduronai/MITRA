"use client";

import { ArrowLeft, FlaskConical, ShieldCheck } from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect, useId, useState, useTransition } from "react";
import { toast } from "sonner";
import { requestOtp, verifyOtp, type AuthErrorKey } from "@/app/login/actions";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";
import { OtpInput } from "./otp-input";

type Stage = { name: "phone" } | { name: "otp"; requestId: string; devCode?: string };

function formatPhone(digits: string): string {
  return `+91 ${digits.slice(0, 5)} ${digits.slice(5)}`;
}

/** Phone number → 6-digit code (docs/07 §3.1). The session cookie is set server-side. */
export function LoginFlow({ signedOut }: { signedOut?: boolean }) {
  const t = useTranslations("auth");
  const phoneId = useId();
  const hintId = useId();
  const errorId = useId();
  const [stage, setStage] = useState<Stage>({ name: "phone" });
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [error, setError] = useState<AuthErrorKey | null>(null);
  const [resendAt, setResendAt] = useState(0);
  const [now, setNow] = useState(() => Date.now());
  const [pending, startTransition] = useTransition();

  const secondsLeft = Math.max(0, Math.ceil((resendAt - now) / 1000));
  useEffect(() => {
    if (stage.name !== "otp" || secondsLeft === 0) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [stage.name, secondsLeft]);

  function sendCode(isResend = false) {
    setError(null);
    startTransition(async () => {
      const result = await requestOtp(phone);
      if (!result.ok) {
        setError(result.error);
        return;
      }
      setCode("");
      setStage({ name: "otp", requestId: result.requestId, devCode: result.devCode });
      setNow(Date.now());
      setResendAt(Date.now() + result.resendIn * 1000);
      if (isResend) toast.success(t("resent"));
    });
  }

  function submitCode(value = code) {
    if (stage.name !== "otp") return;
    const digits = value.replace(/\D/g, "");
    setError(null);
    startTransition(async () => {
      // Resolves only on failure; success redirects on the server.
      const result = await verifyOtp(stage.requestId, digits);
      if (result && !result.ok) {
        setError(result.error);
        if (result.error === "codeWrong") setCode("");
      }
    });
  }

  const errorText = error ? t(`errors.${error}`) : null;

  if (stage.name === "phone") {
    return (
      <form
        className="flex flex-col gap-6"
        onSubmit={(event) => {
          event.preventDefault();
          sendCode();
        }}
        noValidate
      >
        <div>
          <h1 className="text-[28px] leading-[34px] font-semibold tracking-tight md:text-4xl md:leading-[42px]">{t("title")}</h1>
          <p className="mt-2 text-text-muted">{t("subtitle")}</p>
        </div>
        {signedOut && (
          <p role="status" className="rounded-lg bg-info/12 px-4 py-3 text-sm leading-5 text-info-fg">
            {t("signedOut")}
          </p>
        )}
        <div className="flex flex-col gap-2">
          <Label htmlFor={phoneId}>{t("phoneLabel")}</Label>
          <div
            className={cn(
              "flex h-14 items-center rounded-lg border border-input bg-surface shadow-xs transition-[border-color] motion-fast focus-within:border-ring has-focus-visible:outline-2 has-focus-visible:outline-offset-2 has-focus-visible:outline-ring",
              error && "border-danger",
            )}
          >
            <span className="flex h-full items-center border-r px-4 text-lg font-medium text-text-muted tabular-nums">+91</span>
            <input
              id={phoneId}
              type="tel"
              inputMode="numeric"
              autoComplete="tel-national"
              maxLength={10}
              placeholder="98765 43210"
              value={phone}
              onChange={(event) => setPhone(event.target.value.replace(/\D/g, "").slice(0, 10))}
              aria-invalid={error ? true : undefined}
              aria-describedby={error ? errorId : hintId}
              className="h-full min-w-0 flex-1 bg-transparent px-4 text-lg tracking-wide tabular-nums outline-none placeholder:text-text-subtle"
              autoFocus
            />
          </div>
          <p id={hintId} className="text-sm leading-5 text-text-muted">
            {t("phoneHint")}
          </p>
          {errorText && (
            <p id={errorId} role="alert" className="text-sm leading-5 font-medium text-danger-fg">
              {errorText}
            </p>
          )}
        </div>
        <Button type="submit" size="lg" className="w-full" disabled={pending} aria-busy={pending}>
          {pending ? t("sending") : t("sendCode")}
        </Button>
        <p className="flex items-center justify-center gap-2 text-sm leading-5 text-text-muted">
          <ShieldCheck className="size-4" aria-hidden />
          {t("trust")}
        </p>
      </form>
    );
  }

  return (
    <form
      className="flex flex-col gap-6"
      onSubmit={(event) => {
        event.preventDefault();
        submitCode();
      }}
      noValidate
    >
      <div>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="-ml-3 text-text-muted"
          onClick={() => {
            setStage({ name: "phone" });
            setError(null);
          }}
        >
          <ArrowLeft aria-hidden />
          {t("changeNumber")}
        </Button>
        <h1 className="mt-3 text-[28px] leading-[34px] font-semibold tracking-tight md:text-4xl md:leading-[42px]">{t("otpTitle")}</h1>
        <p className="mt-2 text-text-muted">{t("otpSubtitle", { phone: formatPhone(phone) })}</p>
      </div>

      {stage.devCode && (
        // Local development only: the API returns dev_code when it runs with env=local.
        <p className="flex items-center gap-2 rounded-lg border border-dashed border-warning/60 bg-warning/10 px-4 py-2.5 text-sm leading-5 text-warning-fg">
          <FlaskConical className="size-4 shrink-0" aria-hidden />
          <span>{t("devHint", { code: stage.devCode })}</span>
        </p>
      )}

      <div className="flex flex-col gap-2">
        <OtpInput
          value={code}
          onChange={setCode}
          onComplete={submitCode}
          invalid={Boolean(error)}
          disabled={pending}
          describedBy={error ? errorId : undefined}
          autoFocus
        />
        {errorText && (
          <p id={errorId} role="alert" className="text-sm leading-5 font-medium text-danger-fg">
            {errorText}
          </p>
        )}
      </div>

      <Button type="submit" size="lg" className="w-full" disabled={pending} aria-busy={pending}>
        {pending ? t("checking") : t("verify")}
      </Button>

      <div className="flex justify-center">
        {secondsLeft > 0 ? (
          <p className="text-sm leading-5 text-text-muted tabular-nums">
            {t("resendIn", { seconds: secondsLeft })}
          </p>
        ) : (
          <Button type="button" variant="link" size="sm" onClick={() => sendCode(true)} disabled={pending}>
            {t("resend")}
          </Button>
        )}
      </div>
    </form>
  );
}
