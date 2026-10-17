import { cn } from "@/lib/utils";

/** Pulsing Marigold dot for "on a call right now". Static under reduced motion. */
export function LiveDot({ className, label }: { className?: string; label?: string }) {
  return (
    <span
      className={cn("relative inline-flex size-2.5 shrink-0", className)}
      role={label ? "img" : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
    >
      <span className="absolute inset-0 rounded-full bg-accent-400 opacity-70 motion-safe:animate-[ping_1.8s_cubic-bezier(0,0,0.2,1)_infinite]" />
      <span className="relative inline-flex size-2.5 rounded-full bg-accent-400" />
    </span>
  );
}
