import { cn } from "@/lib/utils";

export interface UsageBar {
  key: string;
  /** Short axis label, e.g. "18". */
  label: string;
  value: number;
  /** Full sentence for hover/focus and screen readers. */
  tooltip: string;
}

/**
 * Single-series daily spend: one hue (brand), thin bars with 4 px rounded tops on a shared
 * baseline, 2 px gaps, recessive axis. Each bar is focusable and shows its value on hover/focus;
 * the accessible list doubles as the table view.
 */
export function UsageBars({ bars, maxLabel }: { bars: UsageBar[]; maxLabel: string }) {
  const max = Math.max(1, ...bars.map((b) => b.value));
  return (
    <div>
      <div className="flex items-baseline justify-between text-[12px] text-text-subtle tabular-nums">
        <span>{maxLabel}</span>
      </div>
      <ol className="relative mt-1 flex h-36 items-end gap-[2px] border-b border-border" role="list">
        {bars.map((bar) => (
          <li key={bar.key} className="group relative flex h-full flex-1 items-end justify-center">
            <span
              tabIndex={0}
              aria-label={bar.tooltip}
              className="focus-ring absolute inset-x-0 bottom-0 top-0 rounded-sm"
            />
            <span
              aria-hidden
              className={cn(
                "w-full max-w-6 rounded-t-[4px] transition-colors motion-fast",
                bar.value > 0 ? "bg-brand-500 group-hover:bg-brand-700" : "bg-border",
              )}
              style={{ height: bar.value > 0 ? `${Math.max(3, (bar.value / max) * 100)}%` : "2px" }}
            />
            <span
              role="tooltip"
              className="pointer-events-none absolute bottom-full left-1/2 z-10 mb-1 hidden -translate-x-1/2 rounded-md border bg-popover px-2 py-1 text-[12px] whitespace-nowrap text-popover-foreground shadow-sm group-focus-within:block group-hover:block"
            >
              {bar.tooltip}
            </span>
          </li>
        ))}
      </ol>
      <div className="mt-1 flex gap-[2px] text-[11px] text-text-subtle tabular-nums" aria-hidden>
        {bars.map((bar, index) => (
          <span key={bar.key} className="flex-1 text-center">
            {index % 2 === 0 || bars.length <= 7 ? bar.label : ""}
          </span>
        ))}
      </div>
    </div>
  );
}
