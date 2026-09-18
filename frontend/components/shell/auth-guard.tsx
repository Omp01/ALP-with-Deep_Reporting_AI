"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { ShieldAlert } from "lucide-react";

import { canAccess, homeRouteForRole, type Role } from "@/lib/auth";
import { useAuth } from "@/hooks/use-auth";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { SpinnerBlock } from "@/components/ui/spinner";

/**
 * Gates a page on being signed in, and optionally on holding a role.
 *
 * This is a convenience and a UX affordance — NOT a security boundary. Anything
 * it hides is still reachable by calling the API directly, so authorisation is
 * enforced server-side on every request by `require_roles()` and the tenant
 * dependency in services/api/app/api/deps.py. This guard exists so a user is
 * not shown a screen that will only fail once its requests return 403.
 *
 * Unauthenticated users are redirected to /login. A signed-in user who lacks
 * the role is *not* redirected — they are told plainly, and offered their own
 * home, because silently bouncing someone is confusing.
 */
export function AuthGuard({
  children,
  roles,
  fallback,
}: {
  children: React.ReactNode;
  /** Roles permitted here. Omit to require only that the user is signed in. */
  roles?: Role[];
  /** Replaces the default loading state while the session resolves. */
  fallback?: React.ReactNode;
}) {
  const router = useRouter();
  const { user, role, ready, isAuthenticated, homeRoute } = useAuth();

  React.useEffect(() => {
    if (ready && !isAuthenticated) router.replace("/login");
  }, [ready, isAuthenticated, router]);

  // Session not yet read from storage. Redirecting here would bounce every
  // signed-in user to /login on first paint.
  if (!ready) {
    return <>{fallback ?? <SpinnerBlock label="Loading your workspace" />}</>;
  }

  // Redirect is in flight; render nothing rather than a flash of the page.
  if (!isAuthenticated || !user) return null;

  if (roles && !canAccess(role, roles)) {
    return (
      <div className="mx-auto max-w-lg px-4 py-16">
        <EmptyState
          icon={ShieldAlert}
          title="You do not have access to this page"
          description="This area is restricted to a different role. If you believe you should have access, contact your organisation's administrator."
          action={
            <Button onClick={() => router.replace(homeRoute || homeRouteForRole(role))}>
              Go to my dashboard
            </Button>
          }
        />
      </div>
    );
  }

  return <>{children}</>;
}
