import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

interface EmptyStateProps {
  icon: LucideIcon;
  title?: string;
  /** One sentence. */
  description: string;
  /** One action — usually a single <Button>. */
  action?: React.ReactNode;
  className?: string;
}

/** Icon + one sentence + one action (docs/06 §8). */
export function EmptyState({ icon: Icon, title, description, action, className }: EmptyStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center rounded-xl border border-dashed bg-card px-6 py-12 text-center md:py-16",
        className,
      )}
    >
      <span className="relative mb-5 inline-flex size-16 items-center justify-center rounded-full bg-surface-2">
        <Icon className="size-7 text-text-muted" strokeWidth={1.75} aria-hidden />
        {/* Sky accent, after the illustration style in docs/06 §6 */}
        <span className="absolute top-2 right-2 size-2.5 rounded-full bg-sky-400" aria-hidden />
      </span>
      {title && <h2 className="text-lg leading-[26px] font-semibold">{title}</h2>}
      <p className="mt-1 max-w-sm text-text-muted">{description}</p>
      {action && <div className="mt-6">{action}</div>}
    </div>
  );
}
