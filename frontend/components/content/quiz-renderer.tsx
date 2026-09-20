"use client";

import React, { useRef, useState, useEffect } from "react";
import {
  HelpCircle,
  CheckCircle2,
  XCircle,
  Clock,
  Award,
  ArrowRight,
  ArrowLeft,
  RotateCcw,
  Sparkles,
  AlertTriangle,
  Hourglass,
} from "lucide-react";
import {
  Button,
  Badge,
  ConfirmDialog,
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
  CardFooter,
  Progress,
  Spinner,
  Textarea,
  useToast,
} from "@/components/ui";
import { useLearningEvents } from "@/hooks/use-learning-events";
import { apiClient } from "@/lib/api-client";
import {
  QuizMetaData,
  QuizQuestionData,
  QuizAttemptData,
} from "./types";

interface QuizRendererProps {
  /** The quiz linked to this lesson item (from the player payload). */
  quizId: string;
  /** Called after an attempt is graded. The server completes the lesson item itself. */
  onGraded?: (result: QuizAttemptData) => void;
  /** "Continue" after a pass. */
  onContinue?: () => void;
}

export function QuizRenderer({ quizId, onGraded, onContinue }: QuizRendererProps) {
  const { toast } = useToast();

  const resolvedQuizId = quizId;
  const [quizNotFound, setQuizNotFound] = useState<boolean>(false);
  const [confirmSubmit, setConfirmSubmit] = useState<boolean>(false);
  const [quizMeta, setQuizMeta] = useState<QuizMetaData | null>(null);
  const [questions, setQuestions] = useState<QuizQuestionData[]>([]);
  const [activeQuestionIdx, setActiveQuestionIdx] = useState<number>(0);
  const [selectedAnswers, setSelectedAnswers] = useState<Record<string, string>>({});
  const [writtenAnswers, setWrittenAnswers] = useState<Record<string, string>>({});
  const [currentAttempt, setCurrentAttempt] = useState<QuizAttemptData | null>(null);
  const [gradedResult, setGradedResult] = useState<QuizAttemptData | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [submitting, setSubmitting] = useState<boolean>(false);
  const [elapsedSeconds, setElapsedSeconds] = useState<number>(0);

  // Which question is on screen, and how long each has been (measured here, checked by the server).
  const events = useLearningEvents();
  const clock = useRef<{ id: string | null; since: number }>({ id: null, since: 0 });
  const millisecondsOn = useRef<Record<string, number>>({});
  const lastShown = useRef<string | null>(null);

  // 2. Load Quiz Metadata & Questions
  useEffect(() => {
    let mounted = true;
    Promise.all([
      apiClient.get<QuizMetaData>(`/api/v1/quizzes/${resolvedQuizId}`),
      apiClient.get<QuizQuestionData[]>(`/api/v1/quizzes/${resolvedQuizId}/questions`),
      apiClient.get<QuizAttemptData[]>(`/api/v1/quizzes/${resolvedQuizId}/attempts`),
    ])
      .then(([meta, qs, prevAttempts]) => {
        if (!mounted) return;
        setQuizMeta(meta);
        setQuestions(qs);
        if (prevAttempts.length > 0 && prevAttempts[0].completed_at) {
          setGradedResult(prevAttempts[0]);
        }
        setLoading(false);
      })
      .catch((err: unknown) => {
        if (!mounted) return;
        setQuizNotFound(true);
        toast({
          title: "Assessment unavailable",
          description:
            err instanceof Error ? err.message : "Failed to load quiz assessment.",
          variant: "error",
        });
        setLoading(false);
      });

    return () => {
      mounted = false;
    };
  }, [resolvedQuizId, toast]);

  // 3. Start a new attempt
  const handleStartAttempt = async () => {
    setLoading(true);
    try {
      const attempt = await apiClient.post<QuizAttemptData>(
        `/api/v1/quizzes/${resolvedQuizId}/attempts`,
        {}
      );
      setCurrentAttempt(attempt);
      setGradedResult(null);
      setSelectedAnswers({});
      setWrittenAnswers({});
      setActiveQuestionIdx(0);
      setElapsedSeconds(0);
      millisecondsOn.current = {};
      clock.current = { id: null, since: 0 };
      lastShown.current = null;
    } catch (err: unknown) {
      toast({
        title: "Cannot start attempt",
        description:
          err instanceof Error
            ? err.message
            : "Maximum attempts reached or session invalid.",
        variant: "error",
      });
    } finally {
      setLoading(false);
    }
  };

  // Timer ticker during active attempt
  useEffect(() => {
    let timer: NodeJS.Timeout;
    if (currentAttempt && !gradedResult) {
      timer = setInterval(() => {
        setElapsedSeconds((prev) => prev + 1);
      }, 1000);
    }
    return () => clearInterval(timer);
  }, [currentAttempt, gradedResult]);

  // A question becomes visible: bank the time on the previous one, note this one, and report it shown.
  const attemptId = currentAttempt?.id ?? null;
  const shownQuestionId = attemptId && !gradedResult ? (questions[activeQuestionIdx]?.id ?? null) : null;
  useEffect(() => {
    const now = Date.now();
    const previous = clock.current;
    if (previous.id) millisecondsOn.current[previous.id] = (millisecondsOn.current[previous.id] ?? 0) + (now - previous.since);
    clock.current = { id: shownQuestionId, since: now };
    if (!attemptId || !shownQuestionId) return;
    const key = `${attemptId}:${shownQuestionId}:${activeQuestionIdx}`;
    if (lastShown.current === key) return; // a repeated effect run, not a new showing
    lastShown.current = key;
    events.report("question_shown", { questionId: shownQuestionId }, { attempt_id: attemptId, position: activeQuestionIdx });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only a new question or attempt is a new showing
  }, [attemptId, shownQuestionId, activeQuestionIdx]);

  // 4. Select Option
  const handleSelectOption = (questionId: string, optionId: string) => {
    if (gradedResult) return;
    setSelectedAnswers((prev) => ({
      ...prev,
      [questionId]: optionId,
    }));
  };

  const handleWrite = (questionId: string, text: string) => {
    if (gradedResult) return;
    setWrittenAnswers((prev) => ({ ...prev, [questionId]: text }));
  };

  // 5. Submit Quiz
  const isWritten = (q: QuizQuestionData) => q.question_type === "short_answer" || q.question_type === "open_ended";
  const isAnswered = (q: QuizQuestionData) => (isWritten(q) ? (writtenAnswers[q.id] ?? "").trim().length > 0 : !!selectedAnswers[q.id]);
  const answeredCount = questions.filter(isAnswered).length;

  const handleSubmit = () => {
    if (answeredCount < questions.length) {
      setConfirmSubmit(true);
      return;
    }
    void submitAttempt();
  };

  const submitAttempt = async () => {
    if (!currentAttempt) return;
    setConfirmSubmit(false);
    setSubmitting(true);
    try {
      // Bank the time on the question that is showing now.
      const now = Date.now();
      if (clock.current.id) {
        millisecondsOn.current[clock.current.id] = (millisecondsOn.current[clock.current.id] ?? 0) + (now - clock.current.since);
        clock.current = { id: clock.current.id, since: now };
      }
      const payload = {
        responses: questions.map((q) => {
          const spent = Math.round(millisecondsOn.current[q.id] ?? 0);
          return {
            question_id: q.id,
            selected_option_id: isWritten(q) ? null : selectedAnswers[q.id] || null,
            ...(isWritten(q) ? { text_response: writtenAnswers[q.id] ?? "" } : {}),
            // Only questions that were actually shown carry a time; the server holds it to the attempt's real length.
            ...(spent > 0 ? { response_time_ms: spent } : {}),
          };
        }),
      };
      const result = await apiClient.post<QuizAttemptData>(
        `/api/v1/quizzes/${resolvedQuizId}/attempts/${currentAttempt.id}/submit`,
        payload
      );
      setGradedResult(result);
      setCurrentAttempt(null);

      onGraded?.(result);
      if (result.grading_status === "needs_review") {
        toast({
          title: "Waiting for a reviewer",
          description: "Some of your written answers could not be graded automatically. A reviewer will grade them and your result will update.",
          variant: "warning",
        });
      } else if (result.passed) {
        toast({
          title: "Assessment Passed!",
          description: `Score: ${result.score}% - Congratulations on mastering this competency.`,
          variant: "success",
        });
      } else {
        toast({
          title: "Assessment Submitted",
          description: `Score: ${result.score}%. Passing score is ${quizMeta?.passing_score}%. Review the feedback below.`,
          variant: "warning",
        });
      }
    } catch (err: unknown) {
      toast({
        title: "Submission failed",
        description:
          err instanceof Error ? err.message : "Could not grade assessment.",
        variant: "error",
      });
    } finally {
      setSubmitting(false);
    }
  };

  const formatTimer = (secs: number) => {
    const m = Math.floor(secs / 60);
    const s = Math.floor(secs % 60);
    return `${m}:${s < 10 ? "0" : ""}${s}`;
  };

  if (loading && !quizNotFound) {
    return (
      <div className="flex flex-col items-center justify-center p-12 gap-4">
        <Spinner size="lg" />
        <p className="text-sm text-fg-muted">Loading assessment questions & rubric...</p>
      </div>
    );
  }

  if (quizNotFound || !quizMeta || questions.length === 0) {
    return (
      <Card className="max-w-2xl mx-auto p-8 text-center">
        <HelpCircle className="w-12 h-12 mx-auto text-fg-muted mb-4 opacity-50" />
        <h3 className="text-lg font-semibold text-fg">Assessment Not Available</h3>
        <p className="text-sm text-fg-muted mt-2">
          No structured quiz items found for this lesson module.
        </p>
      </Card>
    );
  }

  // ---------------------------------------------------------------------------
  // View A: Post-Grading Results Card
  // ---------------------------------------------------------------------------
  if (gradedResult) {
    const isPassing = gradedResult.passed;
    const awaitingReview = gradedResult.grading_status === "needs_review";
    const responseMap = new Map(
      gradedResult.responses.map((r) => [r.question_id, r])
    );

    return (
      <div className="flex flex-col gap-6 max-w-3xl mx-auto">
        {/* Results Banner */}
        <div
          className={`p-6 rounded-xl border flex flex-col sm:flex-row items-center justify-between gap-6 ${
            awaitingReview
              ? "bg-warning-light border-warning/40 text-fg"
              : isPassing
              ? "bg-success/10 border-success/30 text-fg"
              : "bg-danger/10 border-danger/30 text-fg"
          }`}
        >
          <div className="flex items-center gap-4">
            <div
              className={`w-14 h-14 rounded-full flex items-center justify-center shrink-0 ${
                awaitingReview ? "bg-warning/20 text-warning" : isPassing ? "bg-success/20 text-success" : "bg-danger/20 text-danger"
              }`}
            >
              {awaitingReview ? (
                <Hourglass className="w-8 h-8" />
              ) : isPassing ? (
                <Award className="w-8 h-8" />
              ) : (
                <AlertTriangle className="w-8 h-8" />
              )}
            </div>
            <div>
              <div className="flex items-center gap-2">
                <Badge variant={awaitingReview ? "warning" : isPassing ? "success" : "danger"}>
                  {awaitingReview ? "Waiting for a reviewer" : isPassing ? "Passed" : "Not passed"}
                </Badge>
                <span className="text-xs text-fg-muted">
                  Attempt #{gradedResult.attempt_number}
                </span>
              </div>
              <h2 className="text-xl font-bold text-fg mt-1">
                {awaitingReview ? "Provisional score" : "Score"}: {gradedResult.score}%
              </h2>
              <p className="text-xs text-fg-muted mt-0.5">
                {awaitingReview
                  ? "Some written answers are waiting for a reviewer. The result is final once they are graded."
                  : `Passing requirement: ${quizMeta.passing_score}%`}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            {gradedResult.attempt_number < quizMeta.max_attempts && (
              <Button variant="secondary" onClick={handleStartAttempt}>
                <RotateCcw className="w-4 h-4 mr-1.5" /> Retake Quiz
              </Button>
            )}
            {isPassing && (
              <Button variant="primary" onClick={onContinue}>
                Continue Learning <ArrowRight className="w-4 h-4 ml-1.5" />
              </Button>
            )}
          </div>
        </div>

        {/* Detailed Question Review */}
        <div className="flex flex-col gap-4">
          <h3 className="text-sm font-semibold uppercase tracking-wider text-fg-muted">
            Question Review & Knowledge Remediation
          </h3>

          {questions.map((q, idx) => {
            const graded = responseMap.get(q.id);
            const written = isWritten(q);
            const waiting = graded?.grading_status === "needs_review";
            const fraction = graded?.score_fraction ?? null;
            // A written answer can be partly right; it counts as correct from 70% of the points.
            const isCorrect = written ? !waiting && (fraction ?? 0) >= 0.7 : graded?.is_correct;

            return (
              <Card
                key={q.id}
                className={`overflow-hidden border ${
                  waiting ? "border-warning/40 bg-surface" : isCorrect ? "border-success/30 bg-surface" : "border-danger/30 bg-surface"
                }`}
              >
                <CardHeader className="pb-3">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-xs font-mono font-medium text-fg-muted">
                      Question {idx + 1} of {questions.length}
                    </span>
                    <Badge variant={waiting ? "warning" : isCorrect ? "success" : "danger"}>
                      {waiting ? (
                        <>
                          <Hourglass className="w-3.5 h-3.5 mr-1" /> Waiting for a reviewer
                        </>
                      ) : written ? (
                        <>
                          {isCorrect ? <CheckCircle2 className="w-3.5 h-3.5 mr-1" /> : <XCircle className="w-3.5 h-3.5 mr-1" />}
                          {graded?.points_awarded} of {q.points} pts
                          {graded?.graded_by ? ` · graded by ${graded.graded_by === "human" ? "a reviewer" : "AI"}` : ""}
                        </>
                      ) : isCorrect ? (
                        <>
                          <CheckCircle2 className="w-3.5 h-3.5 mr-1" /> Correct (+{graded?.points_awarded} pts)
                        </>
                      ) : (
                        <>
                          <XCircle className="w-3.5 h-3.5 mr-1" /> Incorrect (0 pts)
                        </>
                      )}
                    </Badge>
                  </div>
                  <CardTitle className="text-base text-fg mt-2 font-semibold leading-snug">
                    {q.question_text}
                  </CardTitle>
                </CardHeader>

                <CardContent className="pt-0 space-y-2">
                  {q.options.map((opt) => {
                    const isSelected = graded?.selected_option_id === opt.id;
                    const isTargetCorrect = graded?.correct_option_id === opt.id;

                    let optionStyle = "border-border bg-surface-raised text-fg-muted";
                    if (isTargetCorrect) {
                      optionStyle = "border-success/60 bg-success/15 text-fg font-medium ring-1 ring-success/30";
                    } else if (isSelected && !isCorrect) {
                      optionStyle = "border-danger/60 bg-danger/15 text-fg line-through ring-1 ring-danger/30";
                    }

                    return (
                      <div
                        key={opt.id}
                        className={`p-3 rounded-lg border text-sm flex items-start gap-3 transition-colors ${optionStyle}`}
                      >
                        <div className="mt-0.5 shrink-0">
                          {isTargetCorrect ? (
                            <CheckCircle2 className="w-4 h-4 text-success" />
                          ) : isSelected && !isCorrect ? (
                            <XCircle className="w-4 h-4 text-danger" />
                          ) : (
                            <div className="w-4 h-4 rounded-full border border-border" />
                          )}
                        </div>
                        <span className="flex-1">{opt.option_text}</span>
                      </div>
                    );
                  })}

                  {written && graded?.feedback && (
                    <div className="mt-1 p-3 rounded-lg bg-surface-overlay/60 border border-border/80 text-xs text-fg-muted leading-relaxed">
                      <span className="font-semibold text-fg block mb-1">Feedback on your answer:</span>
                      {graded.feedback}
                    </div>
                  )}

                  {/* Explanation feedback */}
                  {graded?.explanation && (
                    <div className="mt-3 p-3 rounded-lg bg-surface-overlay/60 border border-border/80 text-xs text-fg-muted leading-relaxed">
                      <span className="font-semibold text-fg block mb-1 flex items-center gap-1.5">
                        <Sparkles className="w-3.5 h-3.5 text-primary" /> Pedagogical Explanation:
                      </span>
                      {graded.explanation}
                    </div>
                  )}
                </CardContent>
              </Card>
            );
          })}
        </div>
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // View B: Quiz Intro Card (Before Starting Attempt)
  // ---------------------------------------------------------------------------
  if (!currentAttempt) {
    return (
      <Card className="max-w-2xl mx-auto border-border">
        <CardHeader className="text-center pb-4">
          <div className="w-12 h-12 rounded-xl bg-primary/10 text-primary flex items-center justify-center mx-auto mb-3">
            <HelpCircle className="w-6 h-6" />
          </div>
          <CardTitle className="text-xl font-bold text-fg">{quizMeta.title}</CardTitle>
          {quizMeta.description && (
            <CardDescription className="text-sm mt-1.5">
              {quizMeta.description}
            </CardDescription>
          )}
        </CardHeader>

        <CardContent className="space-y-4">
          <div className="grid grid-cols-3 gap-3 p-4 rounded-xl bg-surface-raised border border-border text-center">
            <div>
              <span className="text-xs text-fg-muted block">Questions</span>
              <span className="text-lg font-bold text-fg">{questions.length}</span>
            </div>
            <div>
              <span className="text-xs text-fg-muted block">Passing Score</span>
              <span className="text-lg font-bold text-fg">{quizMeta.passing_score}%</span>
            </div>
            <div>
              <span className="text-xs text-fg-muted block">Time Limit</span>
              <span className="text-lg font-bold text-fg">{quizMeta.time_limit_mins}m</span>
            </div>
          </div>

          <div className="p-4 rounded-xl border border-primary/20 bg-primary/5 text-xs text-fg-muted leading-relaxed space-y-1">
            <p className="font-medium text-fg">Knowledge Engine Telemetry:</p>
            <p>
              Each answer becomes evidence about the competency it tests. Multiple-choice answers are graded exactly; written answers are graded
              against a rubric, and a person reviews any the system is not sure about. Mastery is then calculated from that evidence.
            </p>
          </div>
        </CardContent>

        <CardFooter className="flex justify-center pt-2">
          <Button variant="primary" size="lg" onClick={handleStartAttempt}>
            Begin Assessment <ArrowRight className="w-4 h-4 ml-2" />
          </Button>
        </CardFooter>
      </Card>
    );
  }

  // ---------------------------------------------------------------------------
  // View C: Active Quiz Runner Stepper
  // ---------------------------------------------------------------------------
  const currentQuestion = questions[activeQuestionIdx];
  const totalQuestions = questions.length;
  const runnerProgress = Math.round((answeredCount / totalQuestions) * 100);

  return (
    <div className="flex flex-col gap-6 max-w-3xl mx-auto">
      {/* Top Runner Header */}
      <div className="flex flex-wrap items-center justify-between gap-4 pb-4 border-b border-border">
        <div>
          <span className="text-xs font-semibold uppercase tracking-wider text-primary">
            Attempt #{currentAttempt.attempt_number} in Progress
          </span>
          <h2 className="text-lg font-bold text-fg">{quizMeta.title}</h2>
        </div>

        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-surface-raised border border-border text-xs font-mono font-medium text-fg">
            <Clock className="w-3.5 h-3.5 text-primary" />
            <span>{formatTimer(elapsedSeconds)}</span>
          </div>

          <Button
            variant="primary"
            size="sm"
            onClick={handleSubmit}
            disabled={submitting}
          >
            {submitting ? (
              <>
                <Spinner size="sm" className="mr-1.5" /> Grading...
              </>
            ) : (
              <>Submit Quiz</>
            )}
          </Button>
        </div>
      </div>

      {/* Progress & Question Stepper Dots */}
      <div className="flex flex-col gap-2">
        <div className="flex items-center justify-between text-xs text-fg-muted font-medium">
          <span>
            Question {activeQuestionIdx + 1} of {totalQuestions}
          </span>
          <span>{answeredCount} answered</span>
        </div>
        <Progress value={runnerProgress} tone="primary" className="h-1.5" />

        <div className="flex items-center gap-1.5 mt-2 overflow-x-auto py-1">
          {questions.map((q, idx) => {
            const answered = isAnswered(q);
            const isCurrent = idx === activeQuestionIdx;
            return (
              <button
                key={q.id}
                type="button"
                onClick={() => setActiveQuestionIdx(idx)}
                className={`w-8 h-8 rounded-lg text-xs font-mono font-semibold transition-all shrink-0 flex items-center justify-center border ${
                  isCurrent
                    ? "border-primary bg-primary text-primary-fg ring-2 ring-primary/40"
                    : answered
                    ? "border-primary/50 bg-primary/10 text-primary"
                    : "border-border bg-surface-raised text-fg-muted hover:border-fg-muted"
                }`}
              >
                {idx + 1}
              </button>
            );
          })}
        </div>
      </div>

      {/* Active Question Card */}
      <Card className="border-border shadow-lg">
        <CardHeader>
          <div className="flex items-center justify-between">
            <Badge variant="neutral">{isWritten(currentQuestion) ? "Written answer" : "Single Choice"}</Badge>
            <span className="text-xs text-fg-muted font-mono">
              Value: {currentQuestion.points} pts
            </span>
          </div>
          <CardTitle className="text-lg font-medium text-fg mt-3 leading-relaxed">
            {currentQuestion.question_text}
          </CardTitle>
        </CardHeader>

        <CardContent className="space-y-3 pt-2">
          {isWritten(currentQuestion) && (
            <>
              {currentQuestion.rubric && currentQuestion.rubric.length > 0 && (
                <div className="rounded-lg border border-border bg-surface-raised p-3 text-xs text-fg-muted">
                  <p className="font-medium text-fg mb-1">Your answer is judged on:</p>
                  <ul className="list-disc pl-4 space-y-0.5">
                    {currentQuestion.rubric.map((c) => (
                      <li key={c.criterion}>
                        <span className="text-fg">{c.criterion}</span>
                        {c.description ? ` — ${c.description}` : ""}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              <Textarea
                aria-label="Your answer"
                rows={7}
                maxLength={6000}
                placeholder="Write your answer in your own words."
                value={writtenAnswers[currentQuestion.id] ?? ""}
                onChange={(e) => handleWrite(currentQuestion.id, e.target.value)}
              />
              <p className="text-xs text-fg-muted text-right">{(writtenAnswers[currentQuestion.id] ?? "").length} / 6000</p>
            </>
          )}
          {!isWritten(currentQuestion) && currentQuestion.options.map((opt) => {
            const isSelected = selectedAnswers[currentQuestion.id] === opt.id;
            return (
              <label
                key={opt.id}
                onClick={() => handleSelectOption(currentQuestion.id, opt.id)}
                className={`w-full flex items-start gap-3 p-4 rounded-xl border cursor-pointer transition-all ${
                  isSelected
                    ? "border-primary bg-primary/10 text-fg ring-1 ring-primary/40"
                    : "border-border bg-surface-raised text-fg-muted hover:border-fg-muted hover:bg-surface-overlay/50"
                }`}
              >
                <input
                  type="radio"
                  name={currentQuestion.id}
                  checked={isSelected}
                  onChange={() => handleSelectOption(currentQuestion.id, opt.id)}
                  className="mt-1 accent-primary h-4 w-4 shrink-0"
                />
                <span className="text-sm font-normal text-fg leading-snug">
                  {opt.option_text}
                </span>
              </label>
            );
          })}
        </CardContent>

        <CardFooter className="flex items-center justify-between border-t border-border pt-4">
          <Button
            variant="secondary"
            size="sm"
            disabled={activeQuestionIdx === 0}
            onClick={() => setActiveQuestionIdx((prev) => Math.max(0, prev - 1))}
          >
            <ArrowLeft className="w-4 h-4 mr-1.5" /> Previous
          </Button>

          {activeQuestionIdx < totalQuestions - 1 ? (
            <Button
              variant="secondary"
              size="sm"
              onClick={() =>
                setActiveQuestionIdx((prev) => Math.min(totalQuestions - 1, prev + 1))
              }
            >
              Next <ArrowRight className="w-4 h-4 ml-1.5" />
            </Button>
          ) : (
            <Button
              variant="primary"
              size="sm"
              onClick={handleSubmit}
              disabled={submitting}
            >
              Finish & Submit
            </Button>
          )}
        </CardFooter>
      </Card>

      <ConfirmDialog
        open={confirmSubmit}
        onClose={() => setConfirmSubmit(false)}
        onConfirm={() => void submitAttempt()}
        title="Submit with unanswered questions?"
        description={`You have answered ${answeredCount} of ${totalQuestions} questions. Unanswered questions are marked incorrect.`}
        confirmLabel="Submit anyway"
        cancelLabel="Keep working"
      />
    </div>
  );
}
