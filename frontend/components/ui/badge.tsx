"use client";

import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1.5 rounded-full border font-medium whitespace-nowrap [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        neutral: "bg-surface text-fg-muted border-border",
        primary: "bg-primary-light text-primary border-primary-border",
        success: "bg-success-light text-success border-success-border",
        warning: "bg-warning-light text-warning border-warning-border",
        danger: "bg-danger-light text-danger border-danger-border",
        info: "bg-info-light text-info border-info-border",
        /** High-contrast fill. Use sparingly — for one key status per view. */
        solid: "bg-fg text-fg-inverse border-transparent",
      },
      size: {
        sm: "px-2 py-0.5 text-[11px] [&_svg]:size-3",
        md: "px-2.5 py-0.5 text-xs [&_svg]:size-3.5",
      },
    },
    defaultVariants: { variant: "neutral", size: "md" },
  }
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, size, ...props }: BadgeProps) {
  return (
    <span className={cn(badgeVariants({ variant, size }), className)} {...props} />
  );
}

/** Small coloured dot, for inline status without a full badge. */
export function StatusDot({
  variant = "neutral",
  className,
  label,
}: {
  variant?: "neutral" | "success" | "warning" | "danger" | "info" | "primary";
  className?: string;
  /** Screen-reader text. Without it the dot is decorative only. */
  label?: string;
}) {
  const color = {
    neutral: "bg-fg-subtle",
    primary: "bg-primary",
    success: "bg-success",
    warning: "bg-warning",
    danger: "bg-danger",
    info: "bg-info",
  }[variant];

  return (
    <>
      <span
        className={cn("inline-block size-2 rounded-full shrink-0", color, className)}
        aria-hidden="true"
      />
      {label && <span className="sr-only">{label}</span>}
    </>
  );
}

export { badgeVariants };
