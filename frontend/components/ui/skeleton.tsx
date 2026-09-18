"use client";

import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * Loading placeholder.
 *
 * Skeletons exist so a page never renders blank while its data arrives. The
 * shape of a skeleton should approximate the content it replaces — a wrong
 * shape causes a layout jump the moment real data lands, which is worse than
 * showing nothing.
 */
export function Skeleton({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("skeleton-shimmer rounded-md", className)}
      aria-hidden="true"
      {...props}
    />
  );
}

/**
 * Paragraph placeholder. The last line is short so the block reads as prose
 * rather than as a stack of identical bars.
 */
export function SkeletonText({
  lines = 3,
  className,
}: {
  lines?: number;
  className?: string;
}) {
  return (
    <div className={cn("space-y-2", className)}>
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton
          key={i}
          className={cn("h-3.5", i === lines - 1 ? "w-3/5" : "w-full")}
        />
      ))}
    </div>
  );
}

/** Stand-in for a stat tile while its metric loads. */
export function SkeletonStat({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        "rounded-lg border border-border bg-surface-elevated p-5 space-y-3",
        className
      )}
    >
      <Skeleton className="h-3 w-24" />
      <Skeleton className="h-7 w-16" />
      <Skeleton className="h-3 w-32" />
    </div>
  );
}

/** Stand-in for a content card — thumbnail, title, two meta lines. */
export function SkeletonCard({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        "rounded-lg border border-border bg-surface-elevated overflow-hidden",
        className
      )}
    >
      <Skeleton className="h-36 w-full rounded-none" />
      <div className="p-4 space-y-3">
        <Skeleton className="h-4 w-4/5" />
        <Skeleton className="h-3 w-2/5" />
        <Skeleton className="h-2 w-full rounded-full" />
      </div>
    </div>
  );
}

/** Stand-in for a data table. */
export function SkeletonTable({
  rows = 5,
  columns = 4,
  className,
}: {
  rows?: number;
  columns?: number;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "rounded-lg border border-border bg-surface-elevated overflow-hidden",
        className
      )}
    >
      <div className="flex gap-4 border-b border-border bg-surface px-4 py-3">
        {Array.from({ length: columns }).map((_, i) => (
          <Skeleton key={i} className="h-3 flex-1" />
        ))}
      </div>
      {Array.from({ length: rows }).map((_, r) => (
        <div key={r} className="flex gap-4 border-b border-border px-4 py-3 last:border-0">
          {Array.from({ length: columns }).map((_, c) => (
            <Skeleton key={c} className="h-3.5 flex-1" />
          ))}
        </div>
      ))}
    </div>
  );
}

/**
 * Announces to assistive technology that a region is loading, and renders the
 * given skeleton visually. Wrap a loading region in this rather than leaving
 * the state change silent.
 */
export function LoadingRegion({
  label = "Loading",
  children,
}: {
  label?: string;
  children: React.ReactNode;
}) {
  return (
    <div role="status" aria-live="polite" aria-busy="true">
      <span className="sr-only">{label}</span>
      {children}
    </div>
  );
}
