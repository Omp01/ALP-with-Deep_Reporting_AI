"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  Play,
  Pause,
  RotateCcw,
  Volume2,
  VolumeX,
  Maximize,
  Sparkles,
  ShieldAlert,
  TriangleAlert,
  CheckCircle2,
} from "lucide-react";

import { Badge, Button, Spinner } from "@/components/ui";
import { useAuthedObjectUrl } from "@/hooks/use-object-url";
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

interface InteractiveVideoPlayerProps {
  contentItemId: string;
  title: string;
  kind?: "video" | "audio";
  src?: string | null;
  authedPath?: string | null;
  transcript?: string | null;
  startSeconds: number;
  initialPercent: number;
  completed: boolean;
  reporter: ProgressReporter;
}

function formatTime(seconds: number): string {
  if (isNaN(seconds) || seconds < 0) return "00:00";
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
}

export function InteractiveVideoPlayer({
  contentItemId,
  title,
  kind = "video",
  src,
  authedPath,
  transcript,
  startSeconds,
  initialPercent,
  completed,
  reporter,
}: InteractiveVideoPlayerProps) {
  const fetched = useAuthedObjectUrl(authedPath ?? null);
  const source = authedPath ? fetched.url : (src ?? null);

  const videoRef = useRef<HTMLVideoElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const durationRef = useRef<number | null>(null);

  // Playback state
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(startSeconds || 0);
  const [duration, setDuration] = useState(0);
  const [volume, setVolume] = useState(1);
  const [isMuted, setIsMuted] = useState(false);
  const [playbackRate, setPlaybackRate] = useState(1);
  const [isControlsVisible, setIsControlsVisible] = useState(true);
  const controlsTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  // Checkpoints & Anti-Skipping state
  const [checkpoints, setCheckpoints] = useState<VideoCheckpoint[]>([]);
  const [loadingCheckpoints, setLoadingCheckpoints] = useState(true);
  const [activeFlashCard, setActiveFlashCard] = useState<VideoCheckpoint | null>(null);
  const [missedQueue, setMissedQueue] = useState<VideoCheckpoint[]>([]);
  const [skipWarning, setSkipWarning] = useState<string | null>(null);

  // Anti-Skipping tracker: stores the furthest verified contiguous watch point
  const lastValidTimeRef = useRef<number>(startSeconds || 0);
  const isEnforcingSeekRef = useRef<boolean>(false);
  const dismissedCheckpointIdRef = useRef<string | null>(null);

  const tracker = usePlaybackTracker(reporter, {
    initialPercent,
    getDuration: () => durationRef.current,
    startSeconds,
  });

  // 1. Fetch checkpoints on load
  useEffect(() => {
    let cancelled = false;
    async function loadCheckpoints() {
      try {
        setLoadingCheckpoints(true);
        const data = await apiClient.get<VideoCheckpointsPayload>(
          `/api/v1/learning/video/${contentItemId}/checkpoints`
        );
        if (!cancelled && data.checkpoints) {
          setCheckpoints(data.checkpoints);
        }
      } catch (err) {
        console.warn("Could not load video checkpoints", err);
      } finally {
        if (!cancelled) setLoadingCheckpoints(false);
      }
    }
    loadCheckpoints();
    return () => {
      cancelled = true;
    };
  }, [contentItemId]);

  const isCheckpointCompleted = useCallback((chk: VideoCheckpoint) => {
    return chk.status === "correct" || chk.status === "answered";
  }, []);

  // 2. Intercept uncompleted checkpoints
  const triggerCheckpoint = useCallback(
    (checkpoint: VideoCheckpoint, remainingQueue: VideoCheckpoint[] = []) => {
      if (videoRef.current) {
        videoRef.current.pause();
      }
      setIsPlaying(false);
      setActiveFlashCard(checkpoint);
      setMissedQueue(remainingQueue);

      // Report displayed status to backend
      apiClient
        .post(`/api/v1/learning/video/${contentItemId}/checkpoints/${checkpoint.id}/status`, {
          status: "displayed",
        })
        .catch(() => {});
    },
    [contentItemId]
  );

  // 3. Time update & Seek Guard
  const handleTimeUpdate = useCallback(() => {
    if (!videoRef.current) return;
    const mediaCurrent = videoRef.current.currentTime;
    setCurrentTime(mediaCurrent);
    tracker.onTime(mediaCurrent);

    if (isEnforcingSeekRef.current) return;

    const lastValid = lastValidTimeRef.current;
    const delta = mediaCurrent - lastValid;

    // A. Detect forward seek/skip beyond normal playback (more than 2.5s jump)
    if (delta > 2.5) {
      // Find any incomplete checkpoints between lastValid and mediaCurrent
      const missed = checkpoints.filter(
        (chk) =>
          chk.timestamp_seconds > lastValid &&
          chk.timestamp_seconds <= mediaCurrent &&
          !isCheckpointCompleted(chk)
      );

      if (missed.length > 0) {
        // Enforce anti-skipping: pause immediately and clamp position
        isEnforcingSeekRef.current = true;
        videoRef.current.pause();
        const firstMissed = missed[0];
        videoRef.current.currentTime = firstMissed.timestamp_seconds;
        lastValidTimeRef.current = firstMissed.timestamp_seconds;
        setCurrentTime(firstMissed.timestamp_seconds);

        setSkipWarning(
          `Skipping restricted: Complete Checkpoint #${firstMissed.order_index || 1} before continuing.`
        );
        setTimeout(() => setSkipWarning(null), 4500);

        triggerCheckpoint(firstMissed, missed.slice(1));
        setTimeout(() => {
          isEnforcingSeekRef.current = false;
        }, 100);
        return;
      }
    }

    // B. Natural Playback: check if we just hit a checkpoint
    if (delta >= 0 && delta <= 2.5) {
      // Update verified contiguous watch position
      lastValidTimeRef.current = Math.max(lastValidTimeRef.current, mediaCurrent);

      // Trigger checkpoint if we are at its timestamp (within 1 second) and not yet answered
      const dueCheckpoint = checkpoints.find(
        (chk) =>
          Math.abs(mediaCurrent - chk.timestamp_seconds) <= 1.0 &&
          !isCheckpointCompleted(chk) &&
          chk.id !== dismissedCheckpointIdRef.current &&
          (!activeFlashCard || activeFlashCard.id !== chk.id)
      );

      if (dueCheckpoint) {
        triggerCheckpoint(dueCheckpoint);
        return;
      }

      if (
        dismissedCheckpointIdRef.current &&
        checkpoints.some(
          (c) => c.id === dismissedCheckpointIdRef.current && mediaCurrent > c.timestamp_seconds + 2.0
        )
      ) {
        dismissedCheckpointIdRef.current = null;
      }
    }

    // C. Backward seek: always allowed, update reference without penalty
    if (delta < 0) {
      // User is reviewing earlier material; keep lastValidTimeRef intact so they can return
    }
  }, [checkpoints, isCheckpointCompleted, activeFlashCard, tracker, triggerCheckpoint]);

  // Handle explicit seek events from controls
  const handleSeeking = useCallback(() => {
    if (!videoRef.current || isEnforcingSeekRef.current) return;
    tracker.onSeek();
    const target = videoRef.current.currentTime;
    const lastValid = lastValidTimeRef.current;

    if (target > lastValid + 2.5) {
      const missed = checkpoints.filter(
        (chk) =>
          chk.timestamp_seconds > lastValid &&
          chk.timestamp_seconds <= target &&
          !isCheckpointCompleted(chk)
      );

      if (missed.length > 0) {
        isEnforcingSeekRef.current = true;
        videoRef.current.pause();
        const firstMissed = missed[0];
        videoRef.current.currentTime = firstMissed.timestamp_seconds;
        lastValidTimeRef.current = firstMissed.timestamp_seconds;
        setCurrentTime(firstMissed.timestamp_seconds);

        setSkipWarning(
          `Cannot skip forward past uncompleted checkpoints! Answering question at ${formatTime(firstMissed.timestamp_seconds)}.`
        );
        setTimeout(() => setSkipWarning(null), 4500);

        triggerCheckpoint(firstMissed, missed.slice(1));
        setTimeout(() => {
          isEnforcingSeekRef.current = false;
        }, 100);
      }
    }
  }, [checkpoints, isCheckpointCompleted, tracker, triggerCheckpoint]);

  // Answer submission
  const handleAnswerCheckpoint = async (
    selectedOptionId: string
  ): Promise<VideoCheckpointAnswerResponse> => {
    if (!activeFlashCard) throw new Error("No active checkpoint");

    const res = await apiClient.post<VideoCheckpointAnswerResponse>(
      `/api/v1/learning/video/${contentItemId}/checkpoints/${activeFlashCard.id}/answer`,
      { selected_option_id: selectedOptionId }
    );

    // Update local checkpoint status
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

  // Resume after completing a checkpoint
  const handleResumePlayback = () => {
    if (activeFlashCard) {
      dismissedCheckpointIdRef.current = activeFlashCard.id;
    }
    if (missedQueue.length > 0) {
      const nextMissed = missedQueue[0];
      if (videoRef.current) {
        videoRef.current.currentTime = nextMissed.timestamp_seconds;
      }
      lastValidTimeRef.current = nextMissed.timestamp_seconds;
      setCurrentTime(nextMissed.timestamp_seconds);
      triggerCheckpoint(nextMissed, missedQueue.slice(1));
    } else {
      setActiveFlashCard(null);
      setMissedQueue([]);
      if (videoRef.current) {
        videoRef.current.play().catch(() => {});
        setIsPlaying(true);
      }
    }
  };

  // Video UI controls
  const togglePlay = () => {
    if (!videoRef.current) return;
    if (activeFlashCard) return; // Prevent playback while flashcard is open

    if (isPlaying) {
      videoRef.current.pause();
      setIsPlaying(false);
      tracker.onPause();
    } else {
      videoRef.current.play().then(() => {
        setIsPlaying(true);
        tracker.onPlay();
      }).catch(() => {});
    }
  };

  const handleProgressBarClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!videoRef.current || duration <= 0 || activeFlashCard) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const clickPos = (e.clientX - rect.left) / rect.width;
    const targetSeconds = clickPos * duration;

    // Check anti-skipping before applying seek
    const lastValid = lastValidTimeRef.current;
    if (targetSeconds > lastValid + 2.5) {
      const missed = checkpoints.filter(
        (chk) =>
          chk.timestamp_seconds > lastValid &&
          chk.timestamp_seconds <= targetSeconds &&
          !isCheckpointCompleted(chk)
      );

      if (missed.length > 0) {
        isEnforcingSeekRef.current = true;
        videoRef.current.pause();
        const firstMissed = missed[0];
        videoRef.current.currentTime = firstMissed.timestamp_seconds;
        lastValidTimeRef.current = firstMissed.timestamp_seconds;
        setCurrentTime(firstMissed.timestamp_seconds);

        setSkipWarning(
          `Skipping restricted: Please answer checkpoint #${firstMissed.order_index || 1} first.`
        );
        setTimeout(() => setSkipWarning(null), 4000);

        triggerCheckpoint(firstMissed, missed.slice(1));
        setTimeout(() => {
          isEnforcingSeekRef.current = false;
        }, 100);
        return;
      }
    }

    videoRef.current.currentTime = targetSeconds;
    setCurrentTime(targetSeconds);
  };

  const handleSeekBackward = () => {
    if (!videoRef.current) return;
    const newTime = Math.max(0, videoRef.current.currentTime - 10);
    videoRef.current.currentTime = newTime;
    setCurrentTime(newTime);
  };

  const toggleMute = () => {
    if (!videoRef.current) return;
    videoRef.current.muted = !isMuted;
    setIsMuted(!isMuted);
  };

  const handleVolumeChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = parseFloat(e.target.value);
    setVolume(val);
    if (videoRef.current) {
      videoRef.current.volume = val;
      videoRef.current.muted = val === 0;
      setIsMuted(val === 0);
    }
  };

  const cyclePlaybackRate = () => {
    const rates = [1, 1.25, 1.5, 0.75];
    const nextRate = rates[(rates.indexOf(playbackRate) + 1) % rates.length];
    setPlaybackRate(nextRate);
    if (videoRef.current) {
      videoRef.current.playbackRate = nextRate;
    }
  };

  const toggleFullscreen = () => {
    if (!containerRef.current) return;
    if (!document.fullscreenElement) {
      containerRef.current.requestFullscreen().catch(() => {});
    } else {
      document.exitFullscreen().catch(() => {});
    }
  };

  // Activity timer for controls auto-hide
  const handleMouseMove = () => {
    setIsControlsVisible(true);
    if (controlsTimeoutRef.current) clearTimeout(controlsTimeoutRef.current);
    if (isPlaying && !activeFlashCard) {
      controlsTimeoutRef.current = setTimeout(() => {
        setIsControlsVisible(false);
      }, 3000);
    }
  };

  if (authedPath && fetched.loading) {
    return (
      <div className="flex aspect-video items-center justify-center rounded-2xl border border-border bg-surface">
        <Spinner size="lg" />
      </div>
    );
  }

  if (!source) {
    return (
      <div
        role="alert"
        className="flex items-center gap-3 rounded-xl border border-warning-border bg-warning-light px-4 py-3 text-sm text-fg"
      >
        <TriangleAlert className="size-4 text-warning" aria-hidden="true" />
        This {kind} could not be loaded.
      </div>
    );
  }

  const completedCheckpointsCount = checkpoints.filter(isCheckpointCompleted).length;
  const progressRatio = duration > 0 ? (currentTime / duration) * 100 : 0;

  return (
    <div className="space-y-4">
      {/* Player Container */}
      <div
        ref={containerRef}
        onMouseMove={handleMouseMove}
        onMouseLeave={() => isPlaying && !activeFlashCard && setIsControlsVisible(false)}
        className="relative aspect-video w-full overflow-hidden rounded-2xl border border-border bg-black shadow-xl select-none group"
      >
        {/* Anti-Skipping Overlay Warning */}
        {skipWarning && (
          <div className="absolute top-4 left-1/2 -translate-x-1/2 z-40 flex items-center gap-2 rounded-xl border border-warning-border bg-warning-light/95 px-4 py-2 text-xs font-semibold text-fg shadow-lg backdrop-blur-md animate-in fade-in slide-in-from-top-2">
            <ShieldAlert className="size-4 text-warning animate-pulse" />
            <span>{skipWarning}</span>
          </div>
        )}

        {/* Checkpoint Indicators Banner */}
        <div className="absolute top-3 left-3 z-20 flex items-center gap-2">
          {checkpoints.length > 0 && (
            <button
              type="button"
              onClick={() => {
                if (videoRef.current) videoRef.current.pause();
                const target = checkpoints.find((c) => c.status !== "correct" && c.status !== "answered") || checkpoints[0];
                triggerCheckpoint(target);
              }}
              className="cursor-pointer transition-transform hover:scale-105 active:scale-95 focus:outline-none"
              title="Click to view checkpoint comprehension check"
            >
              <Badge
                variant={
                  completedCheckpointsCount === checkpoints.length ? "success" : "neutral"
                }
                className="bg-black/75 text-white backdrop-blur-md border border-white/20 flex items-center gap-1.5 shadow-md hover:bg-black/90 cursor-pointer"
              >
                <Sparkles className="size-3 text-primary animate-pulse" />
                <span>
                  {completedCheckpointsCount} / {checkpoints.length} Checkpoints · Click to Check
                </span>
              </Badge>
            </button>
          )}
          {loadingCheckpoints && (
            <Badge variant="neutral" className="bg-black/60 text-white backdrop-blur-md">
              <Spinner size="sm" className="mr-1 size-2.5" />
              Analyzing checkpoints...
            </Badge>
          )}
        </div>

        {/* The HTML5 Media Element */}
        <video
          ref={videoRef}
          src={source}
          playsInline
          preload="metadata"
          aria-label={title}
          onClick={togglePlay}
          onTimeUpdate={handleTimeUpdate}
          onSeeking={handleSeeking}
          onPlay={() => {
            setIsPlaying(true);
            tracker.onPlay();
          }}
          onPause={() => {
            setIsPlaying(false);
            tracker.onPause();
          }}
          onEnded={() => {
            setIsPlaying(false);
            tracker.onEnded();
          }}
          onLoadedMetadata={(e) => {
            const el = e.currentTarget;
            if (Number.isFinite(el.duration)) {
              durationRef.current = el.duration;
              setDuration(el.duration);
            }
            if (startSeconds > 0 && startSeconds < el.duration) {
              el.currentTime = startSeconds;
              setCurrentTime(startSeconds);
              lastValidTimeRef.current = startSeconds;
            }
          }}
          className="size-full object-contain cursor-pointer"
        />

        {/* Big Center Play/Pause Button on Hover */}
        {!isPlaying && !activeFlashCard && (
          <button
            type="button"
            onClick={togglePlay}
            aria-label="Play video"
            className="absolute inset-0 m-auto flex size-16 items-center justify-center rounded-full bg-primary/90 text-primary-fg shadow-2xl backdrop-blur-sm transition-transform hover:scale-110 active:scale-95"
          >
            <Play className="size-8 ml-1" fill="currentColor" />
          </button>
        )}

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

        {/* Custom Video Controls Bar */}
        <div
          className={`absolute inset-x-0 bottom-0 z-20 bg-gradient-to-t from-black/90 via-black/50 to-transparent p-4 transition-opacity duration-300 ${
            isControlsVisible || !isPlaying || activeFlashCard
              ? "opacity-100"
              : "opacity-0 pointer-events-none"
          }`}
        >
          {/* Timeline & Checkpoint Markers */}
          <div
            onClick={handleProgressBarClick}
            className="relative h-2 w-full cursor-pointer rounded-full bg-white/20 transition-all hover:h-3 group/bar"
          >
            {/* Furthest Valid Watch Buffer */}
            <div
              className="absolute top-0 left-0 h-full rounded-full bg-white/30 transition-all"
              style={{
                width: `${duration > 0 ? (lastValidTimeRef.current / duration) * 100 : 0}%`,
              }}
              title="Verified watch progress"
            />

            {/* Current Playback Progress */}
            <div
              className="absolute top-0 left-0 h-full rounded-full bg-primary transition-all"
              style={{ width: `${progressRatio}%` }}
            />

            {/* Checkpoint Markers Along Timeline */}
            {checkpoints.map((chk) => {
              const posPercent = duration > 0 ? (chk.timestamp_seconds / duration) * 100 : 0;
              const isDone = isCheckpointCompleted(chk);
              return (
                <div
                  key={chk.id}
                  style={{ left: `${posPercent}%` }}
                  title={`Checkpoint at ${formatTime(chk.timestamp_seconds)}: ${
                    isDone ? "Completed" : "Pending"
                  }`}
                  className={`absolute top-1/2 -translate-x-1/2 -translate-y-1/2 z-10 size-3 rounded-full border-2 border-black transition-transform hover:scale-150 ${
                    isDone ? "bg-success" : "bg-warning shadow-lg shadow-warning/50"
                  }`}
                />
              );
            })}
          </div>

          {/* Controls Bottom Row */}
          <div className="mt-3 flex items-center justify-between text-white text-xs">
            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={togglePlay}
                disabled={activeFlashCard !== null}
                className="rounded-lg p-1.5 hover:bg-white/20 transition-colors"
                title={isPlaying ? "Pause" : "Play"}
              >
                {isPlaying ? <Pause className="size-5" /> : <Play className="size-5" />}
              </button>

              <button
                type="button"
                onClick={handleSeekBackward}
                className="rounded-lg p-1.5 hover:bg-white/20 transition-colors flex items-center gap-0.5"
                title="Rewind 10s"
              >
                <RotateCcw className="size-4" />
                <span className="text-[10px] font-mono">10s</span>
              </button>

              <div className="flex items-center gap-1 font-mono text-[11px] text-white/90">
                <span>{formatTime(currentTime)}</span>
                <span>/</span>
                <span>{formatTime(duration)}</span>
              </div>
            </div>

            <div className="flex items-center gap-3">
              {/* Volume */}
              <div className="flex items-center gap-1.5 group/vol">
                <button
                  type="button"
                  onClick={toggleMute}
                  className="rounded-lg p-1.5 hover:bg-white/20 transition-colors"
                >
                  {isMuted || volume === 0 ? (
                    <VolumeX className="size-4" />
                  ) : (
                    <Volume2 className="size-4" />
                  )}
                </button>
                <input
                  type="range"
                  min={0}
                  max={1}
                  step={0.05}
                  value={isMuted ? 0 : volume}
                  onChange={handleVolumeChange}
                  className="w-16 h-1 accent-primary cursor-pointer"
                />
              </div>

              {/* Speed */}
              <button
                type="button"
                onClick={cyclePlaybackRate}
                className="rounded-lg px-2 py-1 bg-white/10 hover:bg-white/20 font-mono text-[11px] font-semibold transition-colors"
                title="Change playback speed"
              >
                {playbackRate}x
              </button>

              {/* Fullscreen */}
              <button
                type="button"
                onClick={toggleFullscreen}
                className="rounded-lg p-1.5 hover:bg-white/20 transition-colors"
                title="Toggle Fullscreen"
              >
                <Maximize className="size-4" />
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Synchronized Transcript */}
      {transcript && (
        <TranscriptSyncPanel
          transcript={transcript}
          currentTime={currentTime}
          checkpoints={checkpoints}
          onSeekTo={(seekSec) => {
            if (!videoRef.current) return;
            // Seeking backward is always permitted
            if (seekSec <= lastValidTimeRef.current) {
              videoRef.current.currentTime = seekSec;
              setCurrentTime(seekSec);
            } else {
              // Attempting forward jump: validate
              const missed = checkpoints.filter(
                (chk) =>
                  chk.timestamp_seconds > lastValidTimeRef.current &&
                  chk.timestamp_seconds <= seekSec &&
                  !isCheckpointCompleted(chk)
              );
              if (missed.length > 0) {
                videoRef.current.currentTime = missed[0].timestamp_seconds;
                triggerCheckpoint(missed[0], missed.slice(1));
              } else {
                videoRef.current.currentTime = seekSec;
                setCurrentTime(seekSec);
              }
            }
          }}
        />
      )}
    </div>
  );
}
