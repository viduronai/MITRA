import { cn } from "@/lib/utils";

/** Wordmark + three-dot "smile" motif (docs/06 §2). Placeholder until the real logo. */
export function MitraMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={cn("size-8 shrink-0", className)} aria-hidden>
      <rect width="32" height="32" rx="10" className="fill-brand-600" />
      <circle cx="10" cy="15" r="2.4" className="fill-on-brand" />
      <circle cx="16" cy="18.5" r="2.4" className="fill-accent-400" />
      <circle cx="22" cy="15" r="2.4" className="fill-on-brand" />
    </svg>
  );
}

export function MitraWordmark({ className }: { className?: string }) {
  return (
    <span className={cn("font-display text-xl leading-none font-semibold tracking-tight", className)}>
      mitra
    </span>
  );
}
