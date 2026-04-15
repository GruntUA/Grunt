import type { VariantProps } from "class-variance-authority"
import { cva } from "class-variance-authority"

export { default as Badge } from "./Badge.vue"

export const badgeVariants = cva(
  "inline-flex gap-1 items-center rounded-md border px-2.5 py-0.5 text-xs font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2",
  {
    variants: {
      variant: {
        default:
          "border-transparent bg-primary text-primary-foreground shadow hover:bg-primary/80",
        secondary:
          "border-transparent bg-secondary text-secondary-foreground hover:bg-secondary/80",
        destructive:
          "border-transparent bg-destructive text-destructive-foreground shadow hover:bg-destructive/80",
        outline: "text-foreground",
        gray: "border-muted-foreground/20 bg-muted/40 text-muted-foreground dark:bg-muted/20 dark:text-muted-foreground",
        blue: "border-blue-500/30 bg-blue-500/10 text-blue-700 dark:text-blue-400",
        green: "border-green-500/30 bg-green-500/10 text-green-700 dark:text-emerald-400",
        yellow: "border-yellow-500/30 bg-yellow-500/10 text-yellow-700 dark:text-amber-400",
        orange: "border-orange-500/30 bg-orange-500/10 text-orange-700 dark:text-orange-400",
        red: "border-red-500/30 bg-red-500/10 text-red-700 dark:text-red-400",
        purple: "border-purple-500/30 bg-purple-500/10 text-purple-700 dark:text-purple-400",
        pink: "border-pink-500/30 bg-pink-500/10 text-pink-700 dark:text-pink-400",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  },
)

export type BadgeVariants = VariantProps<typeof badgeVariants>
