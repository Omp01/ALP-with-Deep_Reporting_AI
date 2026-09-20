"use client";

import * as React from "react";

import { cn, initials } from "@/lib/utils";

/**
 * User avatar with a deterministic initials fallback.
 *
 * The background colour is derived from the name, so the same person keeps the
 * same colour across every surface — a small but real aid when scanning a team
 * roster. It is decorative, never the only way a user is identified.
 */
const PALETTE = [
  "bg-chart-1/12 text-chart-1",
  "bg-chart-2/12 text-chart-2",
  "bg-chart-3/12 text-chart-3",
  "bg-chart-4/15 text-chart-4",
  "bg-chart-6/12 text-chart-6",
];

function colorFor(seed: string): string {
  let hash = 0;
  for (let i = 0; i < seed.length; i++) {
    hash = (hash * 31 + seed.charCodeAt(i)) | 0;
  }
  return PALETTE[Math.abs(hash) % PALETTE.length];
}

export function Avatar({
  name,
  src,
  size = "md",
  className,
}: {
  name: string;
  src?: string | null;
  size?: "xs" | "sm" | "md" | "lg";
  className?: string;
}) {
  const [failed, setFailed] = React.useState(false);

  const dimension = {
    xs: "size-6 text-[10px]",
    sm: "size-8 text-xs",
    md: "size-9 text-sm",
    lg: "size-12 text-base",
  }[size];

  if (src && !failed) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={src}
        alt=""
        onError={() => setFailed(true)}
        className={cn(
          "rounded-full object-cover border border-border shrink-0",
          dimension,
          className
        )}
      />
    );
  }

  return (
    <span
      aria-hidden="true"
      className={cn(
        "inline-flex items-center justify-center rounded-full font-semibold shrink-0 select-none",
        colorFor(name),
        dimension,
        className
      )}
    >
      {initials(name)}
    </span>
  );
}
