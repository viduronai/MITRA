import { ChevronRight, Globe, Phone, PhoneIncoming, PhoneOutgoing } from "lucide-react";
import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import { formatTime } from "@/lib/format";
import type { CallDirection, CallResult } from "@/lib/calls";
import { cn } from "@/lib/utils";
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

/** Caller initials ("Anjali Sharma" → "AS"); null for a bare or masked phone number. */
function callerInitials(contact: string): string | null {
  if (/^[+\d\s()x•…-]+$/i.test(contact)) return null;
  const words = contact.trim().split(/\s+/).filter(Boolean);
  return words.slice(0, 2).map((word) => [...word][0]?.toUpperCase() ?? "").join("") || null;
}

/** The caller, not the employee: every row would otherwise show the same face. */
function CallerAvatar({ contact }: { contact: string }) {
  const initials = callerInitials(contact);
  return (
    <span
      aria-hidden
      className="inline-flex size-9 shrink-0 items-center justify-center rounded-full bg-surface-2 text-[13px] font-semibold text-text-muted"
    >
      {initials ?? <Phone className="size-4" />}
    </span>
  );
}

/**
 * Contact, caller avatar, result pill, duration and time (docs/06 §8).
 * Render from a Server Component: time formatting must not differ between
 * server and browser.
 */
export function CallRow({ call, href, className }: CallRowProps) {
  const t = useTranslations("call");
  const locale = useLocale();
  const DirectionIcon = { incoming: PhoneIncoming, outgoing: PhoneOutgoing, web: Globe }[call.direction];
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
      <CallerAvatar contact={call.contact} />
      <span className="flex min-w-0 flex-1 flex-col">
        <span className="truncate leading-6 font-medium">{call.contact}</span>
        <span className="flex items-center gap-1.5 overflow-hidden text-[13px] leading-5 whitespace-nowrap text-text-muted">
          <DirectionIcon className="size-3.5 shrink-0" aria-hidden />
          <span className="sr-only">{t(call.direction)}, </span>
          <span className="tabular-nums">{formatTime(call.at, locale)}</span>
          <span aria-hidden>·</span>
          <span className="tabular-nums">{duration}</span>
          {/* Employee as a mini initial: one employee per business today, so a full label would only truncate. */}
          <span
            aria-hidden
            title={t("handledBy", { name: call.employeeName })}
            className="ml-0.5 inline-flex size-4 shrink-0 items-center justify-center rounded-full bg-brand-50 text-[10px] leading-none font-semibold text-brand-700"
          >
            {[...call.employeeName][0]?.toUpperCase()}
          </span>
          <span className="sr-only">, {t("handledBy", { name: call.employeeName })}</span>
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
