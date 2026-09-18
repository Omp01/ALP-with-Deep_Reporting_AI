"use client";

import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * Data table primitives.
 *
 * `<TableContainer>` provides the horizontal scroll that keeps a wide table
 * from forcing the whole page to scroll sideways on a narrow screen — a table
 * must scroll inside its own box, never push the body.
 */

export function TableContainer({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "w-full overflow-x-auto rounded-lg border border-border bg-surface-elevated",
        className
      )}
    >
      {children}
    </div>
  );
}

export function Table({
  children,
  className,
  caption,
}: {
  children: React.ReactNode;
  className?: string;
  /** Describes the table for screen readers. Visually hidden. */
  caption?: string;
}) {
  return (
    <table className={cn("w-full border-collapse text-sm", className)}>
      {caption && <caption className="sr-only">{caption}</caption>}
      {children}
    </table>
  );
}

export function THead({ children }: { children: React.ReactNode }) {
  return <thead className="bg-surface">{children}</thead>;
}

export function TBody({ children }: { children: React.ReactNode }) {
  return <tbody>{children}</tbody>;
}

export function TR({
  children,
  className,
  onClick,
}: {
  children: React.ReactNode;
  className?: string;
  onClick?: () => void;
}) {
  return (
    <tr
      onClick={onClick}
      className={cn(
        "border-b border-border last:border-0",
        onClick && "cursor-pointer hover:bg-surface transition-colors",
        className
      )}
    >
      {children}
    </tr>
  );
}

export function TH({
  children,
  className,
  align = "left",
  scope = "col",
}: {
  children: React.ReactNode;
  className?: string;
  align?: "left" | "right" | "center";
  scope?: "col" | "row";
}) {
  return (
    <th
      scope={scope}
      className={cn(
        "px-4 py-2.5 text-xs font-semibold uppercase tracking-wide text-fg-muted whitespace-nowrap",
        { left: "text-left", right: "text-right", center: "text-center" }[align],
        className
      )}
    >
      {children}
    </th>
  );
}

export function TD({
  children,
  className,
  align = "left",
}: {
  children: React.ReactNode;
  className?: string;
  align?: "left" | "right" | "center";
}) {
  return (
    <td
      className={cn(
        "px-4 py-3 text-sm text-fg align-middle",
        { left: "text-left", right: "text-right", center: "text-center" }[align],
        className
      )}
    >
      {children}
    </td>
  );
}
