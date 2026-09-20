"use client";

import React, { useCallback, useEffect, useState } from "react";
import { Compass } from "lucide-react";

import { Badge, Button } from "@/components/ui";
import { apiClient } from "@/lib/api-client";

export interface AdaptiveDecision {
  decision_id: string | null;
  action: string;
  rule: string;
  reason: string;
  competency: { id: string; name: string };
  content: { content_id: string; title: string; content_type: string; kind: string; course_id: string | null } | null;
  note: string | null;
  why: { headline: string; evidence: string[]; mastery: number | null; confidence: number | null; evidence_ids: string[]; rule: string; considered: string[] };
}

const LABEL: Record<string, string> = {
  CONTINUE: "Continue", REMEDIATE: "Review first", EASIER: "A gentler step", HARDER: "A bigger challenge",
  CHANGE_MODALITY: "A different format", REVISIT: "Revisit", SKIP: "Skip ahead", ASSESS: "Check your understanding",
};

/**
 * The adaptive engine's recommendation for this learner and course, with "Why am I seeing this?".
 * Everything shown comes from the stored decision; `refreshKey` asks for a new one after the learner does something.
 */
export function NextStepCard({ courseId, refreshKey, onOpen }: { courseId: string; refreshKey: number; onOpen: (contentId: string) => void }) {
  const [decision, setDecision] = useState<AdaptiveDecision | null>(null);
  const [failed, setFailed] = useState(false);
  const [open, setOpen] = useState(false);

  const load = useCallback(async () => {
    try {
      setDecision(await apiClient.post<AdaptiveDecision>("/api/v1/adaptive/next", { course_id: courseId }));
      setFailed(false);
    } catch {
      setDecision(null);
      setFailed(true);
    }
  }, [courseId]);

  useEffect(() => {
    void load();
  }, [load, refreshKey]);

  if (failed || !decision) return null;
  return (
    <section className="mb-3 rounded-lg border border-border bg-surface p-3" aria-label="Recommended next step" data-testid="next-step" data-action={decision.action}>
      <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-fg-muted">
        <Compass className="size-3.5" aria-hidden="true" /> Recommended
        <Badge variant="info" size="sm">{LABEL[decision.action] ?? decision.action}</Badge>
      </div>
      {decision.content ? (
        <Button variant="secondary" size="sm" className="mt-2 w-full justify-start" onClick={() => onOpen(decision.content!.content_id)} data-testid="next-step-open">
          {decision.content.title}
        </Button>
      ) : (
        <p className="mt-2 text-xs text-fg-muted">{decision.note ?? "Nothing further is mapped to this competency."}</p>
      )}
      <button type="button" className="mt-2 text-xs text-primary underline" onClick={() => setOpen(!open)} aria-expanded={open} data-testid="why-toggle">
        Why am I seeing this?
      </button>
      {open && (
        <div className="mt-2 space-y-2 text-xs text-fg-muted" data-testid="why-panel">
          <p className="text-fg">{decision.why.headline}</p>
          {decision.why.evidence.length > 0 && (
            <ul className="list-disc pl-4">
              {decision.why.evidence.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          )}
          {decision.why.mastery !== null && (
            <p>
              Your estimated mastery of {decision.competency.name}: <strong className="text-fg">{Math.round(decision.why.mastery * 100)}%</strong>
              {decision.why.confidence !== null ? ` (confidence ${Math.round(decision.why.confidence * 100)}%)` : ""}
            </p>
          )}
          {decision.why.considered.length > 0 && <p>Also considered: {decision.why.considered.join("; ")}.</p>}
        </div>
      )}
    </section>
  );
}
