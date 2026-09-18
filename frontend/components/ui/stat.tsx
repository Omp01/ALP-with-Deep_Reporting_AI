"use client";

import * as React from "react";
import { ArrowDownRight, ArrowRight, ArrowUpRight, type LucideIcon } from "lucide-react";

import { cn } from "@/lib/utils";
import { Tooltip } from "./tooltip";

/**
 * A single headline metric.
 *
 * `value` is always passed in already computed by the backend. Stat tiles must
 * not derive business metrics in the browser (§45) — the component's job is to
 * present a number, not to work one out.
 *
 * `trend` describes movement over a stated period; without a period the arrow
 * means nothing, so `trendPeriod` is required alongside it.
 */
export function Stat({
  label,
  value,
  unit,
  icon: Icon,
  trend,
  trendPeriod,
  hint,
  footer,
  className,
}: {
  label: string;
  value: React.ReactNode;
  unit?: string;
  icon?: LucideIcon;
  /** Signed change. Positive renders as an up arrow, negative as down. */
  trend?: number;
  /** e.g. "vs. last 30 days". Required when `trend` is given. */
  trendPeriod?: string;
  /** Explains how the metric is derived — shown in a tooltip on the label. */
  hint?: string;
  footer?: React.ReactNode;
  className?: string;
}) {
  const hasTrend = typeof trend === "number" && trend !== 0;
  const TrendIcon = !hasTrend ? ArrowRight : trend > 0 ? ArrowUpRight : ArrowDownRight;
  const trendTone = !hasTrend
    ? "text-fg-subtle"
    : trend > 0
      ? "text-success"
      : "text-danger";

  return (
    <div
      className={cn(
        "rounded-lg border border-border bg-surface-elevated p-5 shadow-xs",
        className
      )}
    >
      <div className="flex items-start justify-between gap-3">
        {hint ? (
          <Tooltip content={hint}>
            <span className="text-xs font-medium uppercase tracking-wide text-fg-muted cursor-help border-b border-dotted border-border-strong">
              {label}
            </span>
          </Tooltip>
        ) : (
          <span className="text-xs font-medium uppercase tracking-wide text-fg-muted">
            {label}
          </span>
        )}
        {Icon && <Icon className="size-4 text-fg-subtle shrink-0" aria-hidden="true" />}
      </div>

      <div className="mt-2.5 flex items-baseline gap-1.5">
        <span className="text-2xl font-semibold text-fg tabular-nums tracking-tight">
          {value}
        </span>
        {unit && <span className="text-sm font-medium text-fg-muted">{unit}</span>}
      </div>

      {typeof trend === "number" && trendPeriod && (
        <div className={cn("mt-2 flex items-center gap-1 text-xs font-medium", trendTone)}>
          <TrendIcon className="size-3.5" aria-hidden="true" />
          <span className="tabular-nums">
            {trend > 0 ? "+" : ""}
            {trend}
            {unit === "%" ? " pts" : ""}
          </span>
          <span className="text-fg-subtle font-normal">{trendPeriod}</span>
        </div>
      )}

      {footer && <div className="mt-3 text-xs text-fg-muted">{footer}</div>}
    </div>
  );
}

/** Responsive row of stat tiles. */
export function StatGrid({
  children,
  columns = 4,
  className,
}: {
  children: React.ReactNode;
  columns?: 2 | 3 | 4;
  className?: string;
}) {
  const cols = {
    2: "sm:grid-cols-2",
    3: "sm:grid-cols-2 lg:grid-cols-3",
    4: "sm:grid-cols-2 lg:grid-cols-4",
  }[columns];

  return <div className={cn("grid grid-cols-1 gap-4", cols, className)}>{children}</div>;
}
