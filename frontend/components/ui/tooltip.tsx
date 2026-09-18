"use client";

import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * Tooltip shown on hover and on keyboard focus.
 *
 * Focus support is the point: a tooltip that only appears on hover is invisible
 * to keyboard and touch users, so it must never carry information that is not
 * available elsewhere. Use it for clarification, never for essential content.
 */
export function Tooltip({
  content,
  children,
  side = "top",
  className,
}: {
  content: React.ReactNode;
  children: React.ReactNode;
  side?: "top" | "bottom" | "left" | "right";
  className?: string;
}) {
  const [visible, setVisible] = React.useState(false);
  const id = React.useId();

  const position = {
    top: "bottom-[calc(100%+0.375rem)] left-1/2 -translate-x-1/2",
    bottom: "top-[calc(100%+0.375rem)] left-1/2 -translate-x-1/2",
    left: "right-[calc(100%+0.375rem)] top-1/2 -translate-y-1/2",
    right: "left-[calc(100%+0.375rem)] top-1/2 -translate-y-1/2",
  }[side];

  return (
    <span
      className={cn("relative inline-flex", className)}
      onMouseEnter={() => setVisible(true)}
      onMouseLeave={() => setVisible(false)}
      onFocus={() => setVisible(true)}
      onBlur={() => setVisible(false)}
    >
      <span aria-describedby={visible ? id : undefined} className="inline-flex">
        {children}
      </span>

      {visible && (
        <span
          id={id}
          role="tooltip"
          className={cn(
            "absolute z-50 whitespace-nowrap rounded-md bg-fg px-2.5 py-1.5",
            "text-xs font-medium text-fg-inverse shadow-md pointer-events-none animate-fade-in",
            position
          )}
        >
          {content}
        </span>
      )}
    </span>
  );
}
