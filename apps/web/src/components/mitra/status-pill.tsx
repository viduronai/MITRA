import { Pause } from "lucide-react";
import { useTranslations } from "next-intl";
import { cn } from "@/lib/utils";

export type EmployeeStatus = "working" | "paused";

export function StatusPill({ status, className }: { status: EmployeeStatus; className?: string }) {
  const t = useTranslations("employee");
  const working = status === "working";

  return (
    <span
      className={cn(
        "inline-flex h-7 items-center gap-1.5 rounded-full px-2.5 text-[13px] leading-5 font-medium",
        working ? "bg-success/12 text-success-fg" : "bg-surface-2 text-text-muted",
        className,
      )}
    >
      {working ? (
        <span className="size-2 rounded-full bg-success" aria-hidden />
      ) : (
        <Pause className="size-3.5" aria-hidden />
      )}
      {t(status)}
    </span>
  );
}
