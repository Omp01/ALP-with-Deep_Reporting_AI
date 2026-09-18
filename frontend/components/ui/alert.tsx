"use client";

import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import {
  AlertTriangle,
  CheckCircle2,
  Info,
  XCircle,
  type LucideIcon,
} from "lucide-react";

import { cn } from "@/lib/utils";

const alertVariants = cva("rounded-md border px-4 py-3 flex items-start gap-3", {
  variants: {
    variant: {
      info: "bg-info-light border-info-border text-info",
      success: "bg-success-light border-success-border text-success",
      warning: "bg-warning-light border-warning-border text-warning",
      danger: "bg-danger-light border-danger-border text-danger",
      neutral: "bg-surface border-border text-fg-muted",
    },
  },
  defaultVariants: { variant: "info" },
});

const ICONS: Record<string, LucideIcon> = {
  info: Info,
  success: CheckCircle2,
  warning: AlertTriangle,
  danger: XCircle,
  neutral: Info,
};

export interface AlertProps
  // `title` is omitted from the DOM attributes because we redefine it as a
  // ReactNode heading rather than the string tooltip attribute.
  extends Omit<React.HTMLAttributes<HTMLDivElement>, "title">,
    VariantProps<typeof alertVariants> {
  title?: React.ReactNode;
  icon?: LucideIcon | null;
  action?: React.ReactNode;
}

/**
 * Persistent inline message attached to a region of the page.
 *
 * For transient feedback about something the user just did, use a toast
 * instead — an Alert stays until the condition it describes is resolved.
 */
export function Alert({
  className,
  variant = "info",
  title,
  icon,
  action,
  children,
  ...props
}: AlertProps) {
  const Icon = icon === null ? null : (icon ?? ICONS[variant ?? "info"]);

  return (
    <div
      role={variant === "danger" ? "alert" : "status"}
      className={cn(alertVariants({ variant }), className)}
      {...props}
    >
      {Icon && <Icon className="size-4 shrink-0 mt-0.5" aria-hidden="true" />}
      <div className="flex-1 min-w-0">
        {title && <p className="text-sm font-semibold">{title}</p>}
        {children && (
          <div className={cn("text-sm leading-relaxed", title && "mt-1 opacity-90")}>
            {children}
          </div>
        )}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  );
}

export { alertVariants };
