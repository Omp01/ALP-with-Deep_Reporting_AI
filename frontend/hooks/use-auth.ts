"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import {
  SESSION_CHANGED_EVENT,
  clearSession,
  getSessionUser,
  getToken,
  homeRouteForRole,
  isAdminRole,
  isLearnerRole,
  isManagerRole,
  type Role,
  type SessionUser,
} from "@/lib/auth";

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
 * The session, as React state.
 *
 * Replaces the `useEffect` + `localStorage.getItem` + `JSON.parse` block that
 * every page previously repeated. It also listens for session changes — both
 * from this tab (login, logout, a 401 clearing the token) and from other tabs
 * via the `storage` event — so signing out in one tab logs the others out too.
 *
 * `ready` exists because storage is unavailable during the server render. A
 * component that redirects on `!user` without checking `ready` will bounce
 * every authenticated user to /login on first paint.
 */
export function useAuth(): UseAuthResult {
  const router = useRouter();
  const [user, setUser] = useState<SessionUser | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const sync = () => setUser(getSessionUser());

    sync();
    setReady(true);

    window.addEventListener(SESSION_CHANGED_EVENT, sync);
    window.addEventListener("storage", sync);
    return () => {
      window.removeEventListener(SESSION_CHANGED_EVENT, sync);
      window.removeEventListener("storage", sync);
    };
  }, []);

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
