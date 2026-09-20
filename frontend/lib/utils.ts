import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * Merge Tailwind classes with conflict resolution.
 * Every component in components/ui uses this so a caller's `className`
 * reliably overrides the component's own defaults.
 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/* -------------------------------------------------------------------------- */
/* Numbers                                                                    */
/* -------------------------------------------------------------------------- */

/** Formats a 0–1 ratio as a percentage. Pass ratios, not already-scaled values. */
export function formatPercent(value: number, decimals: number = 0): string {
  return `${(value * 100).toFixed(decimals)}%`;
}

/** Thousands separators, for counts in dashboards and tables. */
export function formatNumber(value: number): string {
  return new Intl.NumberFormat("en-US").format(value);
}

/** Compact form for large counts — 1.2k, 3.4M. */
export function formatCompact(value: number): string {
  return new Intl.NumberFormat("en-US", {
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(value);
}

/** "3 learners" / "1 learner" — avoids "1 learners" in generated copy. */
export function pluralize(count: number, singular: string, plural?: string): string {
  const word = count === 1 ? singular : (plural ?? `${singular}s`);
  return `${formatNumber(count)} ${word}`;
}

/* -------------------------------------------------------------------------- */
/* Dates and durations                                                        */
/* -------------------------------------------------------------------------- */

export function formatDate(date: string | Date): string {
  return new Date(date).toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export function formatDateTime(date: string | Date): string {
  return new Date(date).toLocaleString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/**
 * "just now", "12m ago", "3d ago", then an absolute date past a week.
 * Relative time stops being useful once it is older than a few days.
 */
export function formatRelativeTime(date: string | Date): string {
  const then = new Date(date).getTime();
  const seconds = Math.floor((Date.now() - then) / 1000);

  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86_400) return `${Math.floor(seconds / 3600)}h ago`;
  if (seconds < 604_800) return `${Math.floor(seconds / 86_400)}d ago`;
  return formatDate(date);
}

/** Seconds to "8h 30m" / "12m 05s" — used for lesson and course durations. */
export function formatDuration(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return "—";

  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const secs = Math.floor(seconds % 60);

  if (hours > 0) return `${hours}h ${minutes}m`;
  if (minutes > 0) return `${minutes}m ${String(secs).padStart(2, "0")}s`;
  return `${secs}s`;
}

/** Minutes to "42 min" / "1 h" / "8 h 30 min" — for course and module lengths. */
export function formatMinutes(minutes: number): string {
  if (!Number.isFinite(minutes) || minutes < 0) return "—";
  const total = Math.round(minutes);
  const hours = Math.floor(total / 60);
  const rest = total % 60;
  if (hours === 0) return `${rest} min`;
  return rest === 0 ? `${hours} h` : `${hours} h ${rest} min`;
}

/** Playback position as "04:12" / "1:04:12". */
export function formatTimecode(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return "0:00";

  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const secs = Math.floor(seconds % 60);
  const pad = (n: number) => String(n).padStart(2, "0");

  return hours > 0
    ? `${hours}:${pad(minutes)}:${pad(secs)}`
    : `${minutes}:${pad(secs)}`;
}

/* -------------------------------------------------------------------------- */
/* Strings                                                                    */
/* -------------------------------------------------------------------------- */

export function capitalize(str: string): string {
  if (!str) return str;
  return str.charAt(0).toUpperCase() + str.slice(1);
}

/** "spark_transformations" / "SPARK-TRANSFORMATIONS" → "Spark Transformations". */
export function titleFromSlug(slug: string): string {
  return slug
    .replace(/[_-]+/g, " ")
    .toLowerCase()
    .split(" ")
    .filter(Boolean)
    .map(capitalize)
    .join(" ");
}

/** Up to two initials from a full name, for avatar fallbacks. */
export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

/** Truncates on a word boundary rather than mid-word. */
export function truncate(text: string, maxLength: number): string {
  if (text.length <= maxLength) return text;
  const cut = text.slice(0, maxLength);
  const lastSpace = cut.lastIndexOf(" ");
  return `${lastSpace > maxLength * 0.6 ? cut.slice(0, lastSpace) : cut}…`;
}

/* -------------------------------------------------------------------------- */
/* Domain presentation                                                        */
/* -------------------------------------------------------------------------- */

/** Token classes for a risk level. Matches `learner_risks.risk_level`. */
export function getRiskColor(level: string): string {
  switch (level.toLowerCase()) {
    case "critical":
      return "text-danger bg-danger-light border-danger-border";
    case "high":
      return "text-warning bg-warning-light border-warning-border";
    case "medium":
      return "text-warning bg-warning-light border-warning-border";
    case "low":
      return "text-success bg-success-light border-success-border";
    default:
      return "text-fg-muted bg-surface border-border";
  }
}

/** Text colour for a 0–1 mastery probability. Bands match components/ui/progress. */
export function getMasteryColor(mastery: number): string {
  if (mastery >= 0.8) return "text-mastery-high";
  if (mastery >= 0.6) return "text-mastery-medium";
  if (mastery >= 0.4) return "text-mastery-low";
  return "text-mastery-critical";
}

/** Presentation for a competency trend. Matches `learner_competencies.trend`. */
export function getTrendLabel(trend: string): {
  label: string;
  color: string;
  icon: string;
} {
  switch (trend) {
    case "improving":
      return { label: "Improving", color: "text-success", icon: "↑" };
    case "declining":
      return { label: "Declining", color: "text-danger", icon: "↓" };
    default:
      return { label: "Stable", color: "text-fg-subtle", icon: "→" };
  }
}
