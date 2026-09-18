"use client";

/**
 * @deprecated Use `<AppShell>` from `@/components/shell`.
 *
 * Retained so pages written before the shell existed keep working. It renders
 * the shell's sidebar in `static` mode, which sits in the flow beside a page's
 * own `<main>` the way the original component did.
 *
 * Delegating here fixes two defects those pages inherited from the old
 * sidebar: the learner menu was rendered to every role, so an administrator's
 * primary navigation led with learner surfaces; and the link set was hardcoded
 * in this file rather than resolved from `lib/navigation.ts`.
 *
 * Remove this wrapper once every page has moved to `<AppShell>` (Phases 3–12).
 */

import { Sidebar as ShellSidebar } from "@/components/shell/sidebar";

export function Sidebar() {
  return <ShellSidebar variant="static" />;
}

export default Sidebar;
