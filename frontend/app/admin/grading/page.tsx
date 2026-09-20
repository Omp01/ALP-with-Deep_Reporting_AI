"use client";

import React, { useState } from "react";
import { CheckCircle2, ClipboardCheck } from "lucide-react";

import { AppShell, PageHeader } from "@/components/shell";
import { Alert, Badge, Button, Dialog, EmptyState, ErrorState, Field, Select, SkeletonTable, Textarea, useToast } from "@/components/ui";
import { useApi } from "@/hooks/use-api";
import { formatDateTime } from "@/lib/utils";
import { ERROR_TYPES, gradingService, type ReviewItem } from "@/services/mastery";

const ROLES = ["org_admin", "instructor"] as const;
const PASSING_SIGNAL = 0.7;

export default function GradingQueuePage() {
  const queue = useApi((signal) => gradingService.queue({}, signal));
  const [open, setOpen] = useState<ReviewItem | null>(null);
  const items = queue.data?.items ?? [];

  return (
    <AppShell roles={[...ROLES]}>
      <PageHeader
        title="Answers to review"
        description="Written answers the automatic grader could not grade with enough trust: it was unavailable, unsure, or its grade could not be checked against the answer. Nothing about these answers counts towards mastery until you grade them."
      />

      {queue.loading ? (
        <SkeletonTable rows={5} />
      ) : queue.error ? (
        <ErrorState error={queue.error} onRetry={queue.refetch} />
      ) : items.length === 0 ? (
        <EmptyState icon={ClipboardCheck} title="Nothing to review" description="Every written answer has been graded. Answers appear here when the automatic grader is not sure." />
      ) : (
        <ul className="space-y-3" aria-label="Answers waiting for review">
          {items.map((item) => (
            <li key={item.response_id} className="rounded-lg border border-border p-4" data-review-item={item.response_id}>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="font-medium text-fg">{item.question}</p>
                  <p className="mt-0.5 text-xs text-fg-muted">
                    {item.learner.name} · {item.quiz} · attempt {item.attempt_number}
                    {item.competency ? ` · ${item.competency.name}` : ""}
                    {item.submitted_at ? ` · ${formatDateTime(item.submitted_at)}` : ""}
                  </p>
                </div>
                <Button size="sm" onClick={() => setOpen(item)}>
                  Review
                </Button>
              </div>
              {item.ai_suggestion?.why_review && <p className="mt-2 text-xs text-warning">Held because {item.ai_suggestion.why_review}.</p>}
            </li>
          ))}
        </ul>
      )}

      <Dialog open={open !== null} onClose={() => setOpen(null)} title="Review answer" variant="drawer" size="lg">
        {open && (
          <ReviewForm
            key={open.response_id}
            item={open}
            onDone={() => {
              setOpen(null);
              queue.refetch();
            }}
          />
        )}
      </Dialog>
    </AppShell>
  );
}

function ReviewForm({ item, onDone }: { item: ReviewItem; onDone: () => void }) {
  const { toast } = useToast();
  const [signal, setSignal] = useState<number | null>(null);
  const [errorType, setErrorType] = useState<string>("knowledge_gap");
  const [feedback, setFeedback] = useState("");
  const [saving, setSaving] = useState(false);
  const suggestion = item.ai_suggestion;
  const wrong = signal !== null && signal < PASSING_SIGNAL;

  const choices: { value: number; label: string }[] = [
    { value: 0, label: "No evidence of the skill (0%)" },
    { value: 0.25, label: "Mostly wrong (25%)" },
    { value: 0.5, label: "Partly right (50%)" },
    { value: 0.75, label: "Mostly right (75%)" },
    { value: 1, label: "Complete and correct (100%)" },
  ];

  const save = async () => {
    if (signal === null) return;
    setSaving(true);
    try {
      const result = await gradingService.review(item.response_id, { signal, error_type: wrong ? errorType : null, feedback: feedback.trim() || null });
      toast({
        title: "Answer graded",
        description:
          result.attempt_grading_status === "graded"
            ? `The attempt is now final: ${result.attempt_score}%, ${result.attempt_passed ? "passed" : "not passed"}.`
            : "Other answers in this attempt are still waiting.",
        variant: "success",
      });
      onDone();
    } catch (err) {
      toast({ title: "Could not save the grade", description: err instanceof Error ? err.message : "Try again.", variant: "error" });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-5" data-testid="review-form">
      <div>
        <p className="text-xs text-fg-muted">
          {item.learner.name} · {item.quiz} · {item.points} pts
        </p>
        <p className="mt-1 font-medium text-fg">{item.question}</p>
      </div>

      <section aria-label="Learner answer">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-fg-muted">Learner&apos;s answer</h3>
        <p className="mt-1 whitespace-pre-wrap rounded-lg border border-border bg-surface-raised p-3 text-sm text-fg">{item.answer || "(blank)"}</p>
      </section>

      <section aria-label="What to look for">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-fg-muted">What to look for</h3>
        {item.expected_answer && <p className="mt-1 text-sm text-fg">{item.expected_answer}</p>}
        {item.rubric.length > 0 && (
          <ul className="mt-1 list-disc pl-5 text-sm text-fg-muted">
            {item.rubric.map((c) => (
              <li key={c.criterion}>
                <span className="text-fg">{c.criterion}</span>
                {c.description ? ` — ${c.description}` : ""}
              </li>
            ))}
          </ul>
        )}
      </section>

      {suggestion && (
        <Alert variant="info" title="The automatic grader">
          <p className="text-sm">
            {suggestion.status === "needs_review" && suggestion.signal === 0 && suggestion.confidence === 0
              ? "It gave no grade."
              : `It suggested ${Math.round((suggestion.signal ?? 0) * 100)}% with confidence ${Math.round((suggestion.confidence ?? 0) * 100)}%. This is only a suggestion.`}{" "}
            {suggestion.why_review ? `Held because ${suggestion.why_review}.` : ""}
          </p>
          {suggestion.feedback && <p className="mt-1 text-xs">Its feedback: {suggestion.feedback}</p>}
        </Alert>
      )}

      <Field label="Your grade" htmlFor="review-signal" required>
        {(props) => (
          <Select
            {...props}
            id="review-signal"
            value={signal === null ? "" : String(signal)}
            onChange={(e) => setSignal(e.target.value === "" ? null : Number(e.target.value))}
            options={[{ value: "", label: "Choose…" }, ...choices.map((c) => ({ value: String(c.value), label: c.label }))]}
          />
        )}
      </Field>

      {wrong && (
        <Field label="What kind of mistake?" htmlFor="review-error">
          {(props) => (
            <Select
              {...props}
              id="review-error"
              value={errorType}
              onChange={(e) => setErrorType(e.target.value)}
              options={ERROR_TYPES.map((t) => ({ value: t, label: t.replaceAll("_", " ") }))}
            />
          )}
        </Field>
      )}

      <Field label="Feedback for the learner" htmlFor="review-feedback" hint="Shown to the learner with their result.">
        {(props) => <Textarea {...props} id="review-feedback" rows={3} maxLength={1000} value={feedback} onChange={(e) => setFeedback(e.target.value)} />}
      </Field>

      <div className="flex justify-end gap-2">
        <Button onClick={save} disabled={signal === null || saving} data-testid="save-review">
          <CheckCircle2 className="mr-1.5 size-4" aria-hidden="true" />
          {saving ? "Saving…" : "Save grade"}
        </Button>
      </div>
      <Badge variant="neutral" size="sm">
        Your grade counts with full confidence in the competency record.
      </Badge>
    </div>
  );
}
