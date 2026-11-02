"use client";

import { Check, Copy, PhoneCall } from "lucide-react";
import { useTranslations } from "next-intl";
import { useId, useState, useTransition } from "react";
import { toast } from "sonner";
import { testForwarding } from "@/app/(app)/more/connect/actions";
import { Button } from "@/components/ui/button";
import { FORWARD_CODES, OPERATORS, type ForwardWhen, type Operator } from "@/lib/onboarding";
import type { OperatorCodes } from "@/lib/telephony/types";
import { cn } from "@/lib/utils";

const WHEN: ForwardWhen[] = ["busy", "noAnswer", "unreachable"];
const API_KEY: Record<ForwardWhen, "busy" | "no_answer" | "unreachable"> = {
  busy: "busy",
  noAnswer: "no_answer",
  unreachable: "unreachable",
};

function CopyCode({ code, label }: { code: string; label: string }) {
  const t = useTranslations("connect");
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
        aria-label={t("copyCode", { label })}
        onClick={async () => {
          try {
            await navigator.clipboard.writeText(code);
            setCopied(true);
            toast.success(t("copied"));
            window.setTimeout(() => setCopied(false), 2000);
          } catch {
            // Clipboard can be blocked; the code stays visible to type by hand.
          }
        }}
      >
        {copied ? <Check aria-hidden /> : <Copy aria-hidden />}
        <span aria-hidden>{copied ? t("copied") : t("copyShort")}</span>
      </Button>
    </div>
  );
}

/**
 * Missed/busy-call forwarding codes per operator (NUM-02). With a live number the codes come
 * from core (the real target number); before that, placeholders show what dialling looks like.
 */
export function ForwardingCodes({
  codes,
  numberId,
  testedAt,
}: {
  codes: OperatorCodes[] | null;
  numberId?: string | null;
  testedAt?: string | null;
}) {
  const t = useTranslations("connect");
  const group = useId();
  const [operator, setOperator] = useState<Operator>("jio");
  const [pending, startTransition] = useTransition();
  const [result, setResult] = useState<string | null>(null);
  const live = codes?.find((c) => c.operator === operator);
  const code = (when: ForwardWhen) => (live ? live[API_KEY[when]] : FORWARD_CODES[operator][when]);

  return (
    <div>
      <fieldset>
        <legend className="mb-2 text-sm leading-5 font-medium">{t("network")}</legend>
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
          <CopyCode key={when} code={code(when)} label={t(when)} />
        ))}
      </div>
      <p className="mt-2 text-sm leading-5 text-text-muted">
        {t("dialHint")} {live && t("cancelHint", { code: live.cancel })}
      </p>
      {!codes && <p className="mt-3 rounded-lg bg-sky-100 px-4 py-3 text-sm leading-5 text-sky-ink">{t("forwardPlaceholder")}</p>}

      {numberId && (
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <Button
            variant="secondary"
            disabled={pending}
            aria-busy={pending}
            onClick={() =>
              startTransition(async () => {
                const res = await testForwarding(numberId);
                if (!res.ok) {
                  toast.error(t(`errors.${res.error}`));
                  return;
                }
                const message = res.data.status === "passed" ? t("testPassed") : t("testPending");
                setResult(res.data.simulated ? `${message} ${t("testSimulated")}` : message);
              })
            }
          >
            <PhoneCall aria-hidden />
            {t("testForwarding")}
          </Button>
          <p role="status" className="text-sm leading-5 text-text-muted">
            {result ?? (testedAt ? t("testedBefore") : "")}
          </p>
        </div>
      )}
    </div>
  );
}
