"use client";

import React, { useEffect, useRef, useState } from "react";
import { useLearningEvents } from "@/hooks/use-learning-events";
import { BookOpen, CheckCircle2, Clock } from "lucide-react";

import { Badge, Button } from "@/components/ui";
import type { ProgressReporter } from "@/hooks/use-progress-reporter";
import type { PlayerItem } from "@/types/learning";
import { Markdown } from "./markdown";

/** Share of the estimated reading time that must pass before reaching the end counts as reading. */
const MIN_READ_SHARE = 0.4;
/** Until completion, reported progress stays below the server's completion threshold. */
const PRE_COMPLETION_CAP = 89;

function scrollParentOf(element: HTMLElement | null): HTMLElement | Window {
  let node = element?.parentElement ?? null;
  while (node) {
    const overflowY = getComputedStyle(node).overflowY;
    if (overflowY === "auto" || overflowY === "scroll") return node;
    node = node.parentElement;
  }
  return window;
}

function scrollDepth(target: HTMLElement | Window): number {
  if (target instanceof Window) {
    const doc = document.documentElement;
    return (target.scrollY + target.innerHeight) / Math.max(doc.scrollHeight, 1);
  }
  return (target.scrollTop + target.clientHeight) / Math.max(target.scrollHeight, 1);
}

/** The header already shows the title; drop an identical first heading from the body. */
function withoutLeadingTitle(text: string, title: string): string {
  const match = text.match(/^\s*#{1,2}\s+(.+?)\s*(?:\r?\n|$)/);
  if (match && match[1].trim().toLowerCase() === title.trim().toLowerCase()) {
    return text.slice(match[0].length);
  }
  return text;
}

export function ArticleViewer({
  item,
  completed,
  reporter,
}: {
  item: PlayerItem;
  completed: boolean;
  reporter: ProgressReporter;
}) {
  const root = useRef<HTMLDivElement>(null);
  const text = withoutLeadingTitle(item.text_content ?? "", item.title);
  const words = text.split(/\s+/).filter(Boolean).length;
  const estimatedSeconds = item.duration_seconds > 0 ? item.duration_seconds : Math.max(60, Math.round((words / 200) * 60));

  const events = useLearningEvents();
  const announced = useRef(false);
  useEffect(() => {
    if (announced.current) return;
    announced.current = true;
    events.report("article_opened", { contentId: reporter.contentId });
  }, [events, reporter.contentId]);

  const [depth, setDepth] = useState(0);
  const engagedSeconds = useRef(0);
  const autoCompleted = useRef(completed);

  // The learner is "reading" while this lesson is open and the tab is visible.
  useEffect(() => {
    if (completed) return;
    reporter.setActive(true);
    const tick = setInterval(() => {
      if (document.visibilityState === "visible") engagedSeconds.current += 1;
    }, 1000);
    return () => {
      clearInterval(tick);
      reporter.setActive(false);
    };
  }, [reporter, completed]);

  // Track how far down the text the learner has scrolled.
  useEffect(() => {
    const target = scrollParentOf(root.current);
    const onScroll = () => {
      const value = Math.min(1, scrollDepth(target));
      setDepth((previous) => Math.max(previous, value));
      if (autoCompleted.current) return;

      reporter.update({ percent: Math.min(value * 100, PRE_COMPLETION_CAP) });
      const readLongEnough = engagedSeconds.current >= estimatedSeconds * MIN_READ_SHARE;
      if (value >= 0.98 && readLongEnough) {
        autoCompleted.current = true;
        void reporter.complete();
      }
    };
    onScroll();
    target.addEventListener("scroll", onScroll, { passive: true });
    return () => target.removeEventListener("scroll", onScroll);
  }, [reporter, estimatedSeconds]);

  const minutes = Math.max(1, Math.round(estimatedSeconds / 60));

  return (
    <article ref={root} className="mx-auto max-w-3xl">
      <header className="mb-6 border-b border-border pb-5">
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <Badge variant="info">Reading</Badge>
          <span className="flex items-center gap-1 text-xs text-fg-muted">
            <Clock className="size-3.5" aria-hidden="true" />
            {minutes} min read
          </span>
          {completed && (
            <Badge variant="success">
              <CheckCircle2 className="mr-1 size-3" aria-hidden="true" />
              Completed
            </Badge>
          )}
        </div>
        <h2 className="text-2xl font-semibold tracking-tight text-fg">{item.title}</h2>
        {item.description && <p className="mt-2 text-sm text-fg-muted">{item.description}</p>}
      </header>

      {text ? (
        <Markdown source={text} />
      ) : (
        <div className="rounded-xl border border-dashed border-border p-10 text-center text-fg-muted">
          <BookOpen className="mx-auto mb-3 size-8 opacity-50" aria-hidden="true" />
          <p className="text-sm">This reading has no text yet.</p>
        </div>
      )}

      {!completed && (
        <footer className="mt-10 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-surface p-4">
          <p className="text-sm text-fg-muted">
            {depth >= 0.98
              ? "You have reached the end."
              : "Read to the end and this will be marked complete, or mark it yourself."}
          </p>
          <Button variant="secondary" size="sm" onClick={() => void reporter.complete()}>
            <CheckCircle2 aria-hidden="true" /> Mark as complete
          </Button>
        </footer>
      )}
    </article>
  );
}
