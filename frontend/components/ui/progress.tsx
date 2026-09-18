"use client";

import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * Determinate progress bar.
 *
 * `value` is a percentage (0–100). Callers pass a *derived* number — progress
 * computed from completion records — never a stored or invented figure (§18).
 */
export function Progress({
  value,
  max = 100,
  size = "md",
  tone = "primary",
  label,
  showValue = false,
  className,
}: {
  value: number;
  max?: number;
  size?: "xs" | "sm" | "md";
  tone?: "primary" | "success" | "warning" | "danger";
  /** Accessible name. Required whenever the bar is not adjacent to its own label. */
  label?: string;
  showValue?: boolean;
  className?: string;
}) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  const height = { xs: "h-1", sm: "h-1.5", md: "h-2" }[size];
  const fill = {
    primary: "bg-primary",
    success: "bg-success",
    warning: "bg-warning",
    danger: "bg-danger",
  }[tone];

  return (
    <div className={cn("w-full", className)}>
      {(label || showValue) && (
        <div className="flex items-baseline justify-between mb-1.5 gap-2">
          {label && <span className="text-xs font-medium text-fg-muted">{label}</span>}
          {showValue && (
            <span className="text-xs font-semibold text-fg tabular-nums">
              {Math.round(pct)}%
            </span>
          )}
        </div>
      )}
      <div
        role="progressbar"
        aria-valuenow={Math.round(pct)}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={label}
        className={cn("w-full overflow-hidden rounded-full bg-surface-sunken", height)}
      >
        <div
          className={cn("h-full rounded-full transition-[width] duration-500", fill)}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

/** Mastery bands used across competency surfaces. */
export type MasteryBand = "critical" | "low" | "medium" | "high";

/** Maps a 0–1 mastery probability to its band. Thresholds match the engine. */
export function masteryBand(mastery: number): MasteryBand {
  if (mastery >= 0.8) return "high";
  if (mastery >= 0.6) return "medium";
  if (mastery >= 0.4) return "low";
  return "critical";
}

export function masteryLabel(band: MasteryBand): string {
  return {
    high: "Mastered",
    medium: "Developing",
    low: "Emerging",
    critical: "Needs attention",
  }[band];
}

/**
 * Competency mastery bar.
 *
 * Takes mastery as a 0–1 probability (the engine's native scale) rather than a
 * percentage, so callers cannot accidentally pass an already-scaled number.
 */
export function MasteryBar({
  mastery,
  label,
  showValue = true,
  size = "sm",
  className,
}: {
  mastery: number;
  label?: string;
  showValue?: boolean;
  size?: "xs" | "sm" | "md";
  className?: string;
}) {
  const band = masteryBand(mastery);
  const height = { xs: "h-1", sm: "h-1.5", md: "h-2" }[size];
  const fill = {
    high: "bg-mastery-high",
    medium: "bg-mastery-medium",
    low: "bg-mastery-low",
    critical: "bg-mastery-critical",
  }[band];

  const pct = Math.max(0, Math.min(100, mastery * 100));

  return (
    <div className={cn("w-full", className)}>
      {(label || showValue) && (
        <div className="flex items-baseline justify-between mb-1.5 gap-2">
          {label && (
            <span className="text-xs font-medium text-fg truncate">{label}</span>
          )}
          {showValue && (
            <span className="text-xs font-semibold text-fg tabular-nums shrink-0">
              {Math.round(pct)}%
            </span>
          )}
        </div>
      )}
      <div
        role="progressbar"
        aria-valuenow={Math.round(pct)}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={label ? `${label} mastery` : "Mastery"}
        className={cn("w-full overflow-hidden rounded-full bg-surface-sunken", height)}
      >
        <div
          className={cn("h-full rounded-full transition-[width] duration-500", fill)}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}
