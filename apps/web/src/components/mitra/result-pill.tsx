import {
  CalendarCheck,
  CircleAlert,
  CircleCheck,
  CircleMinus,
  Hourglass,
  PhoneCall,
  PhoneForwarded,
  PhoneMissed,
  Sparkles,
  type LucideIcon,
} from "lucide-react";
import { useTranslations } from "next-intl";
import type { CallResult } from "@/lib/calls";
import { cn } from "@/lib/utils";

const styles: Record<CallResult, { icon: LucideIcon; className: string }> = {
  booked: { icon: CalendarCheck, className: "bg-success/12 text-success-fg" },
  interested: { icon: Sparkles, className: "bg-brand-50 text-brand-700" },
  callBack: { icon: PhoneCall, className: "bg-info/12 text-info-fg" },
  notInterested: { icon: CircleMinus, className: "bg-surface-2 text-text-muted" },
  failed: { icon: CircleAlert, className: "bg-danger/10 text-danger-fg" },
  missed: { icon: PhoneMissed, className: "bg-warning/15 text-warning-fg" },
  transferred: { icon: PhoneForwarded, className: "bg-info/12 text-info-fg" },
  answered: { icon: CircleCheck, className: "bg-surface-2 text-text-muted" },
  processing: { icon: Hourglass, className: "bg-surface-2 text-text-subtle" },
};

/** Call result — always icon + label, never colour alone (docs/06 §3). */
export function ResultPill({ result, className }: { result: CallResult; className?: string }) {
  const t = useTranslations("results");
  const { icon: Icon, className: tone } = styles[result];

  return (
    <span
      className={cn(
        "inline-flex h-7 shrink-0 items-center gap-1.5 rounded-full px-2.5 text-[13px] leading-5 font-medium whitespace-nowrap",
        tone,
        className,
      )}
    >
      <Icon className="size-3.5" aria-hidden strokeWidth={2} />
      {t(result)}
    </span>
  );
}
