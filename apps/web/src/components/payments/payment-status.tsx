import { useTranslations } from "next-intl";
import type { PaymentStatus } from "@/lib/payments/types";
import { cn } from "@/lib/utils";

const tones: Record<PaymentStatus, string> = {
  awaiting_approval: "bg-info/12 text-info-fg",
  sent: "bg-warning/12 text-warning-fg",
  paid: "bg-success/12 text-success-fg",
  failed: "bg-danger/12 text-danger-fg",
  expired: "bg-surface-2 text-text-muted",
  cancelled: "bg-surface-2 text-text-muted",
};

export function PaymentStatusPill({ status, className }: { status: PaymentStatus; className?: string }) {
  const t = useTranslations("payments.status");
  return (
    <span className={cn("inline-flex h-6 items-center rounded-full px-2.5 text-[13px] leading-5 font-medium", tones[status], className)}>
      {t(status)}
    </span>
  );
}
