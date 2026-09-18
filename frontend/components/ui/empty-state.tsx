"use client";

import * as React from "react";
import type { LucideIcon } from "lucide-react";

import { cn } from "@/lib/utils";

/**
 * Shown when a query succeeded and returned nothing.
 *
 * An empty state is not an error and must never be filled with placeholder
 * numbers to look busy (§64/§75). It states the situation plainly and offers
 * the one action that would resolve it — "Explore Courses" for an empty
 * enrolment list, or nothing at all when there is genuinely nothing to do.
 */
export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  secondaryAction,
  size = "md",
  className,
}: {
  icon?: LucideIcon;
  title: string;
  description?: React.ReactNode;
  action?: React.ReactNode;
  secondaryAction?: React.ReactNode;
  /** `sm` for empty regions inside a card; `md` for a whole page. */
  size?: "sm" | "md";
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center text-center",
        size === "sm" ? "px-4 py-8" : "px-6 py-14",
        className
      )}
    >
      {Icon && (
        <div
          className={cn(
            "flex items-center justify-center rounded-full bg-surface text-fg-subtle mb-4",
            size === "sm" ? "size-10" : "size-14"
          )}
          aria-hidden="true"
        >
          <Icon className={size === "sm" ? "size-5" : "size-6"} />
        </div>
      )}

      <h3
        className={cn(
          "font-semibold text-fg",
          size === "sm" ? "text-sm" : "text-base"
        )}
      >
        {title}
      </h3>

      {description && (
        <p
          className={cn(
            "mt-1.5 text-fg-muted leading-relaxed max-w-sm",
            size === "sm" ? "text-xs" : "text-sm"
          )}
        >
          {description}
        </p>
      )}

      {(action || secondaryAction) && (
        <div className="mt-5 flex flex-wrap items-center justify-center gap-2">
          {action}
          {secondaryAction}
        </div>
      )}
    </div>
  );
}

/**
 * The specific empty state for "the model does not have enough evidence yet".
 *
 * This case recurs across every AI surface, and getting it right matters for
 * the grounding requirement: when there is insufficient evidence, the correct
 * product behaviour is to say so, never to generate an insight anyway.
 */
export function InsufficientEvidenceState({
  what = "an AI insight",
  className,
  action,
}: {
  what?: string;
  className?: string;
  action?: React.ReactNode;
}) {
  return (
    <div
      className={cn(
        "rounded-lg border border-dashed border-border bg-surface px-5 py-8 text-center",
        className
      )}
    >
      <p className="text-sm font-medium text-fg">
        Not enough learning activity to generate {what} yet.
      </p>
      <p className="mt-1.5 text-xs text-fg-muted max-w-sm mx-auto leading-relaxed">
        Insights are generated only from recorded learning events. Continue
        learning to build the evidence this report needs.
      </p>
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
