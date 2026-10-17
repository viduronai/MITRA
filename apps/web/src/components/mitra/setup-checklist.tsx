import { Check } from "lucide-react";
import { useTranslations } from "next-intl";
import { cn } from "@/lib/utils";

export interface ChecklistStep {
  id: string;
  label: string;
  done: boolean;
}

interface SetupChecklistProps {
  title: string;
  /** At most 5 steps (docs/06 §8). */
  steps: ChecklistStep[];
  action?: React.ReactNode;
  className?: string;
}

export function SetupChecklist({ title, steps, action, className }: SetupChecklistProps) {
  const t = useTranslations("setup");
  const doneCount = steps.filter((step) => step.done).length;
  const percent = steps.length ? Math.round((doneCount / steps.length) * 100) : 0;

  return (
    <section
      aria-labelledby="setup-checklist-title"
      className={cn("rounded-xl border bg-card p-5 text-card-foreground shadow-xs md:p-6", className)}
    >
      <div className="flex items-baseline justify-between gap-3">
        <h2 id="setup-checklist-title" className="text-lg leading-[26px] font-semibold">
          {title}
        </h2>
        <span className="text-sm font-medium text-text-muted tabular-nums">
          {t("progress", { percent })}
        </span>
      </div>

      <div
        role="progressbar"
        aria-label={title}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent}
        className="mt-3 h-2 overflow-hidden rounded-full bg-surface-2"
      >
        <div
          className="h-full rounded-full bg-brand-600 transition-[width] motion-slow"
          style={{ width: `${percent}%` }}
        />
      </div>

      <ol className="mt-5 flex flex-col gap-1">
        {steps.map((step, index) => (
          <li key={step.id} className="flex min-h-11 items-center gap-3">
            <span
              aria-hidden
              className={cn(
                "inline-flex size-7 shrink-0 items-center justify-center rounded-full text-[13px] font-semibold tabular-nums",
                step.done ? "bg-success/12 text-success-fg" : "border-2 border-border text-text-muted",
              )}
            >
              {step.done ? <Check className="size-4" strokeWidth={2.5} /> : index + 1}
            </span>
            <span className={cn("flex-1", step.done && "text-text-muted")}>
              {step.label}
            </span>
            <span className="sr-only">{step.done ? t("done") : t("todo")}</span>
          </li>
        ))}
      </ol>

      {action && <div className="mt-5">{action}</div>}
    </section>
  );
}
