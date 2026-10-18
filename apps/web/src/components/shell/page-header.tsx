import { cn } from "@/lib/utils";

interface PageHeaderProps {
  title: string;
  subtitle?: string;
  className?: string;
}

/** H1 per docs/06 §4: Host Grotesk 28/34 → 36/42. */
export function PageHeader({ title, subtitle, className }: PageHeaderProps) {
  return (
    <div className={cn("mb-6 md:mb-8", className)}>
      <h1 className="text-[28px] leading-[34px] font-semibold tracking-tight md:text-4xl md:leading-[42px]">
        {title}
      </h1>
      {subtitle && <p className="mt-1.5 max-w-2xl text-text-muted">{subtitle}</p>}
    </div>
  );
}
