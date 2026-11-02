"use client";

import { Check, Copy } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/** A labelled value (URL, secret, code snippet) with a Copy button. */
export function CopyBlock({ label, value, multiline = false, className }: { label: string; value: string; multiline?: boolean; className?: string }) {
  const t = useTranslations("connect");
  const [copied, setCopied] = useState(false);

  return (
    <div className={cn("rounded-lg border bg-surface-2/60 p-3", className)}>
      <div className="flex items-center gap-3">
        <p className="min-w-0 flex-1 text-sm leading-5 font-medium text-text-muted">{label}</p>
        <Button
          variant="secondary"
          size="xs"
          aria-label={t("copyCode", { label })}
          onClick={async () => {
            try {
              await navigator.clipboard.writeText(value);
              setCopied(true);
              toast.success(t("copied"));
              window.setTimeout(() => setCopied(false), 2000);
            } catch {
              // Clipboard can be blocked; the text stays visible to select by hand.
            }
          }}
        >
          {copied ? <Check aria-hidden /> : <Copy aria-hidden />}
          <span aria-hidden>{copied ? t("copied") : t("copyShort")}</span>
        </Button>
      </div>
      {multiline ? (
        <pre className="mt-2 max-h-64 overflow-auto rounded-md bg-surface p-3 font-mono text-xs leading-5 whitespace-pre">{value}</pre>
      ) : (
        <p className="mt-1 font-mono text-sm leading-6 break-all">{value}</p>
      )}
    </div>
  );
}
