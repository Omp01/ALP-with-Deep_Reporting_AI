"use client";

import React, { useEffect, useState, useRef } from "react";
import {
  CheckCircle2,
  XCircle,
  Sparkles,
  Clock,
  ArrowRight,
  RotateCcw,
  X,
  PlayCircle,
  HelpCircle,
  ChevronDown,
  ChevronUp,
  Calculator,
  Tag,
} from "lucide-react";
import { Badge, Button, Spinner } from "@/components/ui";
import type { VideoCheckpoint, VideoCheckpointAnswerResponse } from "@/types/learning";

interface VideoFlashCardProps {
  checkpoint: VideoCheckpoint;
  totalCheckpoints: number;
  currentIndex: number;
  initialCountdownSeconds?: number;
  onAnswer: (selectedOptionId: string) => Promise<VideoCheckpointAnswerResponse>;
  onResume: () => void;
  onSeekToSection?: (startSeconds: number) => void;
}

export function VideoFlashCard({
  checkpoint,
  totalCheckpoints,
  currentIndex,
  initialCountdownSeconds = 15,
  onAnswer,
  onResume,
  onSeekToSection,
}: VideoFlashCardProps) {
  const [selectedOption, setSelectedOption] = useState<string | null>(
    checkpoint.selected_option_id ?? null
  );
  const [submitting, setSubmitting] = useState(false);
  const [showCalculation, setShowCalculation] = useState(false);
  const [answerResult, setAnswerResult] = useState<VideoCheckpointAnswerResponse | null>(
    checkpoint.status === "correct" || checkpoint.status === "incorrect"
      ? {
          checkpoint_id: checkpoint.id,
          is_correct: checkpoint.status === "correct",
          status: checkpoint.status as "correct" | "incorrect",
          selected_option_id: checkpoint.selected_option_id || "",
          correct_option_id: checkpoint.correct_option_id || "",
          score: checkpoint.score || 0,
          max_score: checkpoint.max_score || 10,
          attempt_number: checkpoint.attempt_count || 1,
          formula_id: checkpoint.formula_id || "attempt_decay_v1",
          formula_version: "1.0.0",
          calculation_details: (checkpoint.calculation_details as Record<string, any>) || null,
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
    setShowCalculation(false);
    setTimeLeft(initialCountdownSeconds);
  };

  const progressPercent = Math.round((timeLeft / initialCountdownSeconds) * 100);
  const activeTopic = answerResult?.remediation?.topic || checkpoint.topic;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="flashcard-title"
      className="absolute inset-0 z-50 flex items-center justify-center bg-black/80 p-2 sm:p-4 backdrop-blur-md transition-all duration-300 animate-in fade-in"
    >
      <div className="relative flex flex-col w-full max-w-lg max-h-[92%] rounded-2xl border border-border/80 bg-surface-elevated/95 shadow-2xl backdrop-blur-lg overflow-hidden animate-in zoom-in-95 duration-200">
        
        {/* Top Header */}
        <div className="flex shrink-0 items-center justify-between border-b border-border/70 px-4 py-3 bg-surface/90">
          <div className="flex items-center gap-2">
            <span className="flex size-7 items-center justify-center rounded-lg bg-primary-100 text-primary dark:bg-primary-950">
              <Sparkles className="size-4" aria-hidden="true" />
            </span>
            <div>
              <div className="flex items-center gap-2">
                <h3 id="flashcard-title" className="text-xs sm:text-sm font-semibold tracking-tight text-fg">
                  AI Flashcard · Checkpoint {currentIndex + 1} of {totalCheckpoints}
                </h3>
                {activeTopic && (
                  <span className="hidden sm:inline-flex items-center gap-1 text-[10px] font-medium px-2 py-0.5 rounded-full bg-primary/10 text-primary border border-primary/20">
                    <Tag className="size-2.5" />
                    {activeTopic}
                  </span>
                )}
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {!answerResult && (
              <div className="flex items-center gap-1 rounded-full bg-surface-muted px-2.5 py-0.5 text-[11px] font-medium text-fg-muted border border-border">
                <Clock className="size-3 text-warning" aria-hidden="true" />
                <span>{timeLeft}s</span>
              </div>
            )}

            {answerResult && (
              <div className="flex items-center gap-1.5">
                <Badge
                  variant={answerResult.is_correct ? "success" : "warning"}
                  className="text-[11px] py-0.5 px-2 font-medium"
                >
                  {answerResult.is_correct ? "Correct!" : "Needs Review"}
                </Badge>
                {answerResult.score !== undefined && (
                  <span className="text-[11px] font-semibold px-2 py-0.5 rounded-md bg-surface-muted border border-border text-fg">
                    {answerResult.score} / {answerResult.max_score ?? 10} pts
                  </span>
                )}
              </div>
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
        <div className="flex-1 overflow-y-auto px-4 py-3.5 space-y-3 scrollbar-thin scrollbar-thumb-border">
          {/* Mobile Topic Badge */}
          {activeTopic && (
            <div className="sm:hidden">
              <span className="inline-flex items-center gap-1 text-[11px] font-medium px-2 py-0.5 rounded-full bg-primary/10 text-primary border border-primary/20">
                <Tag className="size-2.5" />
                {activeTopic}
              </span>
            </div>
          )}

          {checkpoint.transcript_segment && !answerResult && (
            <div className="rounded-xl bg-surface px-3 py-2 text-[11px] italic text-fg-muted border border-border/60">
              <span className="font-semibold not-italic text-fg">Context: </span>
              &ldquo;{checkpoint.transcript_segment.slice(0, 130)}
              {checkpoint.transcript_segment.length > 130 ? "..." : ""}&rdquo;
            </div>
          )}

          <p className="text-sm font-medium leading-snug text-fg">
            {checkpoint.question}
          </p>

          {/* Multiple Choice Options */}
          <div className="space-y-2 pt-0.5">
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
                  className={`group flex w-full items-start gap-2.5 rounded-xl border p-2.5 text-left text-xs transition-all focus:outline-none focus:ring-2 focus:ring-primary/40 ${btnClass}`}
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
                    <CheckCircle2 className="size-4 shrink-0 text-success" aria-hidden="true" />
                  )}
                  {answerResult && isChosen && !answerResult.is_correct && (
                    <XCircle className="size-4 shrink-0 text-warning" aria-hidden="true" />
                  )}
                </button>
              );
            })}
          </div>

          {/* Feedback & Traceable Remediation Section */}
          {answerResult && (
            <div className="space-y-2.5 pt-1 animate-in fade-in duration-200">
              <div
                className={`rounded-xl border p-3 text-xs leading-relaxed ${
                  answerResult.is_correct
                    ? "border-success/30 bg-success/5"
                    : "border-warning/30 bg-warning/5"
                }`}
              >
                <div
                  className={`flex items-center gap-1.5 font-semibold ${
                    answerResult.is_correct ? "text-success" : "text-warning"
                  }`}
                >
                  {answerResult.is_correct ? (
                    <>
                      <CheckCircle2 className="size-4" />
                      <span>Great comprehension!</span>
                    </>
                  ) : (
                    <>
                      <XCircle className="size-4" />
                      <span>Key takeaway & remediation:</span>
                    </>
                  )}
                </div>
                {answerResult.explanation && (
                  <p className="mt-1.5 text-fg-muted">{answerResult.explanation}</p>
                )}

                {/* Video Timestamp Remediation Card */}
                {answerResult.remediation && (
                  <div className="mt-2.5 rounded-lg border border-border bg-surface p-2.5 text-xs flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2 shadow-sm">
                    <div className="space-y-0.5">
                      <div className="flex items-center gap-1.5 text-fg font-medium">
                        <PlayCircle className="size-3.5 text-primary shrink-0" />
                        <span>Recommended Section: {answerResult.remediation.section_label}</span>
                      </div>
                      <p className="text-[11px] text-fg-muted line-clamp-1">
                        {answerResult.remediation.video_title} · {answerResult.remediation.topic}
                      </p>
                    </div>

                    {onSeekToSection && (
                      <Button
                        size="sm"
                        variant="secondary"
                        onClick={() => {
                          if (answerResult.remediation) {
                            onSeekToSection(answerResult.remediation.timestamp_start_seconds);
                          }
                        }}
                        className="text-xs h-7 px-2.5 shrink-0 flex items-center gap-1 shadow-sm font-medium"
                      >
                        <PlayCircle className="size-3 text-primary" />
                        <span>Watch Section</span>
                      </Button>
                    )}
                  </div>
                )}
              </div>

              {/* Score Transparency / How was this calculated toggle */}
              {answerResult.calculation_details && (
                <div className="rounded-xl border border-border/80 bg-surface/70 overflow-hidden text-xs">
                  <button
                    type="button"
                    onClick={() => setShowCalculation(!showCalculation)}
                    className="w-full flex items-center justify-between px-3 py-2 text-fg-muted hover:text-fg hover:bg-surface-muted/50 transition-colors"
                  >
                    <span className="flex items-center gap-1.5 font-medium text-[11px]">
                      <Calculator className="size-3.5 text-primary" />
                      <span>How was my score calculated?</span>
                    </span>
                    {showCalculation ? (
                      <ChevronUp className="size-3.5 text-fg-muted" />
                    ) : (
                      <ChevronDown className="size-3.5 text-fg-muted" />
                    )}
                  </button>

                  {showCalculation && (
                    <div className="px-3 pb-3 pt-1 border-t border-border/60 space-y-2 text-[11px] text-fg-muted bg-surface/90">
                      <div className="grid grid-cols-2 gap-2 pt-1 font-mono text-[10px]">
                        <div className="rounded bg-surface-muted p-1.5 border border-border/60">
                          <span className="text-fg-muted block">Base Max:</span>
                          <span className="text-fg font-semibold">{answerResult.calculation_details.max_marks ?? 10} pts</span>
                        </div>
                        <div className="rounded bg-surface-muted p-1.5 border border-border/60">
                          <span className="text-fg-muted block">Attempt:</span>
                          <span className="text-fg font-semibold">#{answerResult.calculation_details.attempt_number ?? 1}</span>
                        </div>
                        <div className="rounded bg-surface-muted p-1.5 border border-border/60">
                          <span className="text-fg-muted block">Retry Penalty (P):</span>
                          <span className="text-fg font-semibold">{answerResult.calculation_details.penalty_p ?? 0.25}</span>
                        </div>
                        <div className="rounded bg-surface-muted p-1.5 border border-border/60">
                          <span className="text-fg-muted block">Attempt Factor:</span>
                          <span className="text-fg font-semibold">{answerResult.calculation_details.attempt_factor ?? 1.0}</span>
                        </div>
                      </div>

                      {answerResult.calculation_details.formula_expression && (
                        <div className="rounded bg-surface-muted/80 p-2 font-mono text-[10px] text-fg border border-border/40">
                          <span className="text-fg-muted block text-[9px]">Formula Expression:</span>
                          {answerResult.calculation_details.formula_expression}
                        </div>
                      )}

                      {answerResult.calculation_details.reason && (
                        <p className="text-[10px] text-fg-muted italic">
                          {answerResult.calculation_details.reason}
                        </p>
                      )}
                    </div>
                  )}
                </div>
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

        {/* Action Footer */}
        <div className="shrink-0 flex items-center justify-between border-t border-border/70 px-4 py-2.5 bg-surface/95">
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
            className="flex items-center gap-1.5 text-xs h-8 px-3.5 shadow-md font-medium"
          >
            <span>Continue Video</span>
            <ArrowRight className="size-3" />
          </Button>
        </div>

      </div>
    </div>
  );
}
