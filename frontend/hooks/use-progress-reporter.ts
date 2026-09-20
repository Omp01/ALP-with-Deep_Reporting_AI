"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { learningService } from "@/services";
import type { ContentProgressResult, ProgressStatus } from "@/types/learning";

/** How often a heartbeat is sent while the learner is actively engaged. */
const HEARTBEAT_MS = 15_000;

export interface ProgressReporter {
  /** The lesson item this reporter tracks. */
  contentId: string;
  /** Tell the reporter the learner is (or is no longer) actively engaged, e.g. video playing. */
  setActive: (active: boolean) => void;
  /** Cheap; store the latest percent / position so the next heartbeat carries them. */
  update: (state: { percent?: number; position?: number }) => void;
  /** Report immediately that the item is complete. */
  complete: () => Promise<void>;
  /** Report the latest state immediately (e.g. on pause or before leaving). */
  flush: () => Promise<void>;
}

/**
 * Reports a learner's progress on one lesson item, truthfully.
 *
 * Time is counted only while (a) the caller says the learner is engaged and (b) the
 * tab is visible; each report carries the seconds accumulated since the previous
 * one. The server independently caps that figure, but the client does not inflate it
 * in the first place. A failed report keeps its seconds for the next attempt and is
 * surfaced through `saveFailed` rather than being swallowed.
 *
 * `reporter` is referentially stable for a given item, so a player can depend on it
 * without being rebuilt on every render.
 */
export function useProgressReporter(
  contentId: string,
  initial: { status: ProgressStatus; percent: number },
  onResult?: (result: ContentProgressResult) => void
): { reporter: ProgressReporter; saveFailed: boolean } {
  const [saveFailed, setSaveFailed] = useState(false);

  const active = useRef(false);
  const pendingSeconds = useRef(0);
  const latest = useRef<{ percent: number; position?: number }>({ percent: initial.percent });
  const completed = useRef(initial.status === "completed");
  const inFlight = useRef(false);
  const onResultRef = useRef(onResult);

  useEffect(() => {
    onResultRef.current = onResult;
  });

  const send = useCallback(
    async (forceComplete: boolean) => {
      if (inFlight.current && !forceComplete) return;
      inFlight.current = true;
      const seconds = pendingSeconds.current;
      pendingSeconds.current = 0;
      const percent = forceComplete ? 100 : latest.current.percent;
      try {
        const result = await learningService.reportProgress(contentId, {
          status: forceComplete || completed.current ? "completed" : "in_progress",
          progress_percent: percent,
          time_spent_seconds: Math.round(seconds),
          position_seconds: latest.current.position,
        });
        if (result.status === "completed") completed.current = true;
        setSaveFailed(false);
        onResultRef.current?.(result);
      } catch {
        pendingSeconds.current += seconds; // keep it for the next attempt
        setSaveFailed(true);
      } finally {
        inFlight.current = false;
      }
    },
    [contentId]
  );

  // Count engaged, visible seconds once a second.
  useEffect(() => {
    const tick = setInterval(() => {
      if (active.current && document.visibilityState === "visible") pendingSeconds.current += 1;
    }, 1000);
    return () => clearInterval(tick);
  }, []);

  // Heartbeat while engaged.
  useEffect(() => {
    const beat = setInterval(() => {
      if (active.current && document.visibilityState === "visible" && !completed.current) void send(false);
    }, HEARTBEAT_MS);
    return () => clearInterval(beat);
  }, [send]);

  // Save what we have when the learner leaves the tab or the lesson.
  useEffect(() => {
    const onHide = () => {
      if (document.visibilityState === "hidden" && pendingSeconds.current > 0) void send(false);
    };
    document.addEventListener("visibilitychange", onHide);
    return () => {
      document.removeEventListener("visibilitychange", onHide);
      if (pendingSeconds.current > 0 && !completed.current) void send(false);
    };
  }, [send]);

  const setActive = useCallback((value: boolean) => {
    active.current = value;
  }, []);

  const update = useCallback((state: { percent?: number; position?: number }) => {
    if (state.percent !== undefined) {
      latest.current.percent = Math.max(latest.current.percent, Math.min(state.percent, 100));
    }
    if (state.position !== undefined) latest.current.position = state.position;
  }, []);

  const complete = useCallback(() => send(true), [send]);
  const flush = useCallback(() => send(false), [send]);

  const reporter = useMemo(
    () => ({ contentId, setActive, update, complete, flush }),
    [contentId, setActive, update, complete, flush]
  );
  return { reporter, saveFailed };
}
