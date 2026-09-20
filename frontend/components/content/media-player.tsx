"use client";

import React, { useRef } from "react";
import { TriangleAlert } from "lucide-react";

import { Spinner } from "@/components/ui";
import { usePlaybackTracker } from "@/hooks/use-playback-tracker";
import type { ProgressReporter } from "@/hooks/use-progress-reporter";
import { useAuthedObjectUrl } from "@/hooks/use-object-url";

/**
 * Plays a directly hosted video or audio file with the native controls.
 *
 * `src` is either a public URL, or (for files stored in the platform) an API path
 * that needs the session token — pass it as `authedPath` and the bytes are fetched
 * with the token and played from an object URL.
 */
export function MediaPlayer({
  kind,
  title,
  src,
  authedPath,
  startSeconds,
  initialPercent,
  reporter,
}: {
  kind: "video" | "audio";
  title: string;
  src?: string | null;
  authedPath?: string | null;
  startSeconds: number;
  initialPercent: number;
  reporter: ProgressReporter;
}) {
  const fetched = useAuthedObjectUrl(authedPath ?? null);
  const source = authedPath ? fetched.url : (src ?? null);

  const durationRef = useRef<number | null>(null);
  const tracker = usePlaybackTracker(reporter, { initialPercent, getDuration: () => durationRef.current, startSeconds });

  if (authedPath && fetched.loading) {
    return (
      <div className="flex aspect-video items-center justify-center rounded-xl border border-border bg-surface">
        <Spinner size="lg" />
      </div>
    );
  }
  if (!source) {
    return (
      <div role="alert" className="flex items-center gap-3 rounded-lg border border-warning-border bg-warning-light px-4 py-3 text-sm text-fg">
        <TriangleAlert className="size-4 text-warning" aria-hidden="true" />
        This {kind} could not be loaded.
      </div>
    );
  }

  const handlers = {
    onLoadedMetadata: (event: React.SyntheticEvent<HTMLMediaElement>) => {
      const element = event.currentTarget;
      if (Number.isFinite(element.duration)) durationRef.current = element.duration;
      if (startSeconds > 0 && startSeconds < element.duration) element.currentTime = startSeconds;
    },
    onPlay: () => tracker.onPlay(),
    onPause: () => tracker.onPause(),
    onSeeking: () => tracker.onSeek(),
    onTimeUpdate: (event: React.SyntheticEvent<HTMLMediaElement>) => tracker.onTime(event.currentTarget.currentTime),
    onEnded: () => tracker.onEnded(),
  };

  return kind === "video" ? (
    <video
      key={source}
      src={source}
      controls
      preload="metadata"
      playsInline
      aria-label={title}
      className="aspect-video w-full rounded-xl bg-black shadow-md"
      {...handlers}
    />
  ) : (
    <audio key={source} src={source} controls preload="metadata" aria-label={title} className="w-full" {...handlers} />
  );
}
