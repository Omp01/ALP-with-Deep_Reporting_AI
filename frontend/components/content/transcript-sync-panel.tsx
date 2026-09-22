"use client";

import React, { useEffect, useMemo, useRef } from "react";
import { PlayCircle, FileText, CheckCircle2 } from "lucide-react";
import type { VideoCheckpoint } from "@/types/learning";

interface TranscriptCue {
  id: string;
  seconds: number;
  timeLabel: string;
  text: string;
}

interface TranscriptSyncPanelProps {
  transcript: string;
  currentTime: number;
  checkpoints?: VideoCheckpoint[];
  onSeekTo?: (seconds: number) => void;
}

function formatSecondsToTime(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
}

export function TranscriptSyncPanel({
  transcript,
  currentTime,
  checkpoints = [],
  onSeekTo,
}: TranscriptSyncPanelProps) {
  const activeCueRef = useRef<HTMLDivElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);

  // Parse raw transcript text into timestamped cues
  const cues = useMemo<TranscriptCue[]>(() => {
    if (!transcript) return [];

    const lines = transcript.split("\n");
    const parsed: TranscriptCue[] = [];
    const timestampRegex = /^(?:\[?(\d{1,2}:\d{2}(?::\d{2})?)\]?)\s*[-–—:]?\s*(.*)$/;

    let autoTimeCounter = 0;

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i].trim();
      if (!line) continue;

      const match = line.match(timestampRegex);
      if (match) {
        const timeParts = match[1].split(":").map(Number);
        let sec = 0;
        if (timeParts.length === 2) {
          sec = timeParts[0] * 60 + timeParts[1];
        } else if (timeParts.length === 3) {
          sec = timeParts[0] * 3600 + timeParts[1] * 60 + timeParts[2];
        }

        parsed.push({
          id: `cue-${i}`,
          seconds: sec,
          timeLabel: match[1],
          text: match[2].trim() || match[1],
        });
      } else {
        // Un-timestamped line or paragraph: estimate chronological spacing
        const sec = autoTimeCounter;
        parsed.push({
          id: `cue-${i}`,
          seconds: sec,
          timeLabel: formatSecondsToTime(sec),
          text: line,
        });
        autoTimeCounter += Math.max(15, Math.floor(line.length / 8));
      }
    }

    return parsed;
  }, [transcript]);

  // Find the active cue based on video currentTime
  const activeCueIndex = useMemo(() => {
    if (cues.length === 0) return -1;
    let idx = 0;
    for (let i = 0; i < cues.length; i++) {
      if (currentTime >= cues[i].seconds) {
        idx = i;
      } else {
        break;
      }
    }
    return idx;
  }, [cues, currentTime]);

  // Auto-scroll active cue smoothly into view within the container
  useEffect(() => {
    if (activeCueRef.current && containerRef.current) {
      activeCueRef.current.scrollIntoView({
        behavior: "smooth",
        block: "nearest",
      });
    }
  }, [activeCueIndex]);

  // Map checkpoints to cues
  const getCheckpointNear = (cueSec: number, nextCueSec: number | null) => {
    return checkpoints.find((chk) => {
      if (nextCueSec !== null) {
        return chk.timestamp_seconds >= cueSec && chk.timestamp_seconds < nextCueSec;
      }
      return chk.timestamp_seconds >= cueSec;
    });
  };

  if (!transcript) return null;

  return (
    <details className="group rounded-2xl border border-border bg-surface-elevated shadow-sm transition-all open:ring-1 open:ring-primary/20">
      <summary className="flex cursor-pointer items-center justify-between p-4 text-sm font-medium text-fg hover:text-primary select-none">
        <div className="flex items-center gap-2">
          <FileText className="size-4 text-primary" aria-hidden="true" />
          <span>Synchronized Transcript & Checkpoint Markers</span>
          {checkpoints.length > 0 && (
            <span className="rounded-full bg-primary-100 px-2 py-0.5 text-xs font-semibold text-primary dark:bg-primary-950">
              {checkpoints.filter((c) => c.status === "correct" || c.status === "answered").length} / {checkpoints.length} checks done
            </span>
          )}
        </div>
        <span className="text-xs text-fg-muted group-open:rotate-180 transition-transform">▼</span>
      </summary>

      <div
        ref={containerRef}
        className="max-h-72 overflow-y-auto border-t border-border p-4 space-y-2 scrollbar-thin scrollbar-thumb-border"
      >
        {cues.map((cue, idx) => {
          const isActive = idx === activeCueIndex;
          const isPast = currentTime > cue.seconds;
          const nextSec = idx + 1 < cues.length ? cues[idx + 1].seconds : null;
          const checkpoint = getCheckpointNear(cue.seconds, nextSec);

          return (
            <div
              key={cue.id}
              ref={isActive ? activeCueRef : null}
              className={`group flex items-start gap-3 rounded-xl p-2.5 transition-all text-xs leading-relaxed ${
                isActive
                  ? "bg-primary-50 dark:bg-primary-950/40 border border-primary/30 text-fg shadow-sm font-medium"
                  : isPast
                  ? "text-fg hover:bg-surface"
                  : "text-fg-muted/80 hover:bg-surface"
              }`}
            >
              <button
                type="button"
                onClick={() => onSeekTo?.(cue.seconds)}
                className={`flex shrink-0 items-center gap-1 font-mono text-[11px] rounded px-1.5 py-0.5 transition-colors ${
                  isActive
                    ? "bg-primary text-primary-fg font-semibold"
                    : "bg-surface-muted text-fg-muted hover:bg-primary hover:text-primary-fg"
                }`}
                title={`Seek to ${cue.timeLabel}`}
              >
                <PlayCircle className="size-3" />
                <span>{cue.timeLabel}</span>
              </button>

              <div className="flex-1">
                <p>{cue.text}</p>
                {checkpoint && (
                  <div className="mt-1 flex items-center gap-1 text-[11px] font-semibold text-primary">
                    <CheckCircle2
                      className={`size-3 ${
                        checkpoint.status === "correct" || checkpoint.status === "answered"
                          ? "text-success"
                          : "text-warning"
                      }`}
                    />
                    <span>
                      Checkpoint: {checkpoint.question.slice(0, 60)}
                      {checkpoint.question.length > 60 ? "..." : ""}
                    </span>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </details>
  );
}
