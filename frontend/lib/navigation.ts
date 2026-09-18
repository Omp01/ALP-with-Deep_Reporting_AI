/**
 * Role-aware information architecture.
 *
 * This is the single definition of what each role can navigate to. The Sidebar
 * and the mobile nav both render from it, so navigation can never drift between
 * surfaces, and adding a route is a one-line change here.
 *
 * `status` is deliberate. The full target IA is declared up front, but items
 * whose route does not exist yet are marked `planned` and are NOT rendered —
 * a nav link that 404s is a broken flow, and showing a greyed-out "coming soon"
 * row would advertise a feature the product does not have. Each planned item
 * records the phase that delivers it; that phase flips the flag to `ready`.
 *
 * Navigation is a convenience layer, never a security boundary. The backend
 * re-checks role and tenant on every request (services/api/app/api/deps.py).
 */

import type { LucideIcon } from "lucide-react";
import {
  Home,
  BookOpen,
  Compass,
  Route,
  ClipboardCheck,
  TrendingUp,
  Target,
  Sparkles,
  User,
  LayoutDashboard,
  Users,
  UsersRound,
  AlertTriangle,
  FileText,
  Library,
  FileStack,
  BarChart3,
  Brain,
  Settings,
} from "lucide-react";

import { isAdminRole, isManagerRole, type Role } from "./auth";

export type NavStatus = "ready" | "planned";

export interface NavItem {
  label: string;
  href: string;
  icon: LucideIcon;
  status: NavStatus;
  /** Phase that delivers this route. Present only while `status` is "planned". */
  phase?: number;
  /** Short hint shown as the link's title attribute. */
  description?: string;
}

export interface NavSection {
  /** Section heading. `null` renders the items without a heading. */
  title: string | null;
  items: NavItem[];
}

/* -------------------------------------------------------------------------- */
/* Learner                                                                    */
/* -------------------------------------------------------------------------- */

const LEARNER_NAV: NavSection[] = [
  {
    title: null,
    items: [
      {
        label: "Home",
        href: "/learner/dashboard",
        icon: Home,
        status: "ready",
        description: "Your learning at a glance",
      },
      {
        label: "My Learning",
        href: "/learner/my-learning",
        icon: BookOpen,
        status: "planned",
        phase: 3,
      },
      {
        label: "Explore Courses",
        href: "/explore",
        icon: Compass,
        status: "planned",
        phase: 3,
      },
      {
        label: "Learning Paths",
        href: "/learner/paths",
        icon: Route,
        status: "planned",
        phase: 3,
      },
    ],
  },
  {
    title: "Practice",
    items: [
      {
        label: "Continue Learning",
        href: "/learner/learning",
        icon: Compass,
        status: "ready",
        description: "Resume your adaptive session",
      },
      {
        label: "Assessments",
        href: "/learner/assessments",
        icon: ClipboardCheck,
        status: "planned",
        phase: 4,
      },
    ],
  },
  {
    title: "Your progress",
    items: [
      {
        label: "Progress",
        href: "/learner/progress",
        icon: TrendingUp,
        status: "planned",
        phase: 9,
      },
      {
        label: "Competencies",
        href: "/learner/competencies",
        icon: Target,
        status: "planned",
        phase: 6,
      },
      {
        label: "AI Insights",
        href: "/learner/insights",
        icon: Sparkles,
        status: "ready",
        description: "Evidence-grounded insights on your learning",
      },
    ],
  },
  {
    title: "Account",
    items: [
      {
        label: "Profile",
        href: "/learner/profile",
        icon: User,
        status: "planned",
        phase: 14,
      },
    ],
  },
];

/* -------------------------------------------------------------------------- */
/* Manager                                                                    */
/* -------------------------------------------------------------------------- */

const MANAGER_NAV: NavSection[] = [
  {
    title: null,
    items: [
      {
        label: "Dashboard",
        href: "/manager/dashboard",
        icon: LayoutDashboard,
        status: "ready",
        description: "Team learning overview",
      },
      {
        label: "My Team",
        href: "/manager/team",
        icon: Users,
        status: "planned",
        phase: 9,
      },
      {
        label: "Learners",
        href: "/manager/learners",
        icon: UsersRound,
        status: "planned",
        phase: 9,
      },
    ],
  },
  {
    title: "Performance",
    items: [
      {
        label: "Team Progress",
        href: "/manager/progress",
        icon: TrendingUp,
        status: "planned",
        phase: 9,
      },
      {
        label: "Competencies",
        href: "/manager/competencies",
        icon: Target,
        status: "planned",
        phase: 9,
      },
      {
        label: "At-Risk Learners",
        href: "/manager/at-risk",
        icon: AlertTriangle,
        status: "planned",
        phase: 9,
      },
    ],
  },
  {
    title: "Reporting",
    items: [
      {
        label: "Reports",
        href: "/manager/reports",
        icon: FileText,
        status: "ready",
        description: "Grounded team reports and digests",
      },
      {
        label: "AI Insights",
        href: "/manager/insights",
        icon: Sparkles,
        status: "planned",
        phase: 11,
      },
    ],
  },
];

/* -------------------------------------------------------------------------- */
/* Admin / L&D                                                                */
/* -------------------------------------------------------------------------- */

const ADMIN_NAV: NavSection[] = [
  {
    title: null,
    items: [
      {
        label: "Dashboard",
        href: "/admin/dashboard",
        icon: LayoutDashboard,
        status: "ready",
        description: "Organisation-wide learning analytics",
      },
    ],
  },
  {
    title: "Content",
    items: [
      {
        label: "Courses",
        href: "/admin/courses",
        icon: Library,
        status: "planned",
        phase: 12,
      },
      {
        label: "Content",
        href: "/admin/content",
        icon: FileStack,
        status: "planned",
        phase: 12,
      },
      {
        label: "Assessments",
        href: "/admin/assessments",
        icon: ClipboardCheck,
        status: "planned",
        phase: 12,
      },
      {
        label: "Competencies",
        href: "/admin/competencies",
        icon: Target,
        status: "planned",
        phase: 12,
      },
    ],
  },
  {
    title: "Organisation",
    items: [
      {
        label: "Users",
        href: "/admin/users",
        icon: Users,
        status: "planned",
        phase: 12,
      },
      {
        label: "Analytics",
        href: "/admin/analytics",
        icon: BarChart3,
        status: "planned",
        phase: 9,
      },
      {
        label: "Reporting AI",
        href: "/admin/reporting-ai",
        icon: Brain,
        status: "planned",
        phase: 11,
      },
      {
        label: "Settings",
        href: "/admin/settings",
        icon: Settings,
        status: "planned",
        phase: 14,
      },
    ],
  },
];

/* -------------------------------------------------------------------------- */
/* Resolution                                                                 */
/* -------------------------------------------------------------------------- */

/**
 * The navigation a role sees.
 *
 * Admins and managers get their own IA — not the learner IA with extra rows
 * bolted on. The previous Sidebar rendered the learner links to every role
 * unconditionally, which made an admin's primary surface look like a learner's.
 *
 * @param includePlanned  Render not-yet-built routes too. Off in the product;
 *                        useful in development to see the target IA.
 */
export function navigationForRole(
  role: Role | null | undefined,
  includePlanned = false
): NavSection[] {
  let sections: NavSection[];

  if (isAdminRole(role)) sections = ADMIN_NAV;
  else if (isManagerRole(role)) sections = MANAGER_NAV;
  else sections = LEARNER_NAV;

  if (includePlanned) return sections;

  return sections
    .map((section) => ({
      ...section,
      items: section.items.filter((item) => item.status === "ready"),
    }))
    .filter((section) => section.items.length > 0);
}

/**
 * Whether `href` should render as the current page.
 *
 * Exact match for index routes, prefix match otherwise, so that a nested route
 * such as /admin/courses/:id keeps "Courses" highlighted.
 */
export function isActiveRoute(pathname: string, href: string): boolean {
  if (pathname === href) return true;
  return pathname.startsWith(`${href}/`);
}

/** Flat list of every declared route, for tests and the roadmap docs. */
export function allNavItems(): NavItem[] {
  return [...LEARNER_NAV, ...MANAGER_NAV, ...ADMIN_NAV].flatMap((s) => s.items);
}
