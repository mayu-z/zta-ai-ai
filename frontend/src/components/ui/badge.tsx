import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-full border px-2.5 py-0.5 text-[11px] font-medium tracking-wide",
  {
    variants: {
      variant: {
        default: "border-white/15 bg-white/5 text-text-primary",
        success: "border-emerald-400/35 bg-emerald-500/15 text-emerald-200",
        warning: "border-amber-400/35 bg-amber-500/15 text-amber-200",
        danger: "border-red-400/35 bg-red-500/15 text-red-200",
        accent: "border-indigo-400/35 bg-indigo-500/15 text-indigo-200",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return <div className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { Badge, badgeVariants };
