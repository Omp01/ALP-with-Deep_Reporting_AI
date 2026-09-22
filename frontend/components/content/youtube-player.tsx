"use client";

import React, { useEffect, useRef, useState, useCallback } from "react";
import { CheckCircle2, ExternalLink, TriangleAlert, Sparkles, ShieldAlert } from "lucide-react";

import { Badge, Button } from "@/components/ui";
import { usePlaybackTracker } from "@/hooks/use-playback-tracker";
import type { ProgressReporter } from "@/hooks/use-progress-reporter";
import { apiClient } from "@/lib/api-client";
import type {
  VideoCheckpoint,
  VideoCheckpointAnswerResponse,
  VideoCheckpointsPayload,
} from "@/types/learning";
import { TranscriptSyncPanel } from "./transcript-sync-panel";
import { VideoFlashCard } from "./video-flash-card";

/* Minimal typing for the parts of the YouTube IFrame Player API used here. */
interface YTPlayer {
  destroy(): void;
  getCurrentTime(): number;
  getDuration(): number;
  pauseVideo(): void;
  playVideo(): void;
  seekTo(seconds: number, allowSeekAhead?: boolean): void;
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
  contentItemId,
  transcript,
  startSeconds,
  initialPercent,
  completed,
  reporter,
}: {
  videoId: string;
  title: string;
  contentItemId?: string;
  transcript?: string | null;
  startSeconds: number;
  initialPercent: number;
  completed: boolean;
  reporter: ProgressReporter;
}) {
  const host = useRef<HTMLDivElement>(null);
  const playerRef = useRef<YTPlayer | null>(null);
  const durationRef = useRef<number | null>(null);
  const [failure, setFailure] = useState<string | null>(null);

  // Checkpoints & Flash-Card state
  const [checkpoints, setCheckpoints] = useState<VideoCheckpoint[]>([]);
  const [activeFlashCard, setActiveFlashCard] = useState<VideoCheckpoint | null>(null);
  const [missedQueue, setMissedQueue] = useState<VideoCheckpoint[]>([]);
  const [skipWarning, setSkipWarning] = useState<string | null>(null);
  const [currentTime, setCurrentTime] = useState(startSeconds || 0);

  const lastValidTimeRef = useRef<number>(startSeconds || 0);
  const checkpointsRef = useRef<VideoCheckpoint[]>([]);
  useEffect(() => {
    checkpointsRef.current = checkpoints;
  }, [checkpoints]);

  const activeFlashCardRef = useRef<VideoCheckpoint | null>(null);
  useEffect(() => {
    activeFlashCardRef.current = activeFlashCard;
  }, [activeFlashCard]);

  const dismissedCheckpointIdRef = useRef<string | null>(null);

  // Load interactive checkpoints
  useEffect(() => {
    if (!contentItemId) return;
    let cancelled = false;
    async function loadCheckpoints() {
      try {
        const data = await apiClient.get<VideoCheckpointsPayload>(
          `/api/v1/learning/video/${contentItemId}/checkpoints`
        );
        if (!cancelled && data.checkpoints) {
          setCheckpoints(data.checkpoints);
        }
      } catch (err) {
        console.warn("Could not load video checkpoints", err);
      }
    }
    loadCheckpoints();
    return () => {
      cancelled = true;
    };
  }, [contentItemId]);

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

  const isCheckpointCompleted = useCallback((chk: VideoCheckpoint) => {
    return chk.status === "correct" || chk.status === "answered";
  }, []);

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
                poll = setInterval(() => {
                  if (!playerRef.current) return;
                  const current = playerRef.current.getCurrentTime();
                  setCurrentTime(current);
                  trackerRef.current.onTime(current);

                  // Anti-skipping & checkpoint validation
                  const lastValid = lastValidTimeRef.current;
                  const delta = current - lastValid;
                  const currentCheckpoints = checkpointsRef.current;

                  // A. Detect forward seek past incomplete checkpoints
                  if (delta > 2.5) {
                    const missed = currentCheckpoints.filter(
                      (chk) =>
                        chk.timestamp_seconds > lastValid &&
                        chk.timestamp_seconds <= current &&
                        chk.status !== "correct" &&
                        chk.status !== "answered"
                    );

                    if (missed.length > 0) {
                      playerRef.current.pauseVideo();
                      playerRef.current.seekTo(missed[0].timestamp_seconds, true);
                      lastValidTimeRef.current = missed[0].timestamp_seconds;
                      setSkipWarning(
                        `Skipping restricted: Please answer Checkpoint #${missed[0].order_index || 1} first.`
                      );
                      setTimeout(() => setSkipWarning(null), 4000);
                      setActiveFlashCard(missed[0]);
                      setMissedQueue(missed.slice(1));
                      return;
                    }
                  }

                  // B. Natural playback reaching a checkpoint
                  if (delta >= 0 && delta <= 2.5) {
                    lastValidTimeRef.current = Math.max(lastValidTimeRef.current, current);
                    const due = currentCheckpoints.find(
                      (chk) =>
                        Math.abs(current - chk.timestamp_seconds) <= 1.2 &&
                        chk.status !== "correct" &&
                        chk.status !== "answered" &&
                        chk.id !== dismissedCheckpointIdRef.current &&
                        (!activeFlashCardRef.current || activeFlashCardRef.current.id !== chk.id)
                    );

                    if (due) {
                      playerRef.current.pauseVideo();
                      setActiveFlashCard(due);
                      return;
                    }

                    // Clear dismissed ref once we have moved past the checkpoint timestamp
                    if (
                      dismissedCheckpointIdRef.current &&
                      currentCheckpoints.some(
                        (c) =>
                          c.id === dismissedCheckpointIdRef.current &&
                          current > c.timestamp_seconds + 2.0
                      )
                    ) {
                      dismissedCheckpointIdRef.current = null;
                    }
                  }
                }, POLL_MS);
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

  const handleAnswerCheckpoint = async (
    selectedOptionId: string
  ): Promise<VideoCheckpointAnswerResponse> => {
    if (!activeFlashCard || !contentItemId) throw new Error("No active checkpoint");

    const res = await apiClient.post<VideoCheckpointAnswerResponse>(
      `/api/v1/learning/video/${contentItemId}/checkpoints/${activeFlashCard.id}/answer`,
      { selected_option_id: selectedOptionId }
    );

    setCheckpoints((prev) =>
      prev.map((c) =>
        c.id === activeFlashCard.id
          ? {
              ...c,
              status: res.status,
              selected_option_id: selectedOptionId,
              correct_option_id: res.correct_option_id,
              explanation: res.explanation,
            }
          : c
      )
    );

    return res;
  };

  const handleResumePlayback = () => {
    if (activeFlashCard) {
      dismissedCheckpointIdRef.current = activeFlashCard.id;
    }
    if (missedQueue.length > 0) {
      const nextMissed = missedQueue[0];
      if (playerRef.current) {
        playerRef.current.seekTo(nextMissed.timestamp_seconds, true);
      }
      lastValidTimeRef.current = nextMissed.timestamp_seconds;
      setCurrentTime(nextMissed.timestamp_seconds);
      setActiveFlashCard(nextMissed);
      setMissedQueue(missedQueue.slice(1));
    } else {
      setActiveFlashCard(null);
      setMissedQueue([]);
      if (playerRef.current) {
        try {
          playerRef.current.playVideo();
        } catch (e) {
          console.warn("Could not resume player", e);
        }
      }
    }
  };

  const watchUrl = `https://www.youtube.com/watch?v=${videoId}`;
  const completedCount = checkpoints.filter(isCheckpointCompleted).length;

  return (
    <div className="space-y-4">
      <div className="relative aspect-video w-full overflow-hidden rounded-2xl bg-black shadow-xl border border-border">
        {/* Anti-skipping warning badge */}
        {skipWarning && (
          <div className="absolute top-4 left-1/2 -translate-x-1/2 z-40 flex items-center gap-2 rounded-xl border border-warning-border bg-warning-light/95 px-4 py-2 text-xs font-semibold text-fg shadow-lg backdrop-blur-md animate-in fade-in slide-in-from-top-2">
            <ShieldAlert className="size-4 text-warning animate-pulse" />
            <span>{skipWarning}</span>
          </div>
        )}

        {/* Checkpoint pill */}
        {checkpoints.length > 0 && (
          <div className="absolute top-3 left-3 z-20 flex items-center gap-2">
            <button
              type="button"
              onClick={() => {
                if (playerRef.current) playerRef.current.pauseVideo();
                const target = checkpoints.find((c) => c.status !== "correct" && c.status !== "answered") || checkpoints[0];
                setActiveFlashCard(target);
              }}
              className="cursor-pointer transition-transform hover:scale-105 active:scale-95 focus:outline-none"
              title="Click to view checkpoint comprehension check"
            >
              <Badge
                variant={completedCount === checkpoints.length ? "success" : "neutral"}
                className="bg-black/75 text-white backdrop-blur-md border border-white/20 flex items-center gap-1.5 shadow-md hover:bg-black/90 cursor-pointer"
              >
                <Sparkles className="size-3 text-primary animate-pulse" />
                <span>
                  {completedCount} / {checkpoints.length} Checkpoints · Click to Check
                </span>
              </Badge>
            </button>
          </div>
        )}

        {/* The YouTube iframe container */}
        <div ref={host} className="absolute inset-0 [&>iframe]:h-full [&>iframe]:w-full" aria-label={title} />

        {/* Flash Card Question Popup Overlay */}
        {activeFlashCard && (
          <VideoFlashCard
            checkpoint={activeFlashCard}
            totalCheckpoints={checkpoints.length}
            currentIndex={checkpoints.findIndex((c) => c.id === activeFlashCard.id)}
            initialCountdownSeconds={15}
            onAnswer={handleAnswerCheckpoint}
            onResume={handleResumePlayback}
          />
        )}
      </div>

      {failure && (
        <div role="alert" className="flex flex-wrap items-center gap-3 rounded-xl border border-warning-border bg-warning-light px-4 py-3 text-sm">
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

      {/* Synchronized Transcript */}
      {transcript && (
        <TranscriptSyncPanel
          transcript={transcript}
          currentTime={currentTime}
          checkpoints={checkpoints}
          onSeekTo={(sec) => {
            if (playerRef.current) {
              if (sec <= lastValidTimeRef.current) {
                playerRef.current.seekTo(sec, true);
                setCurrentTime(sec);
              } else {
                const missed = checkpoints.filter(
                  (chk) =>
                    chk.timestamp_seconds > lastValidTimeRef.current &&
                    chk.timestamp_seconds <= sec &&
                    !isCheckpointCompleted(chk)
                );
                if (missed.length > 0) {
                  playerRef.current.seekTo(missed[0].timestamp_seconds, true);
                  setActiveFlashCard(missed[0]);
                  setMissedQueue(missed.slice(1));
                } else {
                  playerRef.current.seekTo(sec, true);
                  setCurrentTime(sec);
                }
              }
            }
          }}
        />
      )}
    </div>
  );
}
