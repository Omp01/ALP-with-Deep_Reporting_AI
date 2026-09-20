"use client";

import React, { useState } from "react";
import { ShieldCheck, Target } from "lucide-react";

import { AppShell, PageHeader } from "@/components/shell";
import { Badge, Button, Dialog, EmptyState, ErrorState, MasteryBar, SkeletonTable, Table, TableContainer, TBody, TD, TH, THead, TR } from "@/components/ui";
import { useApi } from "@/hooks/use-api";
import { formatDateTime, getTrendLabel, pluralize } from "@/lib/utils";
import { masteryService, type ChainStep, type CompetencyState, type SkillGap } from "@/services/mastery";

const pct = (value: number) => `${Math.round(value * 100)}%`;

function TrendCell({ state }: { state: CompetencyState }) {
  if (state.trend === "insufficient_data") return <span className="text-fg-muted">Not enough history</span>;
  const t = getTrendLabel(state.trend);
  return (
    <span className={t.color}>
      {t.icon} {t.label}
      {state.trend_delta !== null && <span className="ml-1 text-xs text-fg-muted">({state.trend_delta > 0 ? "+" : ""}{state.trend_delta.toFixed(2)})</span>}
    </span>
  );
}

export default function LearnerCompetenciesPage() {
  const mine = useApi((signal) => masteryService.mine(signal));
  const gaps = useApi((signal) => masteryService.myGaps(signal));
  const [open, setOpen] = useState<CompetencyState | null>(null);

  const states = mine.data?.competencies ?? [];
  const gapFor = new Map((gaps.data?.gaps ?? []).map((g) => [g.competency_id, g]));

  return (
    <AppShell roles={["learner", "manager", "instructor", "org_admin", "system_admin"]}>
      <PageHeader
        title="Competencies"
        description="What you have shown you can do, worked out from your graded answers and assignments. Watching or reading never counts as mastery; only evidence does."
      />

      {mine.loading ? (
        <SkeletonTable rows={5} />
      ) : mine.error ? (
        <ErrorState error={mine.error} onRetry={mine.refetch} />
      ) : states.length === 0 ? (
        <EmptyState
          icon={Target}
          title="No competency evidence yet"
          description="Your competencies appear here once you answer graded questions or hand in assignments. Nothing is shown until there is evidence behind it."
        />
      ) : (
        <>
          <TableContainer>
            <Table caption="Your competencies">
              <THead>
                <TR>
                  <TH>Competency</TH>
                  <TH className="w-56">Mastery</TH>
                  <TH>Confidence</TH>
                  <TH>Trend</TH>
                  <TH>Evidence</TH>
                  <TH>
                    <span className="sr-only">Details</span>
                  </TH>
                </TR>
              </THead>
              <TBody>
                {states.map((s) => {
                  const gap = gapFor.get(s.competency_id);
                  return (
                    <TR key={s.competency_id} data-competency={s.code}>
                      <TD>
                        <div className="font-medium text-fg">{s.name}</div>
                        <div className="flex items-center gap-1.5 text-xs text-fg-muted">
                          <span>{s.status}</span>
                          {gap && (
                            <Badge variant={gap.severity === "critical" || gap.severity === "high" ? "danger" : "warning"} size="sm">
                              below target ({pct(gap.target_mastery)})
                            </Badge>
                          )}
                        </div>
                      </TD>
                      <TD>
                        <MasteryBar mastery={s.mastery} />
                      </TD>
                      <TD className="tabular-nums">
                        <span title="How much evidence stands behind the estimate, not how high it is">{pct(s.confidence)}</span>
                      </TD>
                      <TD>
                        <TrendCell state={s} />
                      </TD>
                      <TD className="text-fg-muted">
                        {pluralize(s.evidence_count, "answer")}
                        {s.retries > 0 && <span className="block text-xs">{s.retries} on retries</span>}
                      </TD>
                      <TD className="text-right">
                        <Button variant="secondary" size="sm" onClick={() => setOpen(s)} aria-label={`Why is ${s.name} at ${pct(s.mastery)}?`}>
                          Why {pct(s.mastery)}?
                        </Button>
                      </TD>
                    </TR>
                  );
                })}
              </TBody>
            </Table>
          </TableContainer>

          <GapList gaps={gaps.data?.gaps ?? []} notEnough={gaps.data?.not_enough_evidence ?? []} />
        </>
      )}

      <Dialog open={open !== null} onClose={() => setOpen(null)} title={open ? `Why ${open.name} is at ${pct(open.mastery)}` : ""} variant="drawer" size="lg">
        {open && mine.data && <ChainBody key={open.competency_id} userId={mine.data.user_id} state={open} />}
      </Dialog>
    </AppShell>
  );
}

function GapList({ gaps, notEnough }: { gaps: SkillGap[]; notEnough: SkillGap[] }) {
  if (gaps.length === 0 && notEnough.length === 0) return null;
  return (
    <section className="mt-8" aria-labelledby="gaps-title">
      <h2 id="gaps-title" className="text-base font-semibold text-fg">
        Where you are below your target
      </h2>
      {gaps.length === 0 ? (
        <p className="mt-2 text-sm text-fg-muted">You are at or above the target on every competency assessed so far.</p>
      ) : (
        <ul className="mt-3 space-y-3">
          {gaps.map((g) => (
            <li key={g.competency_id} className="rounded-lg border border-border p-4" data-gap={g.code}>
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium text-fg">{g.name}</span>
                <Badge variant={g.severity === "critical" || g.severity === "high" ? "danger" : "warning"} size="sm">
                  {g.severity}
                </Badge>
              </div>
              <ul className="mt-2 list-disc space-y-0.5 pl-5 text-sm text-fg-muted">
                {g.reasons.map((r) => (
                  <li key={r}>{r}</li>
                ))}
              </ul>
              {g.note && <p className="mt-2 text-xs text-fg-muted">{g.note}</p>}
            </li>
          ))}
        </ul>
      )}
      {notEnough.length > 0 && (
        <p className="mt-3 text-xs text-fg-muted">
          Not enough evidence yet to say whether {notEnough.map((n) => n.name).join(", ")} {notEnough.length === 1 ? "is" : "are"} a gap.
        </p>
      )}
    </section>
  );
}

function ChainBody({ userId, state }: { userId: string; state: CompetencyState }) {
  const explained = useApi((signal) => masteryService.explain(userId, state.competency_id, signal), { deps: [userId, state.competency_id] });

  if (explained.loading) return <SkeletonTable rows={4} />;
  if (explained.error || !explained.data) return <ErrorState error={explained.error} onRetry={explained.refetch} />;
  const e = explained.data;

  return (
    <div className="space-y-5" data-testid="evidence-chain">
      <p className="text-sm text-fg-muted">
        Every step below is a stored answer or grade. Mastery is recalculated after each one by a fixed formula ({e.method}); no language model decides it.
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant={e.verified ? "success" : "danger"} data-testid="chain-verified">
          <ShieldCheck className="mr-1 size-3.5" aria-hidden="true" />
          {e.verified ? "Recomputed from the evidence: matches" : "Does not match the evidence"}
        </Badge>
        <span className="text-xs text-fg-muted">
          confidence {pct(e.state.confidence)} · {pluralize(e.chain.length, "piece", "pieces")} of evidence
        </span>
      </div>

      <ol className="space-y-3" aria-label="Evidence chain">
        {e.chain.map((step) => (
          <StepRow key={step.update_id} step={step} />
        ))}
      </ol>

      {e.parameters && (
        <details className="text-xs text-fg-muted">
          <summary className="cursor-pointer text-fg">Parameters used</summary>
          <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 sm:grid-cols-3">
            {Object.entries(e.parameters).map(([k, v]) => (
              <div key={k} className="flex justify-between gap-2">
                <dt>{k.replaceAll("_", " ")}</dt>
                <dd className="tabular-nums text-fg">{typeof v === "number" ? Number(v.toFixed(4)) : String(v)}</dd>
              </div>
            ))}
          </dl>
        </details>
      )}
    </div>
  );
}

function StepRow({ step }: { step: ChainStep }) {
  const before = step.previous_mastery === null ? null : pct(step.previous_mastery);
  return (
    <li className="rounded-lg border border-border p-3 text-sm" data-step={step.sequence}>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <span className="text-xs text-fg-muted">
          #{step.sequence} · {formatDateTime(step.occurred_at)}
        </span>
        <span className="tabular-nums font-medium text-fg">
          {before ?? "start"} → {pct(step.new_mastery)}
        </span>
      </div>
      <p className="mt-1 text-fg">{step.summary}</p>
      {step.evidence_quote && <blockquote className="mt-2 border-l-2 border-border pl-3 text-xs italic text-fg-muted">“{step.evidence_quote}”</blockquote>}
      {step.error_type && <p className="mt-1 text-xs text-fg-muted">Kind of mistake: {step.error_type.replaceAll("_", " ")}</p>}
      {step.note && <p className="mt-1 text-xs text-warning">{step.note}</p>}
    </li>
  );
}
