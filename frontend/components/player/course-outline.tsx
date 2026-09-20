"use client";

import React, { useState } from "react";
import {
  CheckCircle2,
  ChevronDown,
  Code2,
  FileText,
  Headphones,
  HelpCircle,
  PlayCircle,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { cn, formatDuration } from "@/lib/utils";
import type { ItemSummary, ModuleOverview } from "@/types/learning";

/** The icon that says what kind of thing a lesson item is. */
export function itemIcon(item: Pick<ItemSummary, "content_type" | "kind">): LucideIcon {
  if (item.kind === "assessment") return HelpCircle;
  if (item.kind === "assignment") return Code2;
  switch (item.content_type.toUpperCase()) {
    case "VIDEO":
      return PlayCircle;
    case "AUDIO":
      return Headphones;
    default:
      return FileText;
  }
}

export function itemKindLabel(item: Pick<ItemSummary, "content_type" | "kind">): string {
  if (item.kind === "assessment") return "Quiz";
  if (item.kind === "assignment") return "Assignment";
  switch (item.content_type.toUpperCase()) {
    case "VIDEO":
      return "Video";
    case "AUDIO":
      return "Audio";
    case "DOCUMENT":
      return "Document";
    default:
      return "Reading";
  }
}

/**
 * The course contents list: modules, their items, and where the learner is.
 * Used by the player, beside the lesson.
 */
export function CourseOutline({
  modules,
  activeId,
  onSelect,
}: {
  modules: ModuleOverview[];
  activeId: string | null;
  onSelect: (itemId: string) => void;
}) {
  const activeModuleId = modules.find((m) => m.items.some((i) => i.id === activeId))?.id;
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());

  const toggle = (moduleId: string) =>
    setCollapsed((previous) => {
      const next = new Set(previous);
      if (next.has(moduleId)) next.delete(moduleId);
      else next.add(moduleId);
      return next;
    });

  return (
    <nav aria-label="Course contents" className="space-y-1">
      {modules.map((module, index) => {
        const open = !collapsed.has(module.id) || module.id === activeModuleId;
        return (
          <section key={module.id}>
            <button
              type="button"
              onClick={() => toggle(module.id)}
              aria-expanded={open}
              className="flex w-full items-start gap-2 rounded-lg px-2 py-2 text-left hover:bg-surface focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary"
            >
              <ChevronDown
                className={cn("mt-0.5 size-4 shrink-0 text-fg-subtle transition-transform", !open && "-rotate-90")}
                aria-hidden="true"
              />
              <span className="min-w-0 flex-1">
                <span className="block text-sm font-medium leading-snug text-fg">
                  {index + 1}. {module.title.replace(/^Module\s+\d+:\s*/i, "")}
                </span>
                <span className="text-xs text-fg-muted">
                  {module.completed_items}/{module.total_items} complete
                </span>
              </span>
            </button>

            {open && (
              <ul className="mb-2 ml-3 space-y-0.5 border-l border-border pl-2">
                {module.items.map((item) => {
                  const Icon = itemIcon(item);
                  const active = item.id === activeId;
                  const done = item.progress_status === "completed";
                  return (
                    <li key={item.id}>
                      <button
                        type="button"
                        onClick={() => onSelect(item.id)}
                        aria-current={active ? "true" : undefined}
                        className={cn(
                          "flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-left text-sm transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary",
                          active ? "bg-primary-light font-medium text-primary" : "text-fg hover:bg-surface"
                        )}
                      >
                        {done ? (
                          <CheckCircle2 className="size-4 shrink-0 text-success" aria-label="Completed" />
                        ) : (
                          <Icon
                            className={cn(
                              "size-4 shrink-0",
                              item.progress_status === "in_progress" ? "text-primary" : "text-fg-subtle"
                            )}
                            aria-hidden="true"
                          />
                        )}
                        <span className="min-w-0 flex-1 truncate">{item.title}</span>
                        {item.duration_seconds > 0 && (
                          <span className="shrink-0 text-xs text-fg-muted">{formatDuration(item.duration_seconds)}</span>
                        )}
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </section>
        );
      })}
    </nav>
  );
}
