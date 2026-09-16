import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * Merge Tailwind CSS classes with conflict resolution.
 * Used throughout the component library.
 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * Format a number as a percentage string.
 */
export function formatPercent(value: number, decimals: number = 0): string {
  return `${(value * 100).toFixed(decimals)}%`;
}

/**
 * Format a date as a human-readable string.
 */
export function formatDate(date: string | Date): string {
  return new Date(date).toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

/**
 * Format a date with time.
 */
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
 * Capitalize the first letter of a string.
 */
export function capitalize(str: string): string {
  return str.charAt(0).toUpperCase() + str.slice(1);
}

/**
 * Get the color for a risk level.
 */
export function getRiskColor(level: string): string {
  switch (level.toLowerCase()) {
    case "critical":
      return "text-red-700 bg-red-50 border-red-200";
    case "high":
      return "text-orange-700 bg-orange-50 border-orange-200";
    case "medium":
      return "text-yellow-700 bg-yellow-50 border-yellow-200";
    case "low":
      return "text-green-700 bg-green-50 border-green-200";
    default:
      return "text-gray-700 bg-gray-50 border-gray-200";
  }
}

/**
 * Get the color for a mastery value.
 */
export function getMasteryColor(mastery: number): string {
  if (mastery >= 0.8) return "text-emerald-600";
  if (mastery >= 0.6) return "text-blue-600";
  if (mastery >= 0.4) return "text-yellow-600";
  return "text-red-600";
}

/**
 * Get the label for a trend direction.
 */
export function getTrendLabel(trend: string): { label: string; color: string; icon: string } {
  switch (trend) {
    case "improving":
      return { label: "Improving", color: "text-emerald-600", icon: "↑" };
    case "declining":
      return { label: "Declining", color: "text-red-600", icon: "↓" };
    default:
      return { label: "Stable", color: "text-gray-500", icon: "→" };
  }
}
