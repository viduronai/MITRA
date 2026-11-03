"use client";

import { Copy } from "lucide-react";
import { useTranslations } from "next-intl";
import { useTransition } from "react";
import { toast } from "sonner";
import { actOnPayment } from "@/app/(app)/payments/actions";
import { Button } from "@/components/ui/button";
import type { PaymentAction, PaymentStatus } from "@/lib/payments/types";

interface PaymentActionsProps {
  id: string;
  status: PaymentStatus;
  link: string | null;
  /** UPI-ID mode: no automatic confirmation, so "Mark paid" is the main action. */
  manual: boolean;
}

/** Resend / mark paid / cancel / copy link on one payment request. */
export function PaymentActions({ id, status, link, manual }: PaymentActionsProps) {
  const t = useTranslations("payments");
  const [pending, startTransition] = useTransition();
  const open = status === "sent" || status === "failed";

  const act = (action: PaymentAction, done: string) =>
    startTransition(async () => {
      const result = await actOnPayment(id, action);
      if (result.ok) toast.success(done);
      else toast.error(t(`errors.${result.error}`));
    });

  if (!open && status !== "expired" && status !== "awaiting_approval") return null;
  return (
    <div className="flex flex-wrap gap-2">
      {open && (
        <Button size="xs" variant="secondary" disabled={pending} onClick={() => act("resend", t("resent"))}>
          {t("resend")}
        </Button>
      )}
      {(open || status === "expired") && (
        <Button
          size="xs"
          variant={manual ? "primary" : "secondary"}
          disabled={pending}
          onClick={() => {
            if (window.confirm(t("markPaidConfirm"))) act("mark-paid", t("markedPaid"));
          }}
        >
          {t("markPaid")}
        </Button>
      )}
      {link && open && (
        <Button
          size="xs"
          variant="ghost"
          onClick={() => {
            void navigator.clipboard?.writeText(link).then(() => toast.success(t("copied")));
          }}
        >
          <Copy aria-hidden />
          {t("copy")}
        </Button>
      )}
      {(open || status === "awaiting_approval") && (
        <Button
          size="xs"
          variant="ghost"
          disabled={pending}
          onClick={() => {
            if (window.confirm(t("cancelConfirm"))) act("cancel", t("cancelled"));
          }}
        >
          {t("cancel")}
        </Button>
      )}
    </div>
  );
}
