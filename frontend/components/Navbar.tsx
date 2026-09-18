"use client";

/**
 * @deprecated Use `<AppShell>` from `@/components/shell`, which renders the
 * header, the navigation rail, and the content well as one frame.
 *
 * This file is retained so the pages written before the shell existed keep
 * working unchanged — they compose `<Navbar />` and `<Sidebar />` themselves.
 * It now delegates to `<Topbar>`, so those pages pick up the fixes that came
 * with it: the organisation name is read from the session instead of falling
 * back to a hardcoded "Acme Corporation", the profile menu is keyboard
 * operable, and sign-out clears the session through one code path.
 *
 * Remove this wrapper once every page has moved to `<AppShell>` (Phases 3–12).
 */

import { Topbar } from "@/components/shell/topbar";

export function Navbar() {
  return <Topbar />;
}

export default Navbar;
