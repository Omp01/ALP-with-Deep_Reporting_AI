import { useCallback, useSyncExternalStore } from "react";
import { useRouter } from "next/navigation";

import {
  clearSession,
  getSessionSnapshot,
  getServerSessionSnapshot,
  getToken,
  homeRouteForRole,
  isAdminRole,
  isLearnerRole,
  isManagerRole,
  subscribeToSession,
  type Role,
  type SessionUser,
} from "@/lib/auth";
import { useIsMounted } from "./use-is-mounted";

export interface UseAuthResult {
  user: SessionUser | null;
  role: Role | null;
  /** False until the session has been read from storage on the client. */
  ready: boolean;
  isAuthenticated: boolean;
  isLearner: boolean;
  isManager: boolean;
  isAdmin: boolean;
  logout: () => void;
  /** The route this user should land on. */
  homeRoute: string;
}

/**
 * The session, as React state via useSyncExternalStore.
 *
 * Replaces the `useEffect` + `localStorage.getItem` + `JSON.parse` block that
 * every page previously repeated. It also listens for session changes — both
 * from this tab (login, logout, a 401 clearing the token) and from other tabs
 * via the `storage` event — so signing out in one tab logs the others out too.
 */
export function useAuth(): UseAuthResult {
  const router = useRouter();
  const ready = useIsMounted();
  const user = useSyncExternalStore(
    subscribeToSession,
    getSessionSnapshot,
    getServerSessionSnapshot
  );

  const logout = useCallback(() => {
    clearSession();
    router.push("/login");
  }, [router]);

  const role = user?.role ?? null;

  return {
    user,
    role,
    ready,
    isAuthenticated: Boolean(user && getToken()),
    isLearner: isLearnerRole(role),
    isManager: isManagerRole(role),
    isAdmin: isAdminRole(role),
    logout,
    homeRoute: homeRouteForRole(role),
  };
}
