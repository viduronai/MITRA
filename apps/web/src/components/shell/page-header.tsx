import { cn } from "@/lib/utils";

interface PageHeaderProps {
  title: string;
  subtitle?: string;
  /** Optional trailing action (e.g. Export), right-aligned on wide screens. */
  actions?: React.ReactNode;
  className?: string;
}

/** H1 per docs/06 §4: Host Grotesk 28/34 → 36/42. */
export function PageHeader({ title, subtitle, actions, className }: PageHeaderProps) {
  const heading = (
    <div className="min-w-0">
      <h1 className="text-[28px] leading-[34px] font-semibold tracking-tight md:text-4xl md:leading-[42px]">
        {title}
      </h1>
      {subtitle && <p className="mt-1.5 max-w-2xl text-text-muted">{subtitle}</p>}
    </div>
  );
  if (!actions) return <div className={cn("mb-6 md:mb-8", className)}>{heading}</div>;
  return (
    <div className={cn("mb-6 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between md:mb-8", className)}>
      {heading}
      <div className="shrink-0">{actions}</div>
    </div>
  );
}
