"use client";

import * as React from "react";
import { Check, Pencil, Plus, Quote, Trash2, Undo2, X } from "lucide-react";

import {
  Alert,
  Badge,
  Button,
  ConfirmDialog,
  Dialog,
  EmptyState,
  Field,
  Input,
  Select,
  Textarea,
} from "@/components/ui";
import { useToast } from "@/hooks/use-toast";
import { cn, pluralize } from "@/lib/utils";
import { contentAdminService } from "@/services";
import type { ContentDetail, QuestionCandidate, QuestionInput, QuestionKind, RubricCriterion } from "@/types/content-admin";

const STATUS_BADGE: Record<
  QuestionCandidate["status"],
  { label: string; variant: "neutral" | "success" | "danger" | "info" | "warning" }
> = {
  pending: { label: "Needs review", variant: "warning" },
  approved: { label: "Approved", variant: "success" },
  rejected: { label: "Rejected", variant: "danger" },
  published: { label: "Published", variant: "info" },
};

function difficultyLabel(value: number): string {
  if (value < 0.34) return "Easy";
  if (value < 0.67) return "Medium";
  return "Hard";
}

/* -------------------------------------------------------------------------- */
/* Editor                                                                     */
/* -------------------------------------------------------------------------- */

interface Draft {
  question_text: string;
  question_type: QuestionKind;
  options: { text: string; is_correct: boolean }[];
  explanation: string;
  difficulty: number;
  competency_name: string;
  expected_answer: string;
  rubric: { criterion: string; description: string }[];
}

const isWritten = (kind: QuestionKind) => kind === "short_answer" || kind === "open_ended";

function emptyDraft(): Draft {
  return {
    question_text: "",
    question_type: "multiple_choice",
    expected_answer: "",
    rubric: [{ criterion: "", description: "" }],
    options: [
      { text: "", is_correct: true },
      { text: "", is_correct: false },
      { text: "", is_correct: false },
    ],
    explanation: "",
    difficulty: 0.5,
    competency_name: "",
  };
}

function draftOf(q: QuestionCandidate): Draft {
  return {
    question_text: q.question_text,
    question_type: q.question_type ?? "multiple_choice",
    expected_answer: q.expected_answer ?? "",
    rubric: (q.rubric ?? []).map((c) => ({ criterion: c.criterion, description: c.description ?? "" })),
    options: q.options.map((o) => ({ text: o.text, is_correct: o.is_correct })),
    explanation: q.explanation ?? "",
    difficulty: q.difficulty,
    competency_name: q.competency_name ?? "",
  };
}

/** Problems a reviewer can fix, mirroring the server's rules so they are told before saving. */
function problems(d: Draft): string[] {
  const found: string[] = [];
  if (d.question_text.trim().length < 10) found.push("Write the question (at least 10 characters).");
  if (isWritten(d.question_type)) {
    if (!d.expected_answer.trim() && !d.rubric.some((c) => c.criterion.trim().length >= 2)) found.push("Say what a good answer contains: an expected answer or at least one rubric criterion.");
    if (!d.competency_name) found.push("Choose the competency this answer is evidence for.");
    return found;
  }
  const filled = d.options.filter((o) => o.text.trim());
  if (filled.length < 3) found.push("Give at least 3 answer options.");
  if (d.options.some((o) => !o.text.trim())) found.push("Remove or fill in empty options.");
  if (d.options.filter((o) => o.is_correct).length !== 1) found.push("Mark exactly one option as correct.");
  const texts = filled.map((o) => o.text.trim().toLowerCase());
  if (new Set(texts).size !== texts.length) found.push("Options must differ from each other.");
  return found;
}

function QuestionEditor({
  open,
  initial,
  competencyNames,
  title,
  typeLocked = false,
  onClose,
  onSave,
}: {
  open: boolean;
  initial: Draft;
  /** The type of an existing question cannot change. */
  typeLocked?: boolean;
  competencyNames: string[];
  title: string;
  onClose: () => void;
  onSave: (draft: Draft) => Promise<void>;
}) {
  const [draft, setDraft] = React.useState<Draft>(initial);
  const [saving, setSaving] = React.useState(false);

  const issues = problems(draft);

  const setOption = (i: number, text: string) =>
    setDraft((d) => ({ ...d, options: d.options.map((o, j) => (j === i ? { ...o, text } : o)) }));

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={title}
      size="lg"
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={saving}>
            Cancel
          </Button>
          <Button
            disabled={issues.length > 0}
            loading={saving}
            onClick={async () => {
              setSaving(true);
              try {
                await onSave({
                  ...draft,
                  question_text: draft.question_text.trim(),
                  options: draft.options.map((o) => ({ ...o, text: o.text.trim() })),
                });
              } finally {
                setSaving(false);
              }
            }}
          >
            Save question
          </Button>
        </>
      }
    >
      <div className="grid gap-4">
        <Field label="Question" htmlFor="q-text" required>
          {(props) => (
            <Textarea
              {...props}
              rows={2}
              maxLength={500}
              value={draft.question_text}
              onChange={(e) => setDraft({ ...draft, question_text: e.target.value })}
            />
          )}
        </Field>

        {!typeLocked && (
          <Field label="Kind of question" htmlFor="q-kind">
            {(props) => (
              <Select
                {...props}
                value={draft.question_type}
                onChange={(e) => setDraft({ ...draft, question_type: e.target.value as QuestionKind })}
                options={[
                  { value: "multiple_choice", label: "Multiple choice (graded exactly)" },
                  { value: "short_answer", label: "Short written answer (graded against a rubric)" },
                  { value: "open_ended", label: "Open-ended written answer (graded against a rubric)" },
                ]}
              />
            )}
          </Field>
        )}

        {isWritten(draft.question_type) && (
          <>
            <Field label="Expected answer" htmlFor="q-expected" hint="What a good answer says. Used by the grader and by reviewers; learners never see it.">
              {(props) => (
                <Textarea {...props} rows={3} maxLength={3000} value={draft.expected_answer} onChange={(e) => setDraft({ ...draft, expected_answer: e.target.value })} />
              )}
            </Field>
            <fieldset className="grid gap-2">
              <legend className="mb-1 text-sm font-medium text-fg">Rubric: what the answer is judged on (learners see this)</legend>
              {draft.rubric.map((c, i) => (
                <div key={i} className="grid gap-2 sm:grid-cols-[1fr_1.5fr_auto]">
                  <Input
                    aria-label={`Criterion ${i + 1}`}
                    placeholder="Criterion"
                    value={c.criterion}
                    maxLength={120}
                    onChange={(e) => setDraft((d) => ({ ...d, rubric: d.rubric.map((r, j) => (j === i ? { ...r, criterion: e.target.value } : r)) }))}
                  />
                  <Input
                    aria-label={`Criterion ${i + 1} description`}
                    placeholder="What a good answer shows"
                    value={c.description}
                    maxLength={300}
                    onChange={(e) => setDraft((d) => ({ ...d, rubric: d.rubric.map((r, j) => (j === i ? { ...r, description: e.target.value } : r)) }))}
                  />
                  {draft.rubric.length > 1 && (
                    <Button variant="ghost" size="icon" aria-label={`Remove criterion ${i + 1}`} onClick={() => setDraft((d) => ({ ...d, rubric: d.rubric.filter((_, j) => j !== i) }))}>
                      <Trash2 />
                    </Button>
                  )}
                </div>
              ))}
              {draft.rubric.length < 8 && (
                <div>
                  <Button variant="secondary" size="sm" onClick={() => setDraft((d) => ({ ...d, rubric: [...d.rubric, { criterion: "", description: "" }] }))}>
                    <Plus aria-hidden="true" /> Add criterion
                  </Button>
                </div>
              )}
            </fieldset>
          </>
        )}

        {!isWritten(draft.question_type) && (
        <fieldset className="grid gap-2">
          <legend className="mb-1 text-sm font-medium text-fg">Answer options (select the correct one)</legend>
          {draft.options.map((option, i) => (
            <div key={i} className="flex items-center gap-2">
              <input
                type="radio"
                name="correct-option"
                aria-label={`Option ${i + 1} is correct`}
                checked={option.is_correct}
                onChange={() =>
                  setDraft((d) => ({ ...d, options: d.options.map((o, j) => ({ ...o, is_correct: j === i })) }))
                }
                className="size-4 accent-[var(--color-primary)]"
              />
              <Input
                aria-label={`Option ${i + 1}`}
                value={option.text}
                maxLength={250}
                onChange={(e) => setOption(i, e.target.value)}
              />
              {draft.options.length > 3 && (
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label={`Remove option ${i + 1}`}
                  onClick={() =>
                    setDraft((d) => {
                      const options = d.options.filter((_, j) => j !== i);
                      if (!options.some((o) => o.is_correct)) options[0] = { ...options[0], is_correct: true };
                      return { ...d, options };
                    })
                  }
                >
                  <Trash2 />
                </Button>
              )}
            </div>
          ))}
          {draft.options.length < 5 && (
            <div>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setDraft((d) => ({ ...d, options: [...d.options, { text: "", is_correct: false }] }))}
              >
                <Plus aria-hidden="true" /> Add option
              </Button>
            </div>
          )}
        </fieldset>
        )}

        <Field label="Explanation" htmlFor="q-explanation" hint="Shown to the learner after they answer.">
          {(props) => (
            <Textarea
              {...props}
              rows={2}
              maxLength={1000}
              value={draft.explanation}
              onChange={(e) => setDraft({ ...draft, explanation: e.target.value })}
            />
          )}
        </Field>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label={`Difficulty: ${difficultyLabel(draft.difficulty)}`} htmlFor="q-difficulty">
            {({ id, "aria-describedby": describedBy }) => (
              <input
                id={id}
                aria-describedby={describedBy}
                type="range"
                min={0}
                max={1}
                step={0.05}
                value={draft.difficulty}
                onChange={(e) => setDraft({ ...draft, difficulty: Number(e.target.value) })}
                className="w-full accent-[var(--color-primary)]"
              />
            )}
          </Field>
          {competencyNames.length > 0 && (
            <Field label="Competency it provides evidence for" htmlFor="q-competency">
              {(props) => (
                <Select
                  {...props}
                  value={draft.competency_name}
                  onChange={(e) => setDraft({ ...draft, competency_name: e.target.value })}
                  options={[
                    { value: "", label: "None" },
                    ...(draft.competency_name && !competencyNames.includes(draft.competency_name)
                      ? [{ value: draft.competency_name, label: draft.competency_name }]
                      : []),
                    ...competencyNames.map((n) => ({ value: n, label: n })),
                  ]}
                />
              )}
            </Field>
          )}
        </div>

        {issues.length > 0 && (
          <ul className="list-disc pl-5 text-sm text-danger" aria-live="polite">
            {issues.map((issue) => (
              <li key={issue}>{issue}</li>
            ))}
          </ul>
        )}
      </div>
    </Dialog>
  );
}

/* -------------------------------------------------------------------------- */
/* Panel                                                                      */
/* -------------------------------------------------------------------------- */

export function QuestionsPanel({
  detail,
  onChanged,
  refresh,
}: {
  detail: ContentDetail;
  /** Replace one candidate locally after a change. */
  onChanged: (candidate: QuestionCandidate) => void;
  /** Reload everything (after add/delete/bulk). */
  refresh: () => void;
}) {
  const { toastSuccess, toastError } = useToast();
  const [editing, setEditing] = React.useState<QuestionCandidate | null>(null);
  const [adding, setAdding] = React.useState(false);
  const [deleting, setDeleting] = React.useState<QuestionCandidate | null>(null);
  const [busy, setBusy] = React.useState<string | null>(null);

  const candidates = detail.candidates;
  const pending = candidates.filter((c) => c.status === "pending");
  const competencyNames = (detail.analysis?.competencies ?? [])
    .filter((c) => c.action !== "skip")
    .map((c) => c.name);
  const rejections = detail.analysis?.question_rejections ?? [];

  const setStatus = async (q: QuestionCandidate, status: "pending" | "approved" | "rejected") => {
    setBusy(q.id);
    try {
      onChanged(await contentAdminService.setQuestionStatus(q.id, status));
    } catch (err) {
      toastError(err, "Could not update the question");
    } finally {
      setBusy(null);
    }
  };

  const approveAll = async () => {
    setBusy("bulk");
    try {
      await contentAdminService.setQuestionsStatus(detail.id, pending.map((c) => c.id), "approved");
      toastSuccess(`${pluralize(pending.length, "question")} approved`);
      refresh();
    } catch (err) {
      toastError(err, "Could not approve the questions");
    } finally {
      setBusy(null);
    }
  };

  const toInput = (d: Draft, creating: boolean): QuestionInput => {
    const written = isWritten(d.question_type);
    const rubric: RubricCriterion[] = d.rubric
      .filter((c) => c.criterion.trim().length >= 2)
      .map((c) => ({ criterion: c.criterion.trim(), weight: 1, description: c.description.trim() || null }));
    const base = {
      question_text: d.question_text,
      ...(creating ? { question_type: d.question_type } : {}),
      explanation: d.explanation.trim() || null,
      difficulty: d.difficulty,
      competency_name: d.competency_name || null,
    };
    return written
      ? { ...base, expected_answer: d.expected_answer.trim() || null, rubric: rubric.length ? rubric : null }
      : { ...base, options: d.options };
  };

  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-fg-muted">
          {candidates.length === 0
            ? "No questions yet."
            : `${pluralize(candidates.filter((c) => c.status === "approved" || c.status === "published").length, "question")} approved, ${pending.length} waiting for your review.`}
        </p>
        <div className="flex flex-wrap gap-2">
          {pending.length > 1 && (
            <Button variant="secondary" size="sm" onClick={approveAll} loading={busy === "bulk"}>
              <Check aria-hidden="true" /> Approve all {pending.length} pending
            </Button>
          )}
          <Button variant="secondary" size="sm" onClick={() => setAdding(true)}>
            <Plus aria-hidden="true" /> Write a question
          </Button>
        </div>
      </div>

      {candidates.some((c) => c.origin === "generated") && (
        <Alert variant="info">
          Every drafted question quotes the passage it was taken from, and was checked against the material. Read each
          one anyway: approved questions become graded evidence about your learners.
        </Alert>
      )}

      {candidates.length === 0 ? (
        <EmptyState
          size="sm"
          title="No questions to review"
          description={
            detail.job?.status === "needs_attention" || detail.job?.status === "failed"
              ? "Question drafting did not complete. See the processing steps, fix the cause and retry — or write questions yourself."
              : "The material did not yield questions that passed verification. You can write your own."
          }
        />
      ) : (
        <ul className="grid gap-3">
          {candidates.map((q) => {
            const badge = STATUS_BADGE[q.status];
            const locked = q.status === "published";
            return (
              <li
                key={q.id}
                data-question-status={q.status}
                className={cn(
                  "rounded-lg border bg-surface-elevated p-4",
                  q.status === "rejected" ? "border-border opacity-70" : "border-border"
                )}
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <p className="min-w-0 flex-1 text-sm font-medium text-fg">{q.question_text}</p>
                  <div className="flex flex-wrap gap-1.5">
                    <Badge variant={badge.variant} size="sm">{badge.label}</Badge>
                    <Badge variant="neutral" size="sm">
                      {q.origin === "manual" ? "Written by you" : q.edited ? "AI draft, edited" : "AI draft"}
                    </Badge>
                    <Badge variant="neutral" size="sm">{difficultyLabel(q.difficulty)}</Badge>
                  </div>
                </div>

                {(q.question_type === "short_answer" || q.question_type === "open_ended") && (
                  <div className="mt-3 grid gap-2 text-sm">
                    <Badge variant="info" size="sm" className="w-fit">
                      {q.question_type === "short_answer" ? "Short written answer" : "Open-ended written answer"}: graded by AI against the rubric, with human review when unsure
                    </Badge>
                    {q.expected_answer && (
                      <p className="rounded-md bg-success-light px-2.5 py-1.5 text-success">
                        <span className="font-medium">Expected answer: </span>
                        {q.expected_answer}
                      </p>
                    )}
                    {(q.rubric ?? []).length > 0 && (
                      <ul className="list-disc pl-5 text-fg-muted">
                        {(q.rubric ?? []).map((c) => (
                          <li key={c.criterion}>
                            <span className="text-fg">{c.criterion}</span>
                            {c.description ? ` — ${c.description}` : ""}
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                )}

                <ol className="mt-3 grid gap-1.5 text-sm">
                  {q.options.map((o, i) => (
                    <li
                      key={o.id}
                      className={cn(
                        "flex items-start gap-2 rounded-md px-2.5 py-1.5",
                        o.is_correct ? "bg-success-light text-success" : "text-fg-muted"
                      )}
                    >
                      <span className="font-medium" aria-hidden="true">{String.fromCharCode(65 + i)}.</span>
                      <span>
                        {o.text}
                        {o.is_correct && <span className="sr-only"> (correct answer)</span>}
                      </span>
                      {o.is_correct && <Check className="ml-auto mt-0.5 size-4 shrink-0" aria-hidden="true" />}
                    </li>
                  ))}
                </ol>

                {q.explanation && <p className="mt-3 text-xs text-fg-muted">{q.explanation}</p>}
                {q.competency_name && (
                  <p className="mt-2 text-xs text-fg-muted">Evidence for: {q.competency_name}</p>
                )}
                {q.source_quote && (
                  <blockquote className="mt-3 flex gap-2 border-l-2 border-border-strong pl-3 text-xs italic text-fg-muted">
                    <Quote className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
                    <span>{q.source_quote}</span>
                  </blockquote>
                )}

                {!locked && (
                  <div className="mt-4 flex flex-wrap gap-2">
                    {q.status !== "approved" && (
                      <Button size="sm" onClick={() => setStatus(q, "approved")} loading={busy === q.id}>
                        <Check aria-hidden="true" /> Approve
                      </Button>
                    )}
                    {q.status !== "rejected" && (
                      <Button size="sm" variant="secondary" onClick={() => setStatus(q, "rejected")} disabled={busy === q.id}>
                        <X aria-hidden="true" /> Reject
                      </Button>
                    )}
                    {q.status !== "pending" && (
                      <Button size="sm" variant="ghost" onClick={() => setStatus(q, "pending")} disabled={busy === q.id}>
                        <Undo2 aria-hidden="true" /> Back to review
                      </Button>
                    )}
                    <Button size="sm" variant="ghost" onClick={() => setEditing(q)}>
                      <Pencil aria-hidden="true" /> Edit
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => setDeleting(q)} aria-label="Delete question">
                      <Trash2 aria-hidden="true" />
                    </Button>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}

      {rejections.length > 0 && (
        <details className="rounded-lg border border-border p-4 text-sm">
          <summary className="cursor-pointer font-medium text-fg">
            {pluralize(rejections.length, "drafted question")} discarded by verification
          </summary>
          <p className="mt-2 text-xs text-fg-muted">
            These did not pass the checks (for example, the quoted passage is not in the material) and were never shown
            as candidates.
          </p>
          <ul className="mt-2 grid gap-2">
            {rejections.map((r, i) => (
              <li key={i} className="text-xs text-fg-muted">
                <span className="text-fg">{r.question}</span> — {r.reason}
              </li>
            ))}
          </ul>
        </details>
      )}

      {adding && (
      <QuestionEditor
        open
        title="Write a question"
        initial={emptyDraft()}
        competencyNames={competencyNames}
        onClose={() => setAdding(false)}
        onSave={async (d) => {
          try {
            await contentAdminService.addQuestion(detail.id, toInput(d, true));
            toastSuccess("Question added and approved");
            setAdding(false);
            refresh();
          } catch (err) {
            toastError(err, "Could not add the question");
          }
        }}
      />
      )}

      {editing && (
      <QuestionEditor
        key={editing.id}
        open
        title="Edit question"
        typeLocked
        initial={draftOf(editing)}
        competencyNames={competencyNames}
        onClose={() => setEditing(null)}
        onSave={async (d) => {
          if (!editing) return;
          try {
            onChanged(await contentAdminService.editQuestion(editing.id, toInput(d, false)));
            toastSuccess("Question updated");
            setEditing(null);
          } catch (err) {
            toastError(err, "Could not save the question");
          }
        }}
      />
      )}

      <ConfirmDialog
        open={deleting !== null}
        onClose={() => setDeleting(null)}
        title="Delete this question?"
        description="It will be removed from the review list. This cannot be undone."
        confirmLabel="Delete"
        destructive
        onConfirm={async () => {
          if (!deleting) return;
          try {
            await contentAdminService.deleteQuestion(deleting.id);
            setDeleting(null);
            refresh();
          } catch (err) {
            toastError(err, "Could not delete the question");
          }
        }}
      />
    </div>
  );
}
