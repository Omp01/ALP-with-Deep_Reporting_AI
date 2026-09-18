"use client";

import * as React from "react";
import { Loader2 } from "lucide-react";

import { cn } from "@/lib/utils";

/**
 * Indeterminate activity indicator.
 *
 * Prefer a Skeleton when you know the shape of what is arriving — a skeleton
 * communicates *what* is loading, a spinner only that something is. Reserve the
 * spinner for actions (submitting, generating) rather than page loads.
 */
export function Spinner({
  size = "md",
  className,
  label = "Loading",
}: {
  size?: "sm" | "md" | "lg";
  className?: string;
  /** Screen-reader announcement. Pass "" for a purely decorative spinner. */
  label?: string;
}) {
  const dimension = { sm: "size-4", md: "size-5", lg: "size-8" }[size];

  return (
    <>
      <Loader2
        className={cn("animate-spin text-primary", dimension, className)}
        aria-hidden="true"
      />
      {label && (
        <span className="sr-only" role="status">
          {label}
        </span>
      )}
    </>
  );
}

/** Centred spinner filling its container — for a panel awaiting a slow action. */
export function SpinnerBlock({
  label = "Loading",
  className,
}: {
  label?: string;
  className?: string;
}) {
  return (
    <div
      className={cn("flex flex-col items-center justify-center gap-3 py-12", className)}
    >
      <Spinner size="lg" label="" />
      <p className="text-sm text-fg-muted" role="status" aria-live="polite">
        {label}
      </p>
    </div>
  );
}
