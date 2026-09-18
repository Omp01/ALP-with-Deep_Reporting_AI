"use client";

import { useEffect } from "react";
import Link from "next/link";
import { AlertTriangle, RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { buttonVariants } from "@/components/ui/button-variants";

/**
 * Route-level error boundary.
 *
 * Catches a render or data error anywhere in the segment and shows something
 * recoverable instead of a blank screen. The raw error is never put in front
 * of the user (§51) — it goes to the console, and the digest is shown only as
 * a reference a user can quote in a bug report.
 */
export default function RouteError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Replace with the real telemetry sink when one exists.
    console.error("Unhandled route error:", error);
  }, [error]);

  return (
    <div className="flex min-h-dvh items-center justify-center bg-surface px-4">
      <div className="w-full max-w-md rounded-xl border border-border bg-surface-elevated p-8 text-center shadow-sm">
        <div
          className="mx-auto mb-5 flex size-12 items-center justify-center rounded-full bg-danger-light text-danger"
          aria-hidden="true"
        >
          <AlertTriangle className="size-6" />
        </div>

        <h1 className="text-lg font-semibold text-fg">Something went wrong</h1>
        <p className="mt-2 text-sm leading-relaxed text-fg-muted">
          This page could not be displayed. The problem has been logged. You can
          try again, or head back to your dashboard.
        </p>

        <div className="mt-6 flex flex-wrap items-center justify-center gap-2">
          <Button onClick={reset}>
            <RefreshCw aria-hidden="true" />
            Try again
          </Button>
          <Link href="/" className={buttonVariants({ variant: "secondary" })}>
            Go home
          </Link>
        </div>

        {error.digest && (
          <p className="mt-5 text-[11px] text-fg-subtle">
            Reference: <code className="font-mono">{error.digest}</code>
          </p>
        )}
      </div>
    </div>
  );
}
