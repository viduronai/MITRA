import { Check, Clock3, Pause, PencilLine, X } from "lucide-react";
import { useTranslations } from "next-intl";
import type { CampaignStatus } from "@/lib/campaigns/types";
import { cn } from "@/lib/utils";

const tones: Record<CampaignStatus, string> = {
  draft: "bg-surface-2 text-text-muted",
  pending_approval: "bg-warning/14 text-warning-fg",
  running: "bg-success/12 text-success-fg",
  paused: "bg-warning/14 text-warning-fg",
  completed: "bg-info/12 text-info-fg",
  cancelled: "bg-surface-2 text-text-muted",
};

const icons = { draft: PencilLine, pending_approval: Clock3, paused: Pause, completed: Check, cancelled: X };

export function CampaignStatusPill({ status, className }: { status: CampaignStatus; className?: string }) {
  const t = useTranslations("campaigns.status");
  const Icon = status === "running" ? null : icons[status];
  return (
    <span
      className={cn(
        "inline-flex h-7 shrink-0 items-center gap-1.5 rounded-full px-2.5 text-[13px] leading-5 font-medium",
        tones[status],
        className,
      )}
    >
      {Icon ? <Icon className="size-3.5" aria-hidden /> : <span className="size-2 animate-pulse rounded-full bg-success" aria-hidden />}
      {t(status)}
    </span>
  );
}
