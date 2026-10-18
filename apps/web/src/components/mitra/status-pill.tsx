import { Hourglass, Pause } from "lucide-react";
import { useTranslations } from "next-intl";
import { cn } from "@/lib/utils";

export type EmployeeStatus = "working" | "paused" | "training";

const tones: Record<EmployeeStatus, string> = {
  working: "bg-success/12 text-success-fg",
  paused: "bg-surface-2 text-text-muted",
  training: "bg-info/12 text-info-fg",
};

export function StatusPill({ status, className }: { status: EmployeeStatus; className?: string }) {
  const t = useTranslations("employee");

  return (
    <span
      className={cn("inline-flex h-7 items-center gap-1.5 rounded-full px-2.5 text-[13px] leading-5 font-medium", tones[status], className)}
    >
      {status === "working" ? (
        <span className="size-2 rounded-full bg-success" aria-hidden />
      ) : status === "paused" ? (
        <Pause className="size-3.5" aria-hidden />
      ) : (
        <Hourglass className="size-3.5" aria-hidden />
      )}
      {t(status)}
    </span>
  );
}
