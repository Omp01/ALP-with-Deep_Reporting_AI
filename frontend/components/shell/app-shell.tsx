"use client";

import * as React from "react";

import { cn } from "@/lib/utils";
import type { Role } from "@/lib/auth";
import { AuthGuard } from "./auth-guard";
import { Sidebar } from "./sidebar";
import { Topbar } from "./topbar";

/**
 * The authenticated application frame: navigation rail, header, content well.
 *
 * Every signed-in page renders inside this. It owns the responsive behaviour
 * (rail above `lg`, drawer below), the skip link, and the `<main>` landmark,
 * so no page has to reassemble the layout — which is how the eight existing
 * pages each ended up with slightly different spacing.
 *
 *   export default function Page() {
 *     return (
 *       <AppShell roles={["manager"]}>
 *         <PageHeader title="Team" />
 *         …
 *       </AppShell>
 *     );
 *   }
 */
export function AppShell({
  children,
  roles,
  /** Controls inserted into the header — search, global filters. */
  headerContent,
  /** Removes the default padding and max-width, for full-bleed screens
   *  such as the course player. */
  bleed = false,
  className,
}: {
  children: React.ReactNode;
  roles?: Role[];
  headerContent?: React.ReactNode;
  bleed?: boolean;
  className?: string;
}) {
  const [navOpen, setNavOpen] = React.useState(false);

  return (
    <AuthGuard roles={roles}>
      <a href="#main-content" className="skip-link">
        Skip to main content
      </a>

      <div className="flex min-h-dvh bg-surface">
        <Sidebar open={navOpen} onClose={() => setNavOpen(false)} />

        {/* `min-w-0` is required: without it a wide table inside the content
            well stretches this flex child and scrolls the whole page sideways. */}
        <div className="flex min-w-0 flex-1 flex-col">
          <Topbar onMenuClick={() => setNavOpen(true)}>{headerContent}</Topbar>

          <main
            id="main-content"
            tabIndex={-1}
            className={cn(
              "flex-1 focus:outline-none",
              bleed ? "" : "mx-auto w-full max-w-7xl px-4 py-6 sm:px-6 lg:px-8",
              className
            )}
          >
            {children}
          </main>
        </div>
      </div>
    </AuthGuard>
  );
}
