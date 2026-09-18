import Link from "next/link";
import { Compass, SearchX } from "lucide-react";

import { buttonVariants } from "@/components/ui/button-variants";

/**
 * 404. Offers a route forward rather than leaving the user at a dead end —
 * and never pretends the page exists.
 */
export default function NotFound() {
  return (
    <div className="flex min-h-dvh items-center justify-center bg-surface px-4">
      <div className="w-full max-w-md rounded-xl border border-border bg-surface-elevated p-8 text-center shadow-sm">
        <div
          className="mx-auto mb-5 flex size-12 items-center justify-center rounded-full bg-surface text-fg-subtle"
          aria-hidden="true"
        >
          <SearchX className="size-6" />
        </div>

        <p className="text-xs font-semibold uppercase tracking-wider text-fg-subtle">
          Error 404
        </p>
        <h1 className="mt-1.5 text-lg font-semibold text-fg">Page not found</h1>
        <p className="mt-2 text-sm leading-relaxed text-fg-muted">
          The page you are looking for does not exist, or you may not have access
          to it.
        </p>

        <div className="mt-6 flex flex-wrap items-center justify-center gap-2">
          <Link href="/" className={buttonVariants()}>
            <Compass className="size-4" aria-hidden="true" />
            Go home
          </Link>
        </div>
      </div>
    </div>
  );
}
