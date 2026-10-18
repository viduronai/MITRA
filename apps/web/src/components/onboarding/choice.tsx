import { Check } from "lucide-react";
import { cn } from "@/lib/utils";

interface ChoiceProps {
  type: "radio" | "checkbox";
  name: string;
  value: string;
  checked: boolean;
  onChange: () => void;
  disabled?: boolean;
  className?: string;
  children: React.ReactNode;
}

/**
 * A native radio/checkbox wearing a card or chip. The input stays in the
 * accessibility tree (visually hidden), so keyboard and screen readers work.
 */
export function Choice({ type, name, value, checked, onChange, disabled, className, children }: ChoiceProps) {
  return (
    <label
      className={cn(
        "relative flex cursor-pointer items-center gap-3 rounded-xl border bg-card shadow-xs transition-[border-color,background-color] motion-fast hover:border-brand-500/50 has-focus-visible:outline-2 has-focus-visible:outline-offset-2 has-focus-visible:outline-ring",
        checked && "border-brand-500 bg-brand-50 hover:border-brand-500",
        disabled && "cursor-not-allowed opacity-60 hover:border-border",
        className,
      )}
    >
      <input
        type={type}
        name={name}
        value={value}
        checked={checked}
        onChange={onChange}
        disabled={disabled}
        className="sr-only"
      />
      {children}
    </label>
  );
}

/** Small round indicator for chips: tick when chosen. */
export function ChoiceTick({ checked }: { checked: boolean }) {
  return (
    <span
      aria-hidden
      className={cn(
        "inline-flex size-5 shrink-0 items-center justify-center rounded-full border-2 border-text-subtle transition-colors motion-fast",
        checked && "border-brand-600 bg-brand-600 text-on-brand",
      )}
    >
      {checked && <Check className="size-3" strokeWidth={3} />}
    </span>
  );
}
