"use client";

import React from "react";
import { CheckCircle2, FileQuestion } from "lucide-react";

import { Badge, Card, EmptyState } from "@/components/ui";
import type { ProgressReporter } from "@/hooks/use-progress-reporter";
import type { PlayerItem } from "@/types/learning";
import { ArticleViewer } from "./article-viewer";
import { AssignmentRenderer } from "./assignment-renderer";
import { DocumentViewer } from "./document-viewer";
import { InteractiveVideoPlayer } from "./interactive-video-player";
import { MediaPlayer } from "./media-player";
import { QuizRenderer } from "./quiz-renderer";
import type { QuizAttemptData } from "./types";
import { YouTubePlayer } from "./youtube-player";

interface ContentRendererProps {
  item: PlayerItem;
  completed: boolean;
  /** Progress already saved for this item, so playback can resume. */
  initialPercent: number;
  positionSeconds: number;
  reporter: ProgressReporter;
  /** Assignment handed in; the server has completed the item. */
  onAssignmentSubmitted: () => void;
  onQuizGraded: (result: QuizAttemptData) => void;
  onContinue: () => void;
}

function Unavailable({ title, message }: { title: string; message: string }) {
  return (
    <Card className="mx-auto max-w-lg p-2">
      <EmptyState icon={FileQuestion} size="sm" title={title} description={message} />
    </Card>
  );
}

/** A video or audio lesson: the player, then what it is about and what it builds. */
function MediaLesson({
  item,
  completed,
  children,
}: {
  item: PlayerItem;
  completed: boolean;
  children: React.ReactNode;
}) {
  return (
    <div className="mx-auto max-w-4xl space-y-5">
      {children}
      <header className="space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="info">{item.content_type === "AUDIO" ? "Audio" : "Video"}</Badge>
          {completed && (
            <Badge variant="success">
              <CheckCircle2 className="mr-1 size-3" aria-hidden="true" />
              Completed
            </Badge>
          )}
        </div>
        <h2 className="text-xl font-semibold tracking-tight text-fg">{item.title}</h2>
        {item.description && <p className="text-sm text-fg-muted">{item.description}</p>}
        {item.competency_names.length > 0 && (
          <p className="flex flex-wrap items-center gap-1.5 text-xs text-fg-muted">
            Builds:
            {item.competency_names.map((name) => (
              <Badge key={name} variant="primary">
                {name}
              </Badge>
            ))}
          </p>
        )}
      </header>

      {item.transcript && item.content_type !== "VIDEO" && (
        <details className="rounded-xl border border-border bg-surface-elevated p-4">
          <summary className="cursor-pointer text-sm font-medium text-fg">Transcript</summary>
          <p className="mt-3 whitespace-pre-line text-sm leading-relaxed text-fg-muted">{item.transcript}</p>
        </details>
      )}
    </div>
  );
}

/**
 * Chooses how to present a lesson item from what the API says it is.
 * Nothing here is specific to any course: presentation follows the item's kind and media.
 */
export function ContentRenderer({
  item,
  completed,
  initialPercent,
  positionSeconds,
  reporter,
  onAssignmentSubmitted,
  onQuizGraded,
  onContinue,
}: ContentRendererProps) {
  if (item.kind === "assessment") {
    return item.quiz_id ? (
      <QuizRenderer quizId={item.quiz_id} onGraded={onQuizGraded} onContinue={onContinue} />
    ) : (
      <Unavailable title="Assessment not available" message="This assessment has not been set up yet." />
    );
  }

  if (item.kind === "assignment") {
    return item.assignment ? (
      <AssignmentRenderer item={item} assignment={item.assignment} onSubmitted={onAssignmentSubmitted} />
    ) : (
      <Unavailable title="Assignment not available" message="This assignment has not been set up yet." />
    );
  }

  const media = item.media;
  const isVideoLike = item.content_type === "VIDEO" || item.content_type === "AUDIO";

  if (media?.provider === "youtube" && media.video_id) {
    return (
      <MediaLesson item={item} completed={completed}>
        <YouTubePlayer
          videoId={media.video_id}
          title={item.title}
          contentItemId={item.id}
          transcript={item.transcript}
          startSeconds={positionSeconds}
          initialPercent={initialPercent}
          completed={completed}
          reporter={reporter}
        />
      </MediaLesson>
    );
  }

  if (media && media.provider === "html5_video") {
    return (
      <MediaLesson item={item} completed={completed}>
        <InteractiveVideoPlayer
          contentItemId={item.id}
          title={item.title}
          kind="video"
          src={media.url}
          transcript={item.transcript}
          startSeconds={positionSeconds}
          initialPercent={initialPercent}
          completed={completed}
          reporter={reporter}
        />
      </MediaLesson>
    );
  }

  if (media && media.provider === "html5_audio") {
    return (
      <MediaLesson item={item} completed={completed}>
        <MediaPlayer
          kind="audio"
          title={item.title}
          src={media.url}
          startSeconds={positionSeconds}
          initialPercent={initialPercent}
          reporter={reporter}
        />
      </MediaLesson>
    );
  }

  if (media?.provider === "file") {
    const mime = media.mime_type ?? "";
    if (mime.startsWith("video/")) {
      return (
        <MediaLesson item={item} completed={completed}>
          <InteractiveVideoPlayer
            contentItemId={item.id}
            title={item.title}
            kind="video"
            authedPath={media.url}
            transcript={item.transcript}
            startSeconds={positionSeconds}
            initialPercent={initialPercent}
            completed={completed}
            reporter={reporter}
          />
        </MediaLesson>
      );
    }
    if (mime.startsWith("audio/")) {
      return (
        <MediaLesson item={item} completed={completed}>
          <MediaPlayer
            kind="audio"
            title={item.title}
            authedPath={media.url}
            startSeconds={positionSeconds}
            initialPercent={initialPercent}
            reporter={reporter}
          />
        </MediaLesson>
      );
    }
    return <DocumentViewer item={item} completed={completed} reporter={reporter} />;
  }

  if (isVideoLike) {
    return (
      <Unavailable
        title="Media unavailable"
        message="This lesson has no playable source. Tell your administrator so it can be fixed."
      />
    );
  }

  if (item.text_content) {
    return <ArticleViewer item={item} completed={completed} reporter={reporter} />;
  }

  return <Unavailable title="Nothing to show" message="This lesson has no content yet." />;
}
