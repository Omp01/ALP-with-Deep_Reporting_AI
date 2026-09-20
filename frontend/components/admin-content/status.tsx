"use client";

import * as React from "react";
import {
  AlertTriangle,
  CheckCircle2,
  CircleDashed,
  Loader2,
  MinusCircle,
  XCircle,
} from "lucide-react";

import { Badge } from "@/components/ui";
import { cn } from "@/lib/utils";
import type { ContentStatus, IngestionStage, JobStatus } from "@/types/content-admin";

type Variant = "neutral" | "primary" | "success" | "warning" | "danger" | "info";

/**
 * What an administrator should read from an item's state. Two facts combine: the item's own
 * status and how its last processing run ended, so "review" alone never hides that AI failed.
 */
export function describeState(
  status: ContentStatus,
  job: JobStatus | null
): { label: string; variant: Variant } {
  if (status === "published") return { label: "Published", variant: "success" };
  if (status === "failed" || job === "failed") return { label: "Failed", variant: "danger" };
  if (status === "processing" || job === "processing" || job === "pending")
    return { label: "Processing", variant: "primary" };
  if (job === "needs_attention") return { label: "Needs attention", variant: "warning" };
  if (status === "review") return { label: "Ready for review", variant: "info" };
  if (status === "archived") return { label: "Archived", variant: "neutral" };
  return { label: "Draft", variant: "neutral" };
}

export function ContentStateBadge({
  status,
  job,
}: {
  status: ContentStatus;
  job: JobStatus | null;
}) {
  const { label, variant } = describeState(status, job);
  return <Badge variant={variant}>{label}</Badge>;
}

const TYPE_LABELS: Record<string, string> = {
  VIDEO: "Video",
  AUDIO: "Audio",
  DOCUMENT: "Document",
  ARTICLE: "Article",
  QUIZ: "Quiz",
  ASSIGNMENT: "Assignment",
};

export function typeLabel(type: string): string {
  return TYPE_LABELS[type] ?? type;
}

export function sourceLabel(source: string): string {
  if (source === "youtube") return "YouTube";
  if (source === "upload") return "Upload";
  if (source === "authored") return "Written in LMS";
  return source;
}

const STAGE_LABELS: Record<string, string> = {
  metadata: "Fetch video details and captions",
  extract: "Read the file",
  transcribe: "Transcribe the recording",
  chunk: "Split into passages",
  analyze: "Analyse the content",
  questions: "Draft and verify questions",
  embed: "Index for search",
};

export function stageLabel(name: string): string {
  return STAGE_LABELS[name] ?? name;
}

function StageIcon({ status }: { status: IngestionStage["status"] }) {
  const base = "size-4 shrink-0";
  switch (status) {
    case "done":
      return <CheckCircle2 className={cn(base, "text-success")} aria-hidden="true" />;
    case "running":
      return <Loader2 className={cn(base, "animate-spin text-primary")} aria-hidden="true" />;
    case "failed":
      return <XCircle className={cn(base, "text-danger")} aria-hidden="true" />;
    case "skipped":
      return <MinusCircle className={cn(base, "text-fg-subtle")} aria-hidden="true" />;
    default:
      return <CircleDashed className={cn(base, "text-fg-subtle")} aria-hidden="true" />;
  }
}

const STAGE_STATUS_TEXT: Record<IngestionStage["status"], string> = {
  pending: "Waiting",
  running: "In progress",
  done: "Done",
  skipped: "Skipped",
  failed: "Failed",
};

/** The pipeline's stages, each with its real outcome and detail. Nothing here is decorative. */
export function StageTracker({ stages }: { stages: IngestionStage[] }) {
  return (
    <ol className="space-y-3" aria-label="Processing steps">
      {stages.map((stage) => (
        <li key={stage.name} className="flex gap-3" data-stage={stage.name} data-status={stage.status}>
          <span className="mt-0.5">
            <StageIcon status={stage.status} />
          </span>
          <div className="min-w-0">
            <p className="text-sm font-medium text-fg">
              {stageLabel(stage.name)}
              <span className="sr-only">: {STAGE_STATUS_TEXT[stage.status]}</span>
            </p>
            {stage.error ? (
              <p className="mt-0.5 flex items-start gap-1.5 text-xs text-danger">
                <AlertTriangle className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
                {stage.error.message}
              </p>
            ) : stage.detail ? (
              <p className="mt-0.5 text-xs text-fg-muted">{stage.detail}</p>
            ) : null}
          </div>
        </li>
      ))}
    </ol>
  );
}
