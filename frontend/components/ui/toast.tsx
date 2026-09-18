"use client";

import * as React from "react";
import { createPortal } from "react-dom";
import {
  AlertTriangle,
  CheckCircle2,
  Info,
  X,
  XCircle,
  type LucideIcon,
} from "lucide-react";

import { cn } from "@/lib/utils";

/**
 * Transient feedback about an action the user just took — "Enrolled",
 * "Report generated", "Could not save".
 *
 * Toasts are for the *result of an action*. A persistent condition belongs in
 * an Alert, and a failed data load belongs in an ErrorState. Errors do not
 * auto-dismiss, because a message that vanishes before it is read is worse
 * than no message.
 */

export type ToastVariant = "success" | "error" | "warning" | "info";

export interface Toast {
  id: string;
  title: string;
  description?: string;
  variant: ToastVariant;
  /** Milliseconds before auto-dismiss. 0 means it stays until dismissed. */
  duration: number;
}

export type ToastInput = Omit<Partial<Toast>, "id"> & { title: string };

interface ToastContextValue {
  toasts: Toast[];
  toast: (input: ToastInput) => string;
  dismiss: (id: string) => void;
}

const ToastContext = React.createContext<ToastContextValue | null>(null);

/** Access the toast queue. Must be called under `<ToastProvider>`. */
export function useToastContext(): ToastContextValue {
  const ctx = React.useContext(ToastContext);
  if (!ctx) {
    throw new Error("useToast must be used within <ToastProvider>");
  }
  return ctx;
}

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = React.useState<Toast[]>([]);
  const counter = React.useRef(0);

  const dismiss = React.useCallback((id: string) => {
    setToasts((current) => current.filter((t) => t.id !== id));
  }, []);

  const toast = React.useCallback(
    (input: ToastInput): string => {
      const variant = input.variant ?? "info";
      const id = `toast-${counter.current++}`;

      const next: Toast = {
        id,
        title: input.title,
        description: input.description,
        variant,
        // Errors persist until dismissed unless the caller overrides.
        duration: input.duration ?? (variant === "error" ? 0 : 5000),
      };

      // Cap the stack so a loop of failures cannot bury the whole screen.
      setToasts((current) => [...current.slice(-2), next]);
      return id;
    },
    []
  );

  return (
    <ToastContext.Provider value={{ toasts, toast, dismiss }}>
      {children}
      <ToastViewport toasts={toasts} onDismiss={dismiss} />
    </ToastContext.Provider>
  );
}

const ICONS: Record<ToastVariant, LucideIcon> = {
  success: CheckCircle2,
  error: XCircle,
  warning: AlertTriangle,
  info: Info,
};

const TONES: Record<ToastVariant, string> = {
  success: "text-success",
  error: "text-danger",
  warning: "text-warning",
  info: "text-info",
};

function ToastViewport({
  toasts,
  onDismiss,
}: {
  toasts: Toast[];
  onDismiss: (id: string) => void;
}) {
  const [mounted, setMounted] = React.useState(false);
  React.useEffect(() => setMounted(true), []);

  if (!mounted) return null;

  return createPortal(
    <div
      // `polite` so a toast never interrupts what a screen reader is reading.
      aria-live="polite"
      aria-atomic="false"
      className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 w-[min(24rem,calc(100vw-2rem))] pointer-events-none"
    >
      {toasts.map((t) => (
        <ToastItem key={t.id} toast={t} onDismiss={onDismiss} />
      ))}
    </div>,
    document.body
  );
}

function ToastItem({
  toast,
  onDismiss,
}: {
  toast: Toast;
  onDismiss: (id: string) => void;
}) {
  React.useEffect(() => {
    if (toast.duration <= 0) return;
    const timer = setTimeout(() => onDismiss(toast.id), toast.duration);
    return () => clearTimeout(timer);
  }, [toast.duration, toast.id, onDismiss]);

  const Icon = ICONS[toast.variant];

  return (
    <div
      role={toast.variant === "error" ? "alert" : "status"}
      className={cn(
        "pointer-events-auto flex items-start gap-3 rounded-lg border border-border",
        "bg-surface-elevated px-4 py-3 shadow-lg animate-slide-in-right"
      )}
    >
      <Icon
        className={cn("size-4.5 shrink-0 mt-0.5", TONES[toast.variant])}
        aria-hidden="true"
      />
      <div className="flex-1 min-w-0">
        <p className="text-sm font-semibold text-fg">{toast.title}</p>
        {toast.description && (
          <p className="mt-0.5 text-xs text-fg-muted leading-relaxed">
            {toast.description}
          </p>
        )}
      </div>
      <button
        type="button"
        onClick={() => onDismiss(toast.id)}
        aria-label="Dismiss notification"
        className="shrink-0 -mr-1 -mt-0.5 rounded p-1 text-fg-subtle hover:text-fg hover:bg-surface transition-colors"
      >
        <X className="size-3.5" aria-hidden="true" />
      </button>
    </div>
  );
}
