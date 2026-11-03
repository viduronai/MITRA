"use client";

import { Eye, EyeOff, Phone } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState, useTransition } from "react";
import { toast } from "sonner";
import { revealPhone } from "@/app/(app)/customers/actions";
import { Button } from "@/components/ui/button";

/**
 * Masked by default; "Show number" asks core for the full number (owners and managers only).
 * Core logs every view (who, when). The number lives only in this component's state.
 */
export function RevealPhone({ customerId, masked, hasPhone }: { customerId: string; masked: string; hasPhone: boolean }) {
  const t = useTranslations("customer");
  const [phone, setPhone] = useState<string | null>(null);
  const [pending, start] = useTransition();

  if (phone) {
    return (
      <span className="inline-flex flex-wrap items-center gap-2">
        <a href={`tel:${phone}`} className="focus-ring inline-flex items-center gap-1 rounded-md font-medium tabular-nums text-brand-600">
          <Phone className="size-4" aria-hidden />
          {phone.replace(/^\+91(\d{5})(\d{5})$/, "+91 $1 $2")}
        </a>
        <Button variant="ghost" size="sm" onClick={() => setPhone(null)}>
          <EyeOff aria-hidden /> {t("hideNumber")}
        </Button>
      </span>
    );
  }
  return (
    <span className="inline-flex flex-wrap items-center gap-2">
      <span className="tabular-nums">{masked}</span>
      {hasPhone && (
        <Button
          variant="ghost"
          size="sm"
          disabled={pending}
          onClick={() =>
            start(async () => {
              const result = await revealPhone(customerId);
              if (result.ok) setPhone(result.phone);
              else toast.error(t(`revealErrors.${result.error}`));
            })
          }
        >
          <Eye aria-hidden /> {t("showNumber")}
        </Button>
      )}
    </span>
  );
}
