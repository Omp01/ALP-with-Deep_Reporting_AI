"use client";

import { useCallback } from "react";

import { ApiError } from "@/lib/api-client";
import { useToastContext, type ToastInput } from "@/components/ui/toast";

/**
 * Convenience wrapper over the toast queue.
 *
 * `toastError` takes a caught error and renders its user-facing message, so
 * call sites never have to decide what is safe to show (§51).
 */
export function useToast() {
  const { toast, dismiss } = useToastContext();

  const toastSuccess = useCallback(
    (title: string, description?: string) =>
      toast({ title, description, variant: "success" }),
    [toast]
  );

  const toastError = useCallback(
    (error: unknown, fallbackTitle = "Something went wrong") => {
      const description =
        error instanceof ApiError
          ? error.userMessage
          : error instanceof Error
            ? "The request could not be completed. Please try again."
            : undefined;

      return toast({ title: fallbackTitle, description, variant: "error" });
    },
    [toast]
  );

  const toastInfo = useCallback(
    (title: string, description?: string) =>
      toast({ title, description, variant: "info" }),
    [toast]
  );

  const toastWarning = useCallback(
    (title: string, description?: string) =>
      toast({ title, description, variant: "warning" }),
    [toast]
  );

  return {
    toast: toast as (input: ToastInput) => string,
    toastSuccess,
    toastError,
    toastInfo,
    toastWarning,
    dismiss,
  };
}
