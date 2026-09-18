"use client";

import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * Lightweight dropdown menu.
 *
 * Closes on Escape, on outside click, and after an item is chosen; supports
 * arrow-key navigation between items. Anchored to its trigger rather than
 * portalled, which is sufficient for the places it is used (topbar profile,
 * row actions) and avoids repositioning logic.
 */
export function DropdownMenu({
  trigger,
  children,
  align = "end",
  className,
  menuClassName,
}: {
  /** Receives `open` so the trigger can render a rotated chevron, etc. */
  trigger: (props: { open: boolean }) => React.ReactNode;
  children: React.ReactNode;
  align?: "start" | "end";
  className?: string;
  menuClassName?: string;
}) {
  const [open, setOpen] = React.useState(false);
  const rootRef = React.useRef<HTMLDivElement>(null);
  const menuRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    if (!open) return;

    const onPointerDown = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
        // Return focus to the trigger so keyboard flow is not lost.
        rootRef.current?.querySelector<HTMLElement>("button")?.focus();
        return;
      }

      if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
      const items = Array.from(
        menuRef.current?.querySelectorAll<HTMLElement>('[role="menuitem"]:not(:disabled)') ?? []
      );
      if (items.length === 0) return;

      event.preventDefault();
      const current = items.findIndex((i) => i === document.activeElement);
      const next =
        event.key === "ArrowDown"
          ? (current + 1) % items.length
          : (current - 1 + items.length) % items.length;
      items[next]?.focus();
    };

    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  return (
    <div ref={rootRef} className={cn("relative", className)}>
      <div onClick={() => setOpen((v) => !v)}>{trigger({ open })}</div>

      {open && (
        <div
          ref={menuRef}
          role="menu"
          onClick={() => setOpen(false)}
          className={cn(
            "absolute top-[calc(100%+0.375rem)] z-40 min-w-52 rounded-lg border border-border",
            "bg-surface-elevated shadow-lg py-1 animate-slide-up-in",
            align === "end" ? "right-0" : "left-0",
            menuClassName
          )}
        >
          {children}
        </div>
      )}
    </div>
  );
}

export function DropdownItem({
  children,
  onSelect,
  icon: Icon,
  destructive = false,
  disabled = false,
}: {
  children: React.ReactNode;
  onSelect?: () => void;
  icon?: React.ComponentType<{ className?: string }>;
  destructive?: boolean;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      role="menuitem"
      disabled={disabled}
      onClick={onSelect}
      className={cn(
        "flex w-full items-center gap-2.5 px-3 py-2 text-left text-sm transition-colors",
        "disabled:opacity-50 disabled:pointer-events-none",
        destructive
          ? "text-danger hover:bg-danger-light"
          : "text-fg-muted hover:bg-surface hover:text-fg"
      )}
    >
      {Icon && <Icon className="size-4 shrink-0" aria-hidden="true" />}
      <span className="truncate">{children}</span>
    </button>
  );
}

export function DropdownLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-fg-subtle">
      {children}
    </div>
  );
}

export function DropdownSeparator() {
  return <div role="separator" className="my-1 h-px bg-border" />;
}
