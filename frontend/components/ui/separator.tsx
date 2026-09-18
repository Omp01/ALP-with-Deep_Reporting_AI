"use client";

import * as React from "react";

import { cn } from "@/lib/utils";

/** Visual divider. Decorative by default, so it is hidden from screen readers. */
export function Separator({
  orientation = "horizontal",
  label,
  className,
}: {
  orientation?: "horizontal" | "vertical";
  /** Renders text centred on the rule — "or", "Older activity", etc. */
  label?: string;
  className?: string;
}) {
  if (label) {
    return (
      <div className={cn("flex items-center gap-3", className)}>
        <div className="h-px flex-1 bg-border" aria-hidden="true" />
        <span className="text-xs font-medium text-fg-subtle whitespace-nowrap">
          {label}
        </span>
        <div className="h-px flex-1 bg-border" aria-hidden="true" />
      </div>
    );
  }

  return (
    <div
      role="separator"
      aria-orientation={orientation}
      className={cn(
        "bg-border shrink-0",
        orientation === "horizontal" ? "h-px w-full" : "w-px self-stretch",
        className
      )}
    />
  );
}
