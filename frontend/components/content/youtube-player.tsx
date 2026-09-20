"use client";

import React, { useEffect, useRef, useState } from "react";
import { CheckCircle2, ExternalLink, TriangleAlert } from "lucide-react";

import { Button } from "@/components/ui";
import { usePlaybackTracker } from "@/hooks/use-playback-tracker";
import type { ProgressReporter } from "@/hooks/use-progress-reporter";

/* Minimal typing for the parts of the YouTube IFrame Player API used here. */
interface YTPlayer {
  destroy(): void;
  getCurrentTime(): number;
  getDuration(): number;
}
interface YTPlayerEvent {
  data: number;
  target: YTPlayer;
}
interface YTNamespace {
  Player: new (
    element: HTMLElement,
    options: {
      videoId: string;
      host?: string;
      playerVars?: Record<string, string | number>;
      events?: {
        onReady?: (event: YTPlayerEvent) => void;
        onStateChange?: (event: YTPlayerEvent) => void;
        onError?: (event: YTPlayerEvent) => void;
      };
    }
  ) => YTPlayer;
}
declare global {
  interface Window {
    YT?: YTNamespace;
    onYouTubeIframeAPIReady?: () => void;
  }
}

const STATE = { ENDED: 0, PLAYING: 1, PAUSED: 2, BUFFERING: 3 } as const;
const POLL_MS = 1000;

let apiPromise: Promise<YTNamespace> | null = null;

/** Load the IFrame API once per page. */
function loadYouTubeApi(): Promise<YTNamespace> {
  if (window.YT?.Player) return Promise.resolve(window.YT);
  if (!apiPromise) {
    apiPromise = new Promise<YTNamespace>((resolve, reject) => {
      const previous = window.onYouTubeIframeAPIReady;
      window.onYouTubeIframeAPIReady = () => {
        previous?.();
        if (window.YT) resolve(window.YT);
      };
      const script = document.createElement("script");
      script.src = "https://www.youtube.com/iframe_api";
      script.async = true;
      script.onerror = () => {
        apiPromise = null;
        reject(new Error("The YouTube player could not be loaded."));
      };
      document.head.appendChild(script);
    });
  }
  return apiPromise;
}

const ERROR_TEXT: Record<number, string> = {
  100: "This video has been removed or made private.",
  101: "The owner of this video does not allow it to be played here.",
  150: "The owner of this video does not allow it to be played here.",
};

export function YouTubePlayer({
  videoId,
  title,
  startSeconds,
  initialPercent,
  completed,
  reporter,
}: {
  videoId: string;
  title: string;
  startSeconds: number;
  initialPercent: number;
  completed: boolean;
  reporter: ProgressReporter;
}) {
  const host = useRef<HTMLDivElement>(null);
  const playerRef = useRef<YTPlayer | null>(null);
  const durationRef = useRef<number | null>(null);
  const [failure, setFailure] = useState<string | null>(null);

  const tracker = usePlaybackTracker(reporter, {
    initialPercent,
    getDuration: () => durationRef.current,
    startSeconds,
  });
  // The player is created once; it must always call the latest tracker handlers.
  const trackerRef = useRef(tracker);
  useEffect(() => {
    trackerRef.current = tracker;
  });

  useEffect(() => {
    let cancelled = false;
    let poll: ReturnType<typeof setInterval> | null = null;
    const mount = document.createElement("div");
    host.current?.appendChild(mount);

    const stopPolling = () => {
      if (poll) clearInterval(poll);
      poll = null;
    };

    loadYouTubeApi()
      .then((YT) => {
        if (cancelled) return;
        playerRef.current = new YT.Player(mount, {
          videoId,
          host: "https://www.youtube-nocookie.com",
          playerVars: {
            start: Math.max(0, Math.floor(startSeconds)),
            rel: 0,
            playsinline: 1,
            origin: window.location.origin,
          },
          events: {
            onReady: (event) => {
              const duration = event.target.getDuration();
              if (duration > 0) durationRef.current = duration;
            },
            onStateChange: (event) => {
              const player = event.target;
              if (event.data === STATE.PLAYING) {
                const duration = player.getDuration();
                if (duration > 0) durationRef.current = duration;
                trackerRef.current.onPlay();
                stopPolling();
                poll = setInterval(() => trackerRef.current.onTime(player.getCurrentTime()), POLL_MS);
              } else if (event.data === STATE.PAUSED) {
                stopPolling();
                trackerRef.current.onPause();
              } else if (event.data === STATE.ENDED) {
                stopPolling();
                trackerRef.current.onEnded();
              } else if (event.data === STATE.BUFFERING) {
                trackerRef.current.onSeek();
              }
            },
            onError: (event) => {
              setFailure(ERROR_TEXT[event.data] ?? "This video could not be played.");
            },
          },
        });
      })
      .catch((error: Error) => {
        if (!cancelled) setFailure(error.message);
      });

    return () => {
      cancelled = true;
      stopPolling();
      playerRef.current?.destroy();
      playerRef.current = null;
      mount.remove();
    };
  }, [videoId, startSeconds]);

  const watchUrl = `https://www.youtube.com/watch?v=${videoId}`;

  return (
    <div className="space-y-3">
      <div className="relative aspect-video w-full overflow-hidden rounded-xl bg-black shadow-md">
        <div ref={host} className="absolute inset-0 [&>iframe]:h-full [&>iframe]:w-full" aria-label={title} />
      </div>

      {failure && (
        <div role="alert" className="flex flex-wrap items-center gap-3 rounded-lg border border-warning-border bg-warning-light px-4 py-3 text-sm">
          <TriangleAlert className="size-4 shrink-0 text-warning" aria-hidden="true" />
          <span className="min-w-0 flex-1 text-fg">{failure}</span>
          <a
            href={watchUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 font-medium text-primary underline underline-offset-2"
          >
            Watch on YouTube <ExternalLink className="size-3.5" aria-hidden="true" />
          </a>
          {!completed && (
            <Button size="sm" variant="secondary" onClick={() => void reporter.complete()}>
              <CheckCircle2 aria-hidden="true" /> I watched it there
            </Button>
          )}
        </div>
      )}
    </div>
  );
}
