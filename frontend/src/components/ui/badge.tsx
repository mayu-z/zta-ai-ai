import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-full border px-2.5 py-0.5 text-[11px] font-medium tracking-wide",
  {
    variants: {
      variant: {
        default: "border-border bg-bg text-text-primary",
        success: "border-[#81B78A] bg-[#E8F3EA] text-[#1F6B2A]",
        warning: "border-[#D2B16A] bg-[#FFF5DC] text-[#7B5600]",
        danger: "border-[#DE8F8F] bg-[#FDEAEA] text-[#9A1F1F]",
        accent: "border-primary bg-primary-tint text-primary-hover",
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
