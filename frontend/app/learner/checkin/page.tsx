"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ClipboardCheck, RefreshCw, Sparkles } from "lucide-react";

import { AppShell, PageHeader } from "@/components/shell";
import { Alert, Badge, Button, Card, CardContent, CardHeader, CardTitle, EmptyState, ErrorState, Progress, Skeleton, SpinnerBlock } from "@/components/ui";
import { useApi } from "@/hooks/use-api";
import type { Role } from "@/lib/auth";
import { formatDateTime } from "@/lib/utils";
import {
  CHECKIN_CURRENT_KEY,
  CHECKIN_PENDING_KEY,
  checkinsService,
  type Checkin,
  type CheckinReport,
  type CheckinSummary,
} from "@/services/checkins";

const ROLES: Role[] = ["learner", "manager", "instructor", "org_admin", "system_admin"];
const BAND_TONE = { low: "warning", moderate: "info", high: "success" } as const;
const ANXIETY_TONE = { low: "success", moderate: "info", high: "warning" } as const;

function remember(id: string | null) {
  try {
    if (id) sessionStorage.setItem(CHECKIN_CURRENT_KEY, id);
    else sessionStorage.removeItem(CHECKIN_CURRENT_KEY);
  } catch {
    /* session storage can be unavailable; the page still works without remembering */
  }
}

export default function CheckinPage() {
  const router = useRouter();
  const [checkin, setCheckin] = useState<Checkin | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [starting, setStarting] = useState(false);
  const booted = useRef(false);

  const begin = useCallback(async () => {
    setStarting(true);
    setError(null);
    try {
      const c = await checkinsService.start(true);
      remember(c.id);
      setCheckin(c);
    } catch (e) {
      setError(e as Error);
    } finally {
      setStarting(false);
    }
  }, []);

  // A login sets a flag: this visit writes a new check-in, once. A reload resumes the one in progress.
  useEffect(() => {
    if (booted.current) return;
    booted.current = true;
    let pending = false;
    let current: string | null = null;
    try {
      pending = sessionStorage.getItem(CHECKIN_PENDING_KEY) === "1";
      sessionStorage.removeItem(CHECKIN_PENDING_KEY);
      current = sessionStorage.getItem(CHECKIN_CURRENT_KEY);
    } catch {
      /* ignore */
    }
    if (pending) {
      void begin();
    } else if (current) {
      checkinsService
        .get(current)
        .then(setCheckin)
        .catch(() => remember(null));
    }
  }, [begin]);

  // While a model is writing the check-in, ask again every few seconds.
  useEffect(() => {
    if (checkin?.status !== "generating") return;
    const id = checkin.id;
    const timer = setInterval(() => {
      checkinsService.get(id).then(setCheckin).catch(() => undefined);
    }, 2500);
    return () => clearInterval(timer);
  }, [checkin?.status, checkin?.id]);

  const leave = () => {
    remember(null);
    router.push("/learner/dashboard");
  };

  const skip = async () => {
    if (checkin) await checkinsService.skip(checkin.id).catch(() => undefined);
    leave();
  };

  return (
    <AppShell roles={ROLES}>
      <PageHeader
        title="Daily check-in"
        description="A short quiz written by AI from your own course material, and a few statements about how learning is going. Each check-in is different. Your score and report appear when you finish."
      />
      {error && <ErrorState error={error} onRetry={begin} />}
      {!error && !checkin && <Landing onStart={begin} starting={starting} onOpen={(id) => checkinsService.get(id).then((c) => { remember(c.id); setCheckin(c); })} />}
      {checkin?.status === "generating" && <Generating course={checkin.course?.title} onSkip={skip} />}
      {checkin?.status === "ready" && <Take checkin={checkin} onDone={(c) => setCheckin(c)} onSkip={skip} />}
      {checkin?.status === "completed" && checkin.report && <Report report={checkin.report} models={checkin.provenance} onNew={begin} onLeave={leave} starting={starting} />}
      {(checkin?.status === "failed" || checkin?.status === "skipped") && (
        <Card>
          <CardContent className="space-y-4 py-6">
            <Alert variant={checkin.status === "failed" ? "warning" : "info"} title={checkin.status === "failed" ? "The check-in could not be written" : "Skipped"}>
              {checkin.error?.message ?? "This check-in was skipped."}
            </Alert>
            <div className="flex flex-wrap gap-2">
              {checkin.error?.code !== "no_course" && (
                <Button onClick={begin} loading={starting}>
                  <RefreshCw className="size-4" aria-hidden /> Try again
                </Button>
              )}
              <Button variant="secondary" onClick={leave}>
                Continue to my learning
              </Button>
            </div>
          </CardContent>
        </Card>
      )}
    </AppShell>
  );
}

/* --------------------------------------------------------------------- landing */
function Landing({ onStart, starting, onOpen }: { onStart: () => void; starting: boolean; onOpen: (id: string) => void }) {
  const history = useApi<CheckinSummary[]>((signal) => checkinsService.history(signal));
  return (
    <div className="space-y-6">
      <Card>
        <CardContent className="flex flex-wrap items-center justify-between gap-4 py-6">
          <div className="flex items-start gap-3">
            <ClipboardCheck className="mt-0.5 size-5 text-primary" aria-hidden />
            <div>
              <p className="font-medium text-fg">Start a check-in</p>
              <p className="text-sm text-fg-muted">About five questions and twelve statements, roughly five minutes. Nothing in your self-report is visible to your manager.</p>
            </div>
          </div>
          <Button onClick={onStart} loading={starting} data-testid="start-checkin">
            Start check-in
          </Button>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Your earlier check-ins</CardTitle>
        </CardHeader>
        <CardContent>
          {history.loading && <Skeleton className="h-16 w-full" />}
          {!history.loading && (history.data ?? []).length === 0 && <EmptyState title="No check-ins yet" description="Your first one will appear here." />}
          <ul className="divide-y divide-border">
            {(history.data ?? []).map((h) => (
              <li key={h.id} className="flex flex-wrap items-center justify-between gap-2 py-3 text-sm">
                <div>
                  <p className="font-medium text-fg">{h.course_title ?? "No course"}</p>
                  <p className="text-xs text-fg-muted">{formatDateTime(h.created_at)}</p>
                </div>
                <div className="flex items-center gap-3">
                  {h.status === "completed" ? (
                    <>
                      <span className="tabular-nums text-fg">
                        {h.quiz_correct} of {h.quiz_total} ({h.quiz_percent}%)
                      </span>
                      <Button size="sm" variant="ghost" onClick={() => onOpen(h.id)}>
                        Open report
                      </Button>
                    </>
                  ) : (
                    <Badge variant="neutral">{h.status}</Badge>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>
    </div>
  );
}

/* ------------------------------------------------------------------ generating */
function Generating({ course, onSkip }: { course?: string; onSkip: () => void }) {
  return (
    <Card>
      <CardContent className="space-y-4 py-10 text-center" data-testid="checkin-generating">
        <SpinnerBlock />
        <p className="font-medium text-fg">Writing your check-in{course ? ` from “${course}”` : ""}…</p>
        <p className="text-sm text-fg-muted">An AI model is reading your course material and writing questions. Each question is checked against the material before you see it. This usually takes under half a minute.</p>
        <Button variant="ghost" onClick={onSkip}>
          Skip for now
        </Button>
      </CardContent>
    </Card>
  );
}

/* ------------------------------------------------------------------------ take */
function Take({ checkin, onDone, onSkip }: { checkin: Checkin; onDone: (c: Checkin) => void; onSkip: () => void }) {
  const [step, setStep] = useState<0 | 1>(0);
  const [quiz, setQuiz] = useState<Record<string, string>>({});
  const [rating, setRating] = useState<Record<string, number>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const questions = checkin.quiz ?? [];
  const statements = checkin.self_report?.statements ?? [];
  const labels = checkin.self_report?.scale.labels ?? [];

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      onDone(await checkinsService.submit(checkin.id, quiz, rating));
    } catch (e) {
      setError(e as Error);
    } finally {
      setBusy(false);
    }
  };

  const answered = Object.keys(quiz).length;
  const rated = Object.keys(rating).length;

  return (
    <div className="space-y-4" data-testid="checkin-take">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-sm text-fg-muted">
          <Badge variant={step === 0 ? "primary" : "neutral"}>1 · Quiz</Badge>
          <Badge variant={step === 1 ? "primary" : "neutral"}>2 · About you</Badge>
          <span>{checkin.course?.title}</span>
        </div>
        <Button variant="ghost" size="sm" onClick={onSkip}>
          Skip for now
        </Button>
      </div>

      {step === 0 && (
        <>
          {questions.map((q, i) => (
            <Card key={q.id}>
              <CardContent className="space-y-3 py-5">
                <p className="font-medium text-fg">
                  {i + 1}. {q.text}
                </p>
                <div className="space-y-2" role="radiogroup" aria-label={q.text}>
                  {q.options.map((o) => (
                    <label
                      key={o.id}
                      className={`flex cursor-pointer items-start gap-3 rounded-lg border p-3 text-sm transition-colors ${quiz[q.id] === o.id ? "border-primary bg-primary-light" : "border-border hover:bg-surface"}`}
                    >
                      <input type="radio" name={q.id} checked={quiz[q.id] === o.id} onChange={() => setQuiz({ ...quiz, [q.id]: o.id })} className="mt-0.5" />
                      <span>{o.text}</span>
                    </label>
                  ))}
                </div>
              </CardContent>
            </Card>
          ))}
          <div className="flex items-center justify-between">
            <span className="text-sm text-fg-muted">
              {answered} of {questions.length} answered
            </span>
            <Button onClick={() => setStep(1)} data-testid="to-self-report">
              Next
            </Button>
          </div>
        </>
      )}

      {step === 1 && (
        <>
          <Alert variant="info" title="About you">
            {checkin.self_report?.disclaimer} There are no right or wrong answers, and you can leave any statement blank.
          </Alert>
          <Card>
            <CardContent className="divide-y divide-border py-2">
              {statements.map((s) => (
                <div key={s.id} className="space-y-2 py-4">
                  <p className="text-sm text-fg">{s.text}</p>
                  <div className="grid grid-cols-5 gap-1.5 text-center text-[11px] text-fg-muted" role="radiogroup" aria-label={s.text}>
                    {labels.map((label, i) => {
                      const value = i + 1;
                      return (
                        <label
                          key={value}
                          className={`cursor-pointer rounded-md border px-1 py-2 leading-tight transition-colors ${rating[s.id] === value ? "border-primary bg-primary-light text-primary" : "border-border hover:bg-surface"}`}
                        >
                          <input type="radio" name={s.id} className="sr-only" checked={rating[s.id] === value} onChange={() => setRating({ ...rating, [s.id]: value })} />
                          {label}
                        </label>
                      );
                    })}
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>
          {error && <ErrorState error={error} onRetry={submit} />}
          <div className="flex flex-wrap items-center justify-between gap-2">
            <Button variant="secondary" onClick={() => setStep(0)}>
              Back
            </Button>
            <div className="flex items-center gap-3">
              <span className="text-sm text-fg-muted">
                {rated} of {statements.length} answered
              </span>
              <Button onClick={submit} loading={busy} data-testid="submit-checkin">
                See my report
              </Button>
            </div>
          </div>
          {busy && <p className="text-right text-xs text-fg-muted">Scoring your answers and writing your report…</p>}
        </>
      )}
    </div>
  );
}

/* ---------------------------------------------------------------------- report */
function Report({ report, models, onNew, onLeave, starting }: { report: CheckinReport; models?: Checkin["provenance"]; onNew: () => void; onLeave: () => void; starting: boolean }) {
  const q = report.quiz;
  const tone = (q.percent ?? 0) >= report.thresholds.quiz_strong ? "success" : (q.percent ?? 0) < report.thresholds.quiz_weak ? "danger" : "warning";
  return (
    <div className="space-y-6" data-testid="checkin-report">
      <Card>
        <CardContent className="space-y-3 py-6">
          <p className="text-sm text-fg-muted">{report.course_title}</p>
          <p className="text-3xl font-semibold tabular-nums text-fg" data-testid="quiz-score">
            {q.correct} of {q.total} correct <span className="text-lg text-fg-muted">({q.percent}%)</span>
          </p>
          <Progress value={q.percent ?? 0} tone={tone} ariaLabel="Quiz score" />
          {q.unanswered > 0 && <p className="text-xs text-fg-muted">{q.unanswered} question{q.unanswered === 1 ? " was" : "s were"} left unanswered and counted as not correct.</p>}
          {q.by_content.length > 0 && (
            <ul className="space-y-1 pt-2 text-sm">
              {q.by_content.map((c) => (
                <li key={c.name} className="flex justify-between gap-4">
                  <span className="text-fg">{c.name}</span>
                  <span className="tabular-nums text-fg-muted">
                    {c.correct} of {c.total}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Sparkles className="size-4 text-primary" aria-hidden /> Coaching note
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          {report.coaching_note.status === "ok" ? (
            <>
              <p className="leading-relaxed text-fg" data-testid="coaching-note">{report.coaching_note.note}</p>
              <p className="text-xs text-fg-muted">Written by an AI model ({report.coaching_note.model}). Every number in it was checked against your scores.</p>
            </>
          ) : (
            <p className="text-fg-muted">
              {report.coaching_note.status === "invalid"
                ? "The AI's note did not pass the checks against your scores, so it was discarded. Your scores and observations below are unaffected."
                : "The AI note is not available right now. Your scores and observations below are unaffected."}
            </p>
          )}
        </CardContent>
      </Card>

      {report.observations.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>What stands out</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="list-disc space-y-2 pl-5 text-sm text-fg">
              {report.observations.map((o) => (
                <li key={o.text}>{o.text}</li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>How learning is going — your view only</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {Object.entries(report.self_report).map(([key, c]) => (
            <div key={key} className="space-y-1" data-testid={`construct-${key}`}>
              <div className="flex items-center justify-between gap-2 text-sm">
                <span className="font-medium text-fg">{c.label}</span>
                {c.scored && c.band ? (
                  <span className="flex items-center gap-2">
                    <span className="tabular-nums text-fg">{c.score} / 100</span>
                    <Badge variant={(c.higher_is === "worse" ? ANXIETY_TONE : BAND_TONE)[c.band]}>{c.band}</Badge>
                  </span>
                ) : (
                  <Badge variant="neutral">not enough answers</Badge>
                )}
              </div>
              {c.scored && <Progress value={c.score ?? 0} tone="primary" size="sm" ariaLabel={c.label} />}
              {c.meaning && <p className="text-xs text-fg-muted">{c.meaning}</p>}
              {c.scored && c.change != null && (
                <p className="text-xs text-fg-muted">
                  {c.change_is_meaningful ? `${c.change > 0 ? "Up" : "Down"} ${Math.abs(c.change)} points from your last check-in (${c.previous}).` : `About the same as your last check-in (${c.previous}).`}
                </p>
              )}
            </div>
          ))}
          <p className="border-t border-border pt-3 text-xs text-fg-muted">{report.self_report_disclaimer}</p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Your answers</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {q.review.map((r, i) => (
            <details key={r.question_id} className="rounded-lg border border-border p-3 text-sm" open={!r.correct}>
              <summary className="flex cursor-pointer items-center justify-between gap-2">
                <span className="font-medium text-fg">
                  {i + 1}. {r.question}
                </span>
                <Badge variant={r.correct ? "success" : "danger"}>{r.correct ? "Correct" : r.answered ? "Not correct" : "Unanswered"}</Badge>
              </summary>
              <div className="mt-3 space-y-2 text-fg">
                {r.answered && !r.correct && <p>Your answer: {r.your_answer}</p>}
                <p>Correct answer: <strong>{r.correct_answer}</strong></p>
                {r.explanation && <p className="text-fg-muted">{r.explanation}</p>}
                <blockquote className="border-l-2 border-primary-border pl-3 text-xs italic text-fg-muted">
                  “{r.source_quote}”{r.content_title ? ` — ${r.content_title}` : ""}
                </blockquote>
              </div>
            </details>
          ))}
        </CardContent>
      </Card>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-xs text-fg-muted">
          Written by {models?.quiz_model ?? "an AI model"}; questions verified against your course material.
        </p>
        <div className="flex gap-2">
          <Button variant="secondary" onClick={onNew} loading={starting}>
            Another check-in
          </Button>
          <Button onClick={onLeave} data-testid="continue">
            Continue to my learning
          </Button>
        </div>
      </div>
    </div>
  );
}
