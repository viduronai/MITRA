"use client";

import { ShieldCheck } from "lucide-react";
import { useTranslations } from "next-intl";
import { useId } from "react";
import { cn } from "@/lib/utils";

/** The owner's list attestation (docs/08 §8.5). `text` is core's exact wording, which is what
 * gets stored with who ticked it and when. Unticked by default; required to start calling. */
export function ConsentCheck({
  text,
  checked,
  onChange,
  promotional,
  className,
}: {
  text: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  promotional?: boolean;
  className?: string;
}) {
  const t = useTranslations("campaigns.consent");
  const id = useId();
  return (
    <div className={cn("rounded-lg border bg-surface-2 p-3", checked && "border-brand-500 bg-brand-50", className)}>
      <label htmlFor={id} className="flex cursor-pointer items-start gap-3">
        <input
          id={id}
          type="checkbox"
          checked={checked}
          onChange={(e) => onChange(e.target.checked)}
          className="focus-ring mt-0.5 size-5 shrink-0 accent-brand-500"
        />
        <span className="text-sm leading-5 font-medium">{text}</span>
      </label>
      <p className="mt-2 flex items-start gap-1.5 pl-8 text-[13px] leading-5 text-text-muted">
        <ShieldCheck className="mt-0.5 size-3.5 shrink-0" aria-hidden />
        {promotional ? t("promotionalHint") : t("hint")}
      </p>
    </div>
  );
}
