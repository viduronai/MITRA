import * as React from "react"
import { cn } from "cn"

// docs/06 §8: 48 px inputs, 12 px radius, label above (use <Label>).
function Input({ className, type, ...props }: React.ComponentProps<"input">) {
  return (
    <input
      type={type}
      data-slot="input"
      className={cn(
        "h-12 w-full min-w-0 rounded-lg border border-input bg-surface px-4 text-base text-foreground shadow-xs transition-[border-color,box-shadow] motion-fast file:inline-flex file:h-7 file:border-0 file:bg-transparent file:text-sm file:font-medium file:text-foreground placeholder:text-text-subtle hover:border-text-subtle/60 focus-visible:border-ring disabled:pointer-events-none disabled:cursor-not-allowed disabled:bg-surface-2 disabled:opacity-60 aria-invalid:border-destructive md:text-[15px]",
        className
      )}
      {...props}
    />
  )
}

export { Input }
