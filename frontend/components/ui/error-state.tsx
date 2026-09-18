"use client";

import * as React from "react";
import {
  AlertTriangle,
  Lock,
  RefreshCw,
  SearchX,
  ServerCrash,
  WifiOff,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { ApiError } from "@/lib/api-client";
import { Button } from "./button";

/**
 * Renders a failed request as something a user can act on.
 *
 * Deliberately never shows `error.message` for 5xx or network failures — those
 * carry server internals. It shows `ApiError.userMessage` and keeps the raw
 * detail in a collapsed block for engineers (§51: no raw stack traces).
 */
export function ErrorState({
  error,
  onRetry,
  title,
  size = "md",
  className,
}: {
  error: unknown;
  onRetry?: () => void;
  /** Overrides the title chosen from the error kind. */
  title?: string;
  size?: "sm" | "md";
  className?: string;
}) {
  const api = error instanceof ApiError ? error : null;

  const { icon: Icon, defaultTitle } = describe(api);
  const message = api
    ? api.userMessage
    : "Something went wrong while loading this. Please try again.";

  // A retry cannot fix a permissions failure, so do not offer one.
  const retryable = !api?.isForbidden && Boolean(onRetry);

  return (
    <div
      role="alert"
      className={cn(
        "flex flex-col items-center justify-center text-center rounded-lg border border-border bg-surface-elevated",
        size === "sm" ? "px-4 py-8" : "px-6 py-12",
        className
      )}
    >
      <div
        className="flex items-center justify-center size-12 rounded-full bg-danger-light text-danger mb-4"
        aria-hidden="true"
      >
        <Icon className="size-5" />
      </div>

      <h3 className="text-base font-semibold text-fg">{title ?? defaultTitle}</h3>
      <p className="mt-1.5 text-sm text-fg-muted max-w-sm leading-relaxed">
        {message}
      </p>

      {retryable && (
        <Button variant="secondary" size="sm" className="mt-5" onClick={onRetry}>
          <RefreshCw aria-hidden="true" />
          Try again
        </Button>
      )}

      {/* Diagnostic detail, collapsed. Useful in development and in a bug
          report; invisible during normal use. */}
      {api && !api.isForbidden && !api.isUnauthorized && (
        <details className="mt-4 w-full max-w-sm text-left">
          <summary className="cursor-pointer text-xs text-fg-subtle hover:text-fg-muted">
            Technical details
          </summary>
          <pre className="mt-2 overflow-x-auto rounded-md bg-surface-sunken p-3 text-[11px] text-fg-muted">
            {api.status} {api.code}
            {"\n"}
            {api.message}
          </pre>
        </details>
      )}
    </div>
  );
}

function describe(api: ApiError | null): { icon: typeof AlertTriangle; defaultTitle: string } {
  if (!api) return { icon: AlertTriangle, defaultTitle: "Something went wrong" };
  if (api.isNetworkError) return { icon: WifiOff, defaultTitle: "Connection problem" };
  if (api.isForbidden) return { icon: Lock, defaultTitle: "Access denied" };
  if (api.isNotFound) return { icon: SearchX, defaultTitle: "Not found" };
  if (api.isServerError) return { icon: ServerCrash, defaultTitle: "Server error" };
  return { icon: AlertTriangle, defaultTitle: "Request failed" };
}

/**
 * Compact inline variant, for a failed region inside an otherwise healthy page
 * — a widget whose data source is down while the rest of the dashboard renders.
 */
export function InlineError({
  error,
  onRetry,
  className,
}: {
  error: unknown;
  onRetry?: () => void;
  className?: string;
}) {
  const message =
    error instanceof ApiError
      ? error.userMessage
      : "Could not load this section.";

  return (
    <div
      role="alert"
      className={cn(
        "flex items-start gap-2.5 rounded-md border border-danger-border bg-danger-light px-3 py-2.5",
        className
      )}
    >
      <AlertTriangle className="size-4 shrink-0 mt-px text-danger" aria-hidden="true" />
      <p className="text-xs text-danger flex-1 leading-relaxed">{message}</p>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="text-xs font-semibold text-danger underline underline-offset-2 hover:opacity-80 shrink-0"
        >
          Retry
        </button>
      )}
    </div>
  );
}
