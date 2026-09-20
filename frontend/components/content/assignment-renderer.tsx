"use client";

import React, { useEffect, useRef, useState } from "react";
import { CheckCircle2, Send } from "lucide-react";

import { Badge, Button, Card, CardContent, Field, Input, Textarea } from "@/components/ui";
import { ApiError, apiClient } from "@/lib/api-client";
import { formatDateTime } from "@/lib/utils";
import { useLearningEvents } from "@/hooks/use-learning-events";
import { useToast } from "@/hooks/use-toast";
import type { AssignmentInfo, PlayerItem } from "@/types/learning";
import { Markdown } from "./markdown";

/** Rubric entries look like {criterion: {weight: 0.4, max: 40}}; render what is actually there. */
function rubricRows(rubric: Record<string, unknown>): { name: string; detail: string | null }[] {
  return Object.entries(rubric).map(([key, value]) => {
    const record = value && typeof value === "object" ? (value as { weight?: number; max?: number }) : {};
    const detail =
      typeof record.weight === "number" ? `${Math.round(record.weight * 100)}% of the grade` : null;
    return { name: key.replace(/_/g, " "), detail };
  });
}

export function AssignmentRenderer({
  item,
  assignment,
  onSubmitted,
}: {
  item: PlayerItem;
  assignment: AssignmentInfo;
  /** Called after a successful submission so the page can refresh its progress. */
  onSubmitted: () => void;
}) {
  const { toastSuccess, toastError } = useToast();
  const events = useLearningEvents();
  const announced = useRef(false);
  useEffect(() => {
    if (announced.current) return;
    announced.current = true;
    events.report("assignment_opened", { contentId: item.id }, { assignment_id: assignment.id });
  }, [events, item.id, assignment.id]);
  const [text, setText] = useState(assignment.submission_text ?? "");
  const [url, setUrl] = useState(assignment.submission_url ?? "");
  const [editing, setEditing] = useState(assignment.submission_status === null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submitted = assignment.submission_status !== null;
  const graded = assignment.submission_status === "GRADED";

  const submit = async () => {
    if (!text.trim() && !url.trim()) {
      setError("Add your work as text, a link, or both.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await apiClient.post(`/api/v1/assignments/${assignment.id}/submit`, {
        submission_text: text.trim() || null,
        submission_url: url.trim() || null,
      });
      toastSuccess("Submitted", "Your work has been handed in.");
      setEditing(false);
      onSubmitted();
    } catch (err) {
      if (err instanceof ApiError && err.status >= 400 && err.status < 500) setError(err.message);
      else toastError(err, "Could not submit");
    } finally {
      setSubmitting(false);
    }
  };

  const rows = rubricRows(assignment.rubric);

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <header className="border-b border-border pb-5">
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <Badge variant="info">Assignment</Badge>
          <Badge className="capitalize">{assignment.difficulty}</Badge>
          {submitted && (
            <Badge variant={graded ? "success" : "primary"}>
              <CheckCircle2 className="mr-1 size-3" aria-hidden="true" />
              {graded ? "Graded" : "Submitted"}
            </Badge>
          )}
        </div>
        <h2 className="text-2xl font-semibold tracking-tight text-fg">{item.title}</h2>
      </header>

      <section aria-labelledby="instructions-heading">
        <h3 id="instructions-heading" className="mb-2 text-sm font-semibold text-fg">
          Instructions
        </h3>
        <Markdown source={assignment.instructions} />
      </section>

      {rows.length > 0 && (
        <section aria-labelledby="rubric-heading">
          <h3 id="rubric-heading" className="mb-2 text-sm font-semibold text-fg">
            How it is assessed
          </h3>
          <ul className="space-y-1.5 text-sm">
            {rows.map((row) => (
              <li key={row.name} className="flex justify-between gap-4 rounded-md bg-surface px-3 py-2">
                <span className="capitalize text-fg">{row.name}</span>
                {row.detail && <span className="text-fg-muted">{row.detail}</span>}
              </li>
            ))}
          </ul>
        </section>
      )}

      {submitted && !editing && (
        <Card>
          <CardContent className="space-y-3 pt-5">
            <p className="text-xs text-fg-muted">
              {assignment.submitted_at ? `Submitted ${formatDateTime(assignment.submitted_at)}` : "Submitted"}
            </p>
            {assignment.submission_text && (
              <pre className="whitespace-pre-wrap rounded-lg bg-surface p-3 font-mono text-[13px] text-fg">
                {assignment.submission_text}
              </pre>
            )}
            {assignment.submission_url && (
              <a href={assignment.submission_url} target="_blank" rel="noopener noreferrer" className="text-sm text-primary underline">
                {assignment.submission_url}
              </a>
            )}
            {graded ? (
              <div className="rounded-lg border border-success-border bg-success-light p-3 text-sm">
                <p className="font-medium text-fg">
                  Score: {assignment.score ?? "—"} / {assignment.max_score}
                </p>
                {assignment.feedback && <p className="mt-1 text-fg-muted">{assignment.feedback}</p>}
              </div>
            ) : (
              <p className="text-sm text-fg-muted">Waiting to be graded. You can hand in a revised version.</p>
            )}
            <Button variant="secondary" size="sm" onClick={() => setEditing(true)}>
              Submit a revision
            </Button>
          </CardContent>
        </Card>
      )}

      {editing && (
        <section aria-labelledby="submit-heading" className="space-y-4">
          <h3 id="submit-heading" className="text-sm font-semibold text-fg">
            Your work
          </h3>
          <Field label="Answer or code" htmlFor="assignment-text">
            {(props) => (
              <Textarea
                {...props}
                rows={10}
                className="font-mono text-[13px]"
                value={text}
                onChange={(e) => setText(e.target.value)}
              />
            )}
          </Field>
          <Field label="Link (optional)" htmlFor="assignment-url" hint="A repository, gist or document.">
            {(props) => (
              <Input {...props} type="url" placeholder="https://…" value={url} onChange={(e) => setUrl(e.target.value)} />
            )}
          </Field>
          {error && (
            <p role="alert" className="rounded-md bg-danger-light px-3 py-2 text-sm text-danger">
              {error}
            </p>
          )}
          <div className="flex gap-2">
            <Button onClick={submit} disabled={submitting}>
              <Send aria-hidden="true" /> {submitting ? "Submitting…" : "Submit work"}
            </Button>
            {submitted && (
              <Button variant="secondary" onClick={() => setEditing(false)} disabled={submitting}>
                Cancel
              </Button>
            )}
          </div>
        </section>
      )}
    </div>
  );
}
