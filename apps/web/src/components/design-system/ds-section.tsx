import { cn } from "@/lib/utils";

interface DsSectionProps {
  id: string;
  title: string;
  description?: string;
  children: React.ReactNode;
  className?: string;
}

export function DsSection({ id, title, description, children, className }: DsSectionProps) {
  return (
    <section id={id} aria-labelledby={`${id}-title`} className={cn("scroll-mt-24", className)}>
      <h2 id={`${id}-title`} className="text-[22px] leading-7 font-semibold tracking-tight md:text-[28px] md:leading-[34px]">
        {title}
      </h2>
      {description && <p className="mt-1 max-w-2xl text-text-muted">{description}</p>}
      <div className="mt-6">{children}</div>
    </section>
  );
}

/** A labelled specimen box used throughout the page. */
export function Specimen({
  label,
  children,
  className,
}: {
  label: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col gap-3 rounded-xl border bg-card p-5 shadow-xs", className)}>
      <span className="font-mono text-xs text-text-muted">{label}</span>
      {children}
    </div>
  );
}
