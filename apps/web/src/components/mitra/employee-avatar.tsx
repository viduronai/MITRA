import { cn } from "@/lib/utils";

// Soft gradient circles with initials — never fake human photos (docs/06 §6).
const gradients = [
  "from-brand-100 to-sky-100",
  "from-sky-100 to-brand-50",
  "from-brand-50 to-success/20",
  "from-info/20 to-brand-100",
];

const sizes = {
  sm: "size-8 text-xs",
  md: "size-12 text-base",
  lg: "size-16 text-xl",
};

function pickGradient(name: string): string {
  let hash = 0;
  for (const char of name) hash = (hash + char.charCodeAt(0)) % gradients.length;
  return gradients[hash];
}

interface EmployeeAvatarProps {
  name: string;
  initials?: string;
  size?: keyof typeof sizes;
  /** Shows a sound ring — only while audio is actually playing. */
  speaking?: boolean;
  className?: string;
}

export function EmployeeAvatar({ name, initials, size = "md", speaking, className }: EmployeeAvatarProps) {
  return (
    <span className={cn("relative inline-flex shrink-0", className)} aria-hidden>
      {speaking && (
        <span className="absolute -inset-1 rounded-full border-2 border-sky-400 motion-safe:animate-[ping_1.4s_cubic-bezier(0,0,0.2,1)_infinite]" />
      )}
      <span
        className={cn(
          "relative inline-flex items-center justify-center rounded-full bg-linear-135 font-display font-semibold text-brand-700 ring-1 ring-black/5 dark:ring-white/10",
          pickGradient(name),
          sizes[size],
          speaking && "ring-2 ring-sky-400",
        )}
      >
        {initials ?? name.slice(0, 1).toUpperCase()}
      </span>
    </span>
  );
}
