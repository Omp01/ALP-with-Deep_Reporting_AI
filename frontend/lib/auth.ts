/**
 * Session handling.
 *
 * Before this module existed, every page read `localStorage.getItem("user")`
 * inside its own `useEffect`, re-parsed the JSON, and re-implemented the
 * redirect-to-login check. Auth logic now lives here and is consumed through
 * the `useAuth` hook (hooks/use-auth.ts) and `<AuthGuard>`.
 *
 * NOTE ON STORAGE: the token lives in localStorage because that is what the
 * existing login flow writes and what api-client reads. That is a deliberate,
 * documented trade-off, not an oversight — it is XSS-exposed, and moving to an
 * httpOnly refresh cookie is tracked as a known limitation. Do not add new
 * reads of these keys outside this file.
 */

/** Roles as the backend actually defines them (services/api/app/models/user.py). */
export const ROLES = [
  "system_admin",
  "org_admin",
  "instructor",
  "manager",
  "learner",
] as const;

export type Role = (typeof ROLES)[number];

export interface SessionOrganization {
  id: string;
  name: string;
  slug: string;
  is_active: boolean;
}

/** Mirrors UserProfileResponse in services/api/app/schemas/auth.py. */
export interface SessionUser {
  id: string;
  org_id: string;
  email: string;
  full_name: string;
  role: Role;
  avatar_url?: string | null;
  is_active: boolean;
  created_at?: string;
  organization?: SessionOrganization | null;
  teams?: string[];
}

const TOKEN_KEY = "access_token";
const USER_KEY = "user";

/** Fired on the window whenever the stored session changes in this tab. */
export const SESSION_CHANGED_EVENT = "alms:session-changed";

function isBrowser(): boolean {
  return typeof window !== "undefined";
}

function notifySessionChanged(): void {
  if (isBrowser()) {
    window.dispatchEvent(new Event(SESSION_CHANGED_EVENT));
  }
}

export function getToken(): string | null {
  if (!isBrowser()) return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function getSessionUser(): SessionUser | null {
  if (!isBrowser()) return null;
  const raw = window.localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as SessionUser;
    // A stored blob with no role is unusable; treat it as no session at all
    // rather than letting downstream code branch on `undefined`.
    return parsed && typeof parsed.role === "string" ? parsed : null;
  } catch {
    return null;
  }
}

export function setSession(token: string, user: SessionUser): void {
  if (!isBrowser()) return;
  window.localStorage.setItem(TOKEN_KEY, token);
  window.localStorage.setItem(USER_KEY, JSON.stringify(user));
  notifySessionChanged();
}

export function clearSession(): void {
  if (!isBrowser()) return;
  window.localStorage.removeItem(TOKEN_KEY);
  window.localStorage.removeItem(USER_KEY);
  notifySessionChanged();
}

export function isAuthenticated(): boolean {
  return Boolean(getToken() && getSessionUser());
}

/* -------------------------------------------------------------------------- */
/* External store — lets React subscribe to the session                       */
/* -------------------------------------------------------------------------- */

/**
 * `useSyncExternalStore` compares snapshots by identity and re-renders on every
 * change. `getSessionUser()` parses JSON afresh on each call, so it returns a
 * new object every time and would loop forever. These cache the parsed value
 * against the raw string and only produce a new object when the raw string
 * actually changes.
 */
let cachedRaw: string | null = null;
let cachedUser: SessionUser | null = null;

export function getSessionSnapshot(): SessionUser | null {
  if (!isBrowser()) return null;

  const raw = window.localStorage.getItem(USER_KEY);
  if (raw === cachedRaw) return cachedUser;

  cachedRaw = raw;
  cachedUser = getSessionUser();
  return cachedUser;
}

/** Server snapshot. Storage does not exist during the server render. */
export function getServerSessionSnapshot(): SessionUser | null {
  return null;
}

/** Subscribes to session changes in this tab and, via `storage`, in others. */
export function subscribeToSession(onChange: () => void): () => void {
  if (!isBrowser()) return () => {};

  window.addEventListener(SESSION_CHANGED_EVENT, onChange);
  window.addEventListener("storage", onChange);
  return () => {
    window.removeEventListener(SESSION_CHANGED_EVENT, onChange);
    window.removeEventListener("storage", onChange);
  };
}

/* -------------------------------------------------------------------------- */
/* Role predicates                                                            */
/* -------------------------------------------------------------------------- */

/**
 * Admin-tier roles. `system_admin` is the cross-tenant superuser and inherits
 * every permission, matching `require_roles()` in services/api/app/api/deps.py.
 */
export function isAdminRole(role?: Role | null): boolean {
  return role === "org_admin" || role === "system_admin";
}

/** Manager-tier. Instructors see the same team surfaces as managers. */
export function isManagerRole(role?: Role | null): boolean {
  return role === "manager" || role === "instructor";
}

export function isLearnerRole(role?: Role | null): boolean {
  return role === "learner";
}

/**
 * Whether a role may reach a surface gated to `required`.
 *
 * Admins inherit manager surfaces, and every role may use learner surfaces
 * (an admin can still take a course). This mirrors the backend's role
 * hierarchy — it does not replace it. The server re-checks every request;
 * this only decides what the navigation offers.
 */
export function canAccess(role: Role | null | undefined, required: Role[]): boolean {
  if (!role) return false;
  if (role === "system_admin") return true;
  if (required.includes(role)) return true;
  if (required.includes("manager") && isAdminRole(role)) return true;
  return false;
}

/** Where a role lands after login, and where "home" points for them. */
export function homeRouteForRole(role?: Role | null): string {
  if (isAdminRole(role)) return "/admin/dashboard";
  if (isManagerRole(role)) return "/manager/dashboard";
  return "/learner/dashboard";
}

/** Human-readable role name for badges and profile chips. */
export function roleLabel(role?: Role | null): string {
  switch (role) {
    case "system_admin":
      return "System Admin";
    case "org_admin":
      return "Administrator";
    case "instructor":
      return "Instructor";
    case "manager":
      return "Manager";
    case "learner":
      return "Learner";
    default:
      return "Guest";
  }
}
