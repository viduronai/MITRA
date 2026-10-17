import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "cn"
import { Slot } from "radix-ui"

// Mitra buttons (docs/06 §8): primary · secondary · ghost · danger · link,
// heights 40 / 48 / 56 px. Small sizes keep a 44 px hit area (hit-area).
const primary =
  "bg-primary text-primary-foreground shadow-xs hover:bg-brand-700 active:bg-brand-700"
const secondary =
  "border-border bg-surface text-foreground shadow-xs hover:bg-surface-2 aria-expanded:bg-surface-2"
const danger =
  "bg-danger text-white hover:bg-danger-fg dark:text-[#0b0b0d] dark:hover:bg-danger/90"

const buttonVariants = cva(
  "group/button relative inline-flex shrink-0 items-center justify-center gap-2 rounded-lg border border-transparent bg-clip-padding font-medium whitespace-nowrap select-none transition-[background-color,border-color,color,box-shadow,transform] motion-fast active:not-aria-[haspopup]:translate-y-px disabled:pointer-events-none disabled:opacity-50 aria-invalid:border-destructive [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-5",
  {
    variants: {
      variant: {
        default: primary,
        primary,
        secondary,
        outline: secondary,
        ghost:
          "text-foreground hover:bg-surface-2 aria-expanded:bg-surface-2",
        destructive: danger,
        danger,
        link: "h-auto! px-0! text-brand-600 underline-offset-4 hover:underline dark:text-brand-500",
      },
      size: {
        xs: "hit-area h-8 gap-1.5 rounded-md px-2.5 text-[13px] [&_svg:not([class*='size-'])]:size-4",
        sm: "hit-area h-10 px-4 text-sm [&_svg:not([class*='size-'])]:size-4",
        default: "h-12 px-5 text-[15px]",
        lg: "h-14 px-6 text-base",
        icon: "size-11",
        "icon-xs": "hit-area size-8 rounded-md [&_svg:not([class*='size-'])]:size-4",
        "icon-sm": "hit-area size-10",
        "icon-lg": "size-12",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

function Button({
  className,
  variant = "default",
  size = "default",
  asChild = false,
  ...props
}: React.ComponentProps<"button"> &
  VariantProps<typeof buttonVariants> & {
    asChild?: boolean
  }) {
  const Comp = asChild ? Slot.Root : "button"

  return (
    <Comp
      data-slot="button"
      data-variant={variant}
      data-size={size}
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  )
}

export { Button, buttonVariants }
