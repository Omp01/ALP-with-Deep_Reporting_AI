"use client";

import React, { useEffect, useState, useRef } from "react";
import { CheckCircle2, XCircle, Sparkles, Clock, ArrowRight, RotateCcw, X } from "lucide-react";
import { Badge, Button, Spinner } from "@/components/ui";
import type { VideoCheckpoint, VideoCheckpointAnswerResponse } from "@/types/learning";

interface VideoFlashCardProps {
  checkpoint: VideoCheckpoint;
  totalCheckpoints: number;
  currentIndex: number;
  initialCountdownSeconds?: number;
  onAnswer: (selectedOptionId: string) => Promise<VideoCheckpointAnswerResponse>;
  onResume: () => void;
}

export function VideoFlashCard({
  checkpoint,
  totalCheckpoints,
  currentIndex,
  initialCountdownSeconds = 15,
  onAnswer,
  onResume,
}: VideoFlashCardProps) {
  const [selectedOption, setSelectedOption] = useState<string | null>(
    checkpoint.selected_option_id ?? null
  );
  const [submitting, setSubmitting] = useState(false);
  const [answerResult, setAnswerResult] = useState<VideoCheckpointAnswerResponse | null>(
    checkpoint.status === "correct" || checkpoint.status === "incorrect"
      ? {
          checkpoint_id: checkpoint.id,
          is_correct: checkpoint.status === "correct",
          status: checkpoint.status as "correct" | "incorrect",
          selected_option_id: checkpoint.selected_option_id || "",
          correct_option_id: checkpoint.correct_option_id || "",
          explanation: checkpoint.explanation || null,
          all_checkpoints_completed: false,
        }
      : null
  );
  const [timeLeft, setTimeLeft] = useState(initialCountdownSeconds);
  const timerRef = useRef<NodeJS.Timeout | null>(null);

  // Countdown timer for pending checkpoints
  useEffect(() => {
    if (answerResult) return; // Stop counting once answered

    timerRef.current = setInterval(() => {
      setTimeLeft((prev) => {
        if (prev <= 1) {
          if (timerRef.current) clearInterval(timerRef.current);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [answerResult]);

  const handleSelect = async (optionId: string) => {
    if (submitting || answerResult) return;
    setSelectedOption(optionId);
    setSubmitting(true);

    try {
      const res = await onAnswer(optionId);
      setAnswerResult(res);
    } catch (err) {
      console.error("Failed to submit checkpoint answer", err);
    } finally {
      setSubmitting(false);
    }
  };

  const handleRetry = () => {
    setAnswerResult(null);
    setSelectedOption(null);
    setTimeLeft(initialCountdownSeconds);
  };

  const progressPercent = Math.round((timeLeft / initialCountdownSeconds) * 100);

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="flashcard-title"
      className="absolute inset-0 z-50 flex items-center justify-center bg-black/75 p-2 sm:p-4 backdrop-blur-sm transition-all duration-300 animate-in fade-in"
    >
      <div className="relative flex flex-col w-full max-w-md max-h-[90%] rounded-2xl border border-border bg-surface-elevated/95 shadow-2xl backdrop-blur-md overflow-hidden animate-in zoom-in-95 duration-200">
        
        {/* Top Header */}
        <div className="flex shrink-0 items-center justify-between border-b border-border px-4 py-3 bg-surface/80">
          <div className="flex items-center gap-2">
            <span className="flex size-6 items-center justify-center rounded-lg bg-primary-100 text-primary dark:bg-primary-950">
              <Sparkles className="size-3.5" aria-hidden="true" />
            </span>
            <div>
              <h3 id="flashcard-title" className="text-xs sm:text-sm font-semibold tracking-tight text-fg">
                Quick Check · Checkpoint {currentIndex + 1} of {totalCheckpoints}
              </h3>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {!answerResult && (
              <div className="flex items-center gap-1 rounded-full bg-surface-muted px-2 py-0.5 text-[11px] font-medium text-fg-muted border border-border">
                <Clock className="size-2.5 text-warning" aria-hidden="true" />
                <span>{timeLeft}s</span>
              </div>
            )}

            {answerResult && (
              <Badge variant={answerResult.is_correct ? "success" : "warning"} className="text-[11px] py-0 px-2">
                {answerResult.is_correct ? "Correct!" : "Needs Review"}
              </Badge>
            )}

            {/* Always visible Close/Resume button so learner is never stuck */}
            <button
              type="button"
              onClick={onResume}
              className="rounded-lg p-1 text-fg-muted hover:bg-surface-muted hover:text-fg transition-colors"
              title="Resume Video"
              aria-label="Resume Video"
            >
              <X className="size-4" />
            </button>
          </div>
        </div>

        {/* Timer countdown progress bar */}
        {!answerResult && (
          <div className="h-0.5 w-full overflow-hidden bg-surface-muted">
            <div
              className="h-full bg-primary transition-all duration-1000 ease-linear"
              style={{ width: `${progressPercent}%` }}
            />
          </div>
        )}

        {/* Scrollable Content Body */}
        <div className="flex-1 overflow-y-auto px-4 py-3 space-y-2.5 scrollbar-thin scrollbar-thumb-border">
          {checkpoint.transcript_segment && !answerResult && (
            <div className="rounded-lg bg-surface px-2.5 py-1.5 text-[11px] italic text-fg-muted border border-border/60">
              <span className="font-semibold not-italic text-fg">Context: </span>
              &ldquo;{checkpoint.transcript_segment.slice(0, 110)}
              {checkpoint.transcript_segment.length > 110 ? "..." : ""}&rdquo;
            </div>
          )}

          <p className="text-xs sm:text-sm font-medium leading-snug text-fg">
            {checkpoint.question}
          </p>

          {/* Multiple Choice Options */}
          <div className="space-y-1.5 pt-0.5">
            {checkpoint.options.map((opt) => {
              const isChosen = selectedOption === opt.id;
              let btnClass = "border-border hover:bg-surface-elevated/80 hover:border-primary/50 text-fg";

              if (answerResult) {
                if (opt.id === answerResult.correct_option_id) {
                  btnClass = "border-success bg-success-light text-success font-medium";
                } else if (isChosen && !answerResult.is_correct) {
                  btnClass = "border-warning bg-warning-light text-warning line-through";
                } else {
                  btnClass = "border-border/40 opacity-50 text-fg-muted";
                }
              } else if (isChosen) {
                btnClass = "border-primary bg-primary-50 dark:bg-primary-950/40 text-primary font-medium";
              }

              return (
                <button
                  key={opt.id}
                  type="button"
                  disabled={submitting || answerResult !== null}
                  onClick={() => handleSelect(opt.id)}
                  className={`group flex w-full items-start gap-2.5 rounded-xl border p-2 text-left text-xs transition-all focus:outline-none focus:ring-2 focus:ring-primary/40 ${btnClass}`}
                >
                  <span
                    className={`flex size-5 shrink-0 items-center justify-center rounded-full text-[10px] font-semibold ${
                      isChosen || (answerResult && opt.id === answerResult.correct_option_id)
                        ? "bg-primary text-primary-fg"
                        : "bg-surface-muted text-fg-muted group-hover:bg-primary-100 dark:group-hover:bg-primary-950"
                    }`}
                  >
                    {opt.id}
                  </span>
                  <span className="flex-1 leading-tight">{opt.text}</span>
                  {answerResult && opt.id === answerResult.correct_option_id && (
                    <CheckCircle2 className="size-3.5 shrink-0 text-success" aria-hidden="true" />
                  )}
                  {answerResult && isChosen && !answerResult.is_correct && (
                    <XCircle className="size-3.5 shrink-0 text-warning" aria-hidden="true" />
                  )}
                </button>
              );
            })}
          </div>

          {/* Feedback & Explanation */}
          {answerResult && (
            <div className="rounded-xl border p-2.5 text-[11px] leading-relaxed animate-in fade-in duration-200">
              <div
                className={`flex items-center gap-1.5 font-semibold ${
                  answerResult.is_correct ? "text-success" : "text-warning"
                }`}
              >
                {answerResult.is_correct ? (
                  <>
                    <CheckCircle2 className="size-3.5" />
                    <span>Great comprehension!</span>
                  </>
                ) : (
                  <>
                    <XCircle className="size-3.5" />
                    <span>Key takeaway:</span>
                  </>
                )}
              </div>
              {answerResult.explanation && (
                <p className="mt-1 text-fg-muted">{answerResult.explanation}</p>
              )}
            </div>
          )}

          {/* Submitting spinner */}
          {submitting && (
            <div className="flex items-center justify-center gap-2 py-1 text-xs text-fg-muted">
              <Spinner size="sm" />
              <span>Verifying answer...</span>
            </div>
          )}
        </div>

        {/* Sticky Action Footer: ALWAYS visible and never clipped */}
        <div className="shrink-0 flex items-center justify-between border-t border-border px-4 py-2.5 bg-surface/90">
          <div>
            {answerResult && !answerResult.is_correct ? (
              <Button
                variant="outline"
                size="sm"
                onClick={handleRetry}
                className="flex items-center gap-1 text-xs h-8 px-2.5"
              >
                <RotateCcw className="size-3" />
                <span>Try Again</span>
              </Button>
            ) : (
              <span className="text-[11px] text-fg-muted">
                {answerResult ? "Check completed" : "Select an answer"}
              </span>
            )}
          </div>

          <Button
            variant="primary"
            size="sm"
            onClick={onResume}
            className="flex items-center gap-1 text-xs h-8 px-3 shadow-md font-medium"
          >
            <span>Continue Video</span>
            <ArrowRight className="size-3" />
          </Button>
        </div>

      </div>
    </div>
  );
}
