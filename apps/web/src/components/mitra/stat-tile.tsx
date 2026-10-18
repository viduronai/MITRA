import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";
import Link from "next/link";
import { cn } from "@/lib/utils";

export type TrendDirection = "up" | "down" | "flat";

interface StatTileProps {
  label: string;
  /** Already formatted for the locale, e.g. "24" or "₹1,20,000". */
  value: string;
  trend?: { direction: TrendDirection; label: string };
  /** Tap → filtered list (docs/06 §8). */
  href?: string;
  highlight?: boolean;
  className?: string;
}

const trendIcons = { up: ArrowUpRight, down: ArrowDownRight, flat: Minus };

export function StatTile({ label, value, trend, href, highlight, className }: StatTileProps) {
  const TrendIcon = trend ? trendIcons[trend.direction] : null;
  const body = (
    <>
      <span className="text-sm leading-5 font-medium text-text-muted">{label}</span>
      <span className="mt-2 font-sans text-[32px] leading-9 font-semibold tracking-tight tabular-nums md:text-[44px] md:leading-[48px]">
        {value}
      </span>
      {trend && TrendIcon && (
        <span className="mt-1 inline-flex items-start gap-1 text-[13px] leading-5 text-text-muted">
          <TrendIcon className="mt-[3px] size-3.5 shrink-0" aria-hidden />
          <span className="line-clamp-2">{trend.label}</span>
        </span>
      )}
    </>
  );

  const classes = cn(
    "flex min-h-[132px] flex-col rounded-xl border bg-card p-4 text-card-foreground shadow-xs md:min-h-40 md:p-5",
    highlight && "border-sky-400/60 bg-sky-100/60",
    href && "focus-ring transition-[transform,box-shadow,border-color] motion-fast hover:-translate-y-0.5 hover:shadow-sm",
    className,
  );

  return href ? (
    <Link href={href} className={classes}>
      {body}
    </Link>
  ) : (
    <div className={classes}>{body}</div>
  );
}
