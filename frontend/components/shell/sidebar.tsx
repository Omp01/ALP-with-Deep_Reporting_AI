"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { GraduationCap, X } from "lucide-react";

import { cn } from "@/lib/utils";
import { isActiveRoute, navigationForRole } from "@/lib/navigation";
import { useAuth } from "@/hooks/use-auth";
import { Button } from "@/components/ui/button";

/**
 * Primary navigation rail.
 *
 * Renders from `lib/navigation.ts`, so each role gets its own IA rather than
 * the learner's menu with extra rows appended — the previous sidebar showed
 * learner links to every role, which made an administrator's primary surface
 * look like a learner's.
 *
 * Below `lg` it becomes an off-canvas drawer driven by `open`/`onClose`.
 */
export function Sidebar({
  open = false,
  onClose,
  variant = "overlay",
}: {
  open?: boolean;
  onClose?: () => void;
  /**
   * `overlay` — off-canvas below `lg`, sticky rail above. Used by AppShell.
   * `static`  — always in flow, no scrim. Used by pages that render their own
   *             header above the sidebar rather than beside it.
   */
  variant?: "overlay" | "static";
}) {
  const pathname = usePathname();
  const { role, ready } = useAuth();

  const sections = React.useMemo(() => navigationForRole(role), [role]);

  // Close the mobile drawer whenever navigation succeeds, otherwise it stays
  // open over the page the user just chose.
  React.useEffect(() => {
    onClose?.();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- fire on route change only
  }, [pathname]);

  return (
    <>
      {/* Scrim — mobile only */}
      {variant === "overlay" && open && (
        <div
          className="fixed inset-0 z-40 bg-slate-900/40 lg:hidden"
          onClick={onClose}
          aria-hidden="true"
        />
      )}

      <aside
        id="primary-navigation"
        className={cn(
          "flex w-64 shrink-0 flex-col bg-sidebar-bg",
          variant === "overlay"
            ? [
                "fixed inset-y-0 left-0 z-50 transition-transform duration-200",
                "lg:sticky lg:top-0 lg:h-dvh lg:translate-x-0",
                open ? "translate-x-0" : "-translate-x-full",
              ]
            : "hidden self-stretch lg:flex"
        )}
      >
        {/* Brand */}
        <div className="flex h-16 items-center justify-between gap-2 px-5 shrink-0">
          <Link
            href="/"
            className="flex items-center gap-2.5 min-w-0"
            aria-label="Adaptive LMS home"
          >
            <span
              className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-sidebar-accent text-white"
              aria-hidden="true"
            >
              <GraduationCap className="size-4.5" />
            </span>
            <span className="truncate text-[15px] font-semibold tracking-tight text-sidebar-text-active">
              Adaptive LMS
            </span>
          </Link>

          {variant === "overlay" && (
            <Button
              variant="ghost"
              size="icon"
              onClick={onClose}
              aria-label="Close navigation"
              className="lg:hidden text-sidebar-text hover:bg-sidebar-hover hover:text-sidebar-text-active"
            >
              <X aria-hidden="true" />
            </Button>
          )}
        </div>

        {/* Navigation */}
        <nav
          aria-label="Primary"
          className="flex-1 overflow-y-auto px-3 pb-4 space-y-6"
        >
          {/* Rendering nothing until the session resolves avoids briefly showing
              the learner menu to an administrator on first paint. */}
          {ready &&
            sections.map((section, index) => (
              <div key={section.title ?? `section-${index}`}>
                {section.title && (
                  <h2 className="px-3 pb-2 text-[11px] font-semibold uppercase tracking-wider text-sidebar-text-subtle">
                    {section.title}
                  </h2>
                )}
                <ul className="space-y-0.5">
                  {section.items.map((item) => {
                    const active = isActiveRoute(pathname, item.href);
                    const Icon = item.icon;

                    return (
                      <li key={item.href}>
                        <Link
                          href={item.href}
                          title={item.description}
                          aria-current={active ? "page" : undefined}
                          className={cn(
                            "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                            active
                              ? "bg-sidebar-accent text-white"
                              : "text-sidebar-text hover:bg-sidebar-hover hover:text-sidebar-text-active"
                          )}
                        >
                          <Icon
                            className={cn(
                              "size-4 shrink-0",
                              active ? "text-white" : "text-sidebar-text-subtle"
                            )}
                            aria-hidden="true"
                          />
                          <span className="truncate">{item.label}</span>
                        </Link>
                      </li>
                    );
                  })}
                </ul>
              </div>
            ))}
        </nav>
      </aside>
    </>
  );
}
