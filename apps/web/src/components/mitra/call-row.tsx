import { ChevronRight, PhoneIncoming, PhoneOutgoing } from "lucide-react";
import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import { formatTime } from "@/lib/format";
import type { CallDirection, CallResult } from "@/lib/mock-data";
import { cn } from "@/lib/utils";
import { EmployeeAvatar } from "./employee-avatar";
import { ResultPill } from "./result-pill";

export interface CallRowData {
  id: string;
  contact: string;
  direction: CallDirection;
  result: CallResult;
  durationSeconds: number;
  at: Date;
  employeeName: string;
}

interface CallRowProps {
  call: CallRowData;
  /** Tap → call detail. */
  href: string;
  className?: string;
}

/**
 * Contact, employee avatar, result pill, duration and time (docs/06 §8).
 * Render from a Server Component: time formatting must not differ between
 * server and browser.
 */
export function CallRow({ call, href, className }: CallRowProps) {
  const t = useTranslations("call");
  const locale = useLocale();
  const DirectionIcon = call.direction === "incoming" ? PhoneIncoming : PhoneOutgoing;
  const duration = t("duration", {
    minutes: Math.floor(call.durationSeconds / 60),
    seconds: call.durationSeconds % 60,
  });

  return (
    <Link
      href={href}
      aria-label={t("open", { name: call.contact })}
      className={cn(
        "group focus-ring flex min-h-16 items-center gap-3 rounded-lg px-2 py-3 transition-colors motion-fast hover:bg-surface-2 md:gap-4 md:px-3",
        className,
      )}
    >
      <EmployeeAvatar name={call.employeeName} size="sm" />
      <span className="flex min-w-0 flex-1 flex-col">
        <span className="truncate leading-6 font-medium">{call.contact}</span>
        <span className="flex items-center gap-1.5 overflow-hidden text-[13px] leading-5 whitespace-nowrap text-text-muted">
          <DirectionIcon className="size-3.5 shrink-0" aria-hidden />
          <span className="sr-only">{t(call.direction)}, </span>
          <span className="tabular-nums">{formatTime(call.at, locale)}</span>
          <span aria-hidden>·</span>
          <span className="tabular-nums">{duration}</span>
        </span>
      </span>
      <ResultPill result={call.result} />
      <ChevronRight
        className="hidden size-4 shrink-0 text-text-subtle transition-transform motion-fast group-hover:translate-x-0.5 sm:block"
        aria-hidden
      />
    </Link>
  );
}
