import Link from "next/link";
import { useTranslations } from "next-intl";
import { BUCKETS, type Bucket, type CampaignProgress } from "@/lib/campaigns/types";
import { cn } from "@/lib/utils";

const tone: Record<Bucket, string> = {
  interested: "bg-success",
  call_back: "bg-info",
  not_interested: "bg-text-subtle",
  no_answer: "bg-warning",
  blocked: "bg-danger",
};

/** Result buckets as one stacked bar plus tappable counts (each filters the people list). */
export function BucketBars({
  progress,
  hrefFor,
  active,
}: {
  progress: CampaignProgress;
  hrefFor?: (bucket: Bucket) => string;
  active?: Bucket | null;
}) {
  const t = useTranslations("campaigns.buckets");
  const total = Math.max(1, progress.total - progress.skipped);
  return (
    <div>
      <div className="flex h-2.5 overflow-hidden rounded-full bg-surface-2" aria-hidden>
        {BUCKETS.map((b) =>
          progress.buckets[b] ? (
            <span key={b} className={tone[b]} style={{ width: `${(progress.buckets[b] / total) * 100}%` }} />
          ) : null,
        )}
      </div>
      <ul className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-5">
        {BUCKETS.map((b) => {
          const body = (
            <>
              <span className="flex items-center gap-2 text-[13px] leading-5 text-text-muted">
                <span className={cn("size-2 rounded-full", tone[b])} aria-hidden />
                {t(b)}
              </span>
              <span className="mt-1 text-xl leading-7 font-semibold tabular-nums">{progress.buckets[b] ?? 0}</span>
            </>
          );
          const classes = cn(
            "flex flex-col rounded-lg border bg-card px-3 py-2.5",
            active === b && "border-brand-500 ring-1 ring-brand-500",
            hrefFor && "focus-ring transition-colors motion-fast hover:bg-surface-2",
          );
          return (
            <li key={b}>
              {hrefFor ? (
                <Link href={hrefFor(b)} className={classes} aria-current={active === b ? "true" : undefined}>
                  {body}
                </Link>
              ) : (
                <div className={classes}>{body}</div>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
