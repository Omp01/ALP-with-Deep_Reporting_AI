"use client";

import { useCallback, useRef } from "react";

import { useLearningEvents } from "./use-learning-events";
import type { ProgressReporter } from "./use-progress-reporter";

/** A jump larger than this between two time readings is a seek, not playback. */
const NATURAL_STEP_SECONDS = 2.5;
/** Ending within this share of the video counts as having watched it (covers end credits). */
const ENDED_COMPLETION_PERCENT = 85;
/** A `video_progress` event is reported after this many seconds of real playback. */
const PROGRESS_EVENT_EVERY_SECONDS = 30;

/**
 * Turns raw player events into honest watch progress.
 *
 * Progress advances only by time that actually played: a jump forward (scrubbing to
 * the end) adds nothing. It builds on the percent already saved, so a learner who
 * resumes a half-watched video continues from where they were rather than from zero.
 * The player supplies events; this decides what they mean.
 */
export function usePlaybackTracker(
  reporter: ProgressReporter,
  options: { initialPercent: number; getDuration: () => number | null; startSeconds?: number }
) {
  const events = useLearningEvents();
  const lastTime = useRef<number | null>(null);
  const playedSeconds = useRef(0);
  const percent = useRef(options.initialPercent);
  const position = useRef(options.startSeconds ?? 0);
  const hasStarted = useRef(false);
  const secondsSinceProgressEvent = useRef(0);
  const { initialPercent, getDuration } = options;

  const mediaPosition = useCallback(() => {
    const duration = getDuration();
    return {
      position_seconds: Math.max(0, Math.floor(position.current)),
      ...(duration && duration > 0 ? { duration_seconds: Math.floor(duration) } : {}),
    };
  }, [getDuration]);

  const onPlay = useCallback(() => {
    lastTime.current = null;
    reporter.setActive(true);
    // First play is a start; every later play (after a pause) is a resume.
    events.report(hasStarted.current ? "video_resumed" : "video_started", { contentId: reporter.contentId }, mediaPosition());
    hasStarted.current = true;
  }, [reporter, events, mediaPosition]);

  const onPause = useCallback(() => {
    reporter.setActive(false);
    lastTime.current = null;
    if (hasStarted.current) events.report("video_paused", { contentId: reporter.contentId }, mediaPosition());
    void reporter.flush();
  }, [reporter, events, mediaPosition]);

  /** Call with the current playback position (seconds), roughly once a second while playing. */
  const onTime = useCallback(
    (currentSeconds: number) => {
      const previous = lastTime.current;
      lastTime.current = currentSeconds;
      if (previous !== null) {
        const delta = currentSeconds - previous;
        if (delta > 0 && delta <= NATURAL_STEP_SECONDS) {
          playedSeconds.current += delta;
          secondsSinceProgressEvent.current += delta;
        }
      }
      position.current = currentSeconds;
      const duration = getDuration();
      if (duration && duration > 0) {
        percent.current = Math.min(100, initialPercent + (playedSeconds.current / duration) * 100);
      }
      reporter.update({ percent: percent.current, position: Math.floor(currentSeconds) });
      if (secondsSinceProgressEvent.current >= PROGRESS_EVENT_EVERY_SECONDS) {
        secondsSinceProgressEvent.current = 0;
        events.report("video_progress", { contentId: reporter.contentId }, { ...mediaPosition(), percent: Math.round(percent.current * 10) / 10 });
      }
    },
    [reporter, events, mediaPosition, initialPercent, getDuration]
  );

  const onSeek = useCallback(() => {
    lastTime.current = null;
  }, []);

  const onEnded = useCallback(() => {
    reporter.setActive(false);
    lastTime.current = null;
    if (percent.current >= ENDED_COMPLETION_PERCENT) {
      reporter.update({ percent: 100 });
      void reporter.complete();
    } else {
      void reporter.flush();
    }
  }, [reporter]);

  return { onPlay, onPause, onTime, onSeek, onEnded };
}
