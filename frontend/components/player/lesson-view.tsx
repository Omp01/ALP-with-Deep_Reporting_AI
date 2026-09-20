"use client";

import React, { useEffect, useRef, useState } from "react";
import { CloudOff } from "lucide-react";

import { ContentRenderer } from "@/components/content/content-renderer";
import { useLearningEvents } from "@/hooks/use-learning-events";
import { useProgressReporter } from "@/hooks/use-progress-reporter";
import type { ContentProgressResult, PlayerPayload } from "@/types/learning";

/**
 * One lesson, presented and tracked. The page mounts this with `key={item.id}` so
 * that switching lessons discards the previous lesson's player and progress state.
 */
export function LessonView({
  payload,
  onProgress,
  onServerCompleted,
  onContinue,
  openedVia = "direct",
}: {
  payload: PlayerPayload;
  /** The learner's progress on this item changed (a heartbeat or completion was saved). */
  onProgress: (result: ContentProgressResult) => void;
  /** The server completed the item (quiz passed, assignment handed in): refresh everything. */
  onServerCompleted: () => void;
  onContinue: () => void;
  /** How the learner got here, for the `lesson_opened` event. */
  openedVia?: "outline" | "resume" | "next" | "recommendation" | "direct";
}) {
  const { item, progress } = payload;
  const [completedNow, setCompletedNow] = useState(false);

  // One `lesson_opened` per time this lesson is shown (the page remounts this component per lesson).
  const events = useLearningEvents();
  const announced = useRef(false);
  useEffect(() => {
    if (announced.current) return;
    announced.current = true;
    events.report("lesson_opened", { contentId: item.id }, { source: openedVia });
  }, [events, item.id, openedVia]);

  const { reporter, saveFailed } = useProgressReporter(
    item.id,
    { status: progress.status, percent: progress.progress_percent },
    (result) => {
      if (result.status === "completed") setCompletedNow(true);
      onProgress(result);
    }
  );

  const completed = progress.status === "completed" || completedNow;

  return (
    <div className="space-y-4">
      {saveFailed && (
        <p role="status" className="mx-auto flex max-w-4xl items-center gap-2 rounded-lg bg-warning-light px-3 py-2 text-xs text-fg">
          <CloudOff className="size-3.5 text-warning" aria-hidden="true" />
          Your progress could not be saved just now. We will keep trying while this page is open.
        </p>
      )}
      <ContentRenderer
        item={item}
        completed={completed}
        initialPercent={progress.progress_percent}
        positionSeconds={progress.position_seconds}
        reporter={reporter}
        onAssignmentSubmitted={onServerCompleted}
        onQuizGraded={onServerCompleted}
        onContinue={onContinue}
      />
    </div>
  );
}
