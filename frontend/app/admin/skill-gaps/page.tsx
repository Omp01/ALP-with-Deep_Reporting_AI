"use client";

import React, { useState } from "react";
import { AlertTriangle, Target } from "lucide-react";

import { AppShell, PageHeader } from "@/components/shell";
import { Badge, Button, EmptyState, ErrorState, Progress, SkeletonTable, Stat, StatGrid, Tabs, TabsContent, TabsList, TabsTrigger, useToast } from "@/components/ui";
import { useApi } from "@/hooks/use-api";
import { formatRelativeTime, getRiskColor, pluralize } from "@/lib/utils";
import { masteryService, riskService, type RiskRecord } from "@/services/mastery";

const ROLES = ["org_admin", "instructor", "manager"] as const;
const pct = (v: number) => `${Math.round(v * 100)}%`;

export default function SkillGapsAndRiskPage() {
  const gaps = useApi((signal) => masteryService.cohortGaps({}, signal));
  const risks = useApi((signal) => riskService.active(signal));
  const { toast } = useToast();
  const [scanning, setScanning] = useState(false);

  const scan = async () => {
    setScanning(true);
    try {
      await riskService.scan();
      risks.refetch();
      toast({ title: "Risk scan finished", variant: "success" });
    } catch (err) {
      toast({ title: "The scan failed", description: err instanceof Error ? err.message : undefined, variant: "error" });
    } finally {
      setScanning(false);
    }
  };

  const atRisk = (risks.data ?? []).filter((r) => r.risk_level !== "low");

  return (
    <AppShell roles={[...ROLES]}>
      <PageHeader
        title="Skill gaps and risk"
        description="Where the learners you are responsible for are below their targets, and who may need help. Every line states the figures behind it; where there is too little evidence, it says so instead of guessing."
        actions={
          <Button variant="secondary" onClick={scan} disabled={scanning}>
            {scanning ? "Scanning…" : "Run risk scan"}
          </Button>
        }
      />

      <StatGrid>
        <Stat label="Learners with evidence" value={gaps.data ? String(gaps.data.learners_with_evidence) : "—"} icon={Target} />
        <Stat label="Competencies below target" value={gaps.data ? String(gaps.data.competencies.filter((c) => c.learners_below_target > 0).length) : "—"} icon={Target} />
        <Stat label="Learners at risk" value={risks.data ? String(new Set(atRisk.map((r) => r.user_id)).size) : "—"} icon={AlertTriangle} />
      </StatGrid>

      <Tabs defaultValue="gaps" className="mt-6">
        <TabsList aria-label="Views">
          <TabsTrigger value="gaps">Skill gaps</TabsTrigger>
          <TabsTrigger value="risk">At-risk learners</TabsTrigger>
        </TabsList>

        <TabsContent value="gaps">
          {gaps.loading ? (
            <SkeletonTable rows={5} />
          ) : gaps.error ? (
            <ErrorState error={gaps.error} onRetry={gaps.refetch} />
          ) : gaps.data!.competencies.length === 0 ? (
            <EmptyState icon={Target} title="No gaps to show yet" description="Competencies appear once at least two graded answers exist for a learner. Until then nobody is labelled weak." />
          ) : (
            <ul className="space-y-3" aria-label="Competencies by share of learners below target">
              {gaps.data!.competencies.map((c) => (
                <li key={c.competency_id} className="rounded-lg border border-border p-4" data-gap-competency={c.code ?? c.name}>
                  <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <span className="font-medium text-fg">{c.name}</span>
                    <span className="text-sm text-fg" data-testid="gap-count">
                      {c.learners_below_target} of {c.assessed_learners} assessed {c.assessed_learners === 1 ? "learner is" : "learners are"} below {pct(c.target_mastery)}
                    </span>
                  </div>
                  <Progress
                    value={c.share_below_target * 100}
                    tone={c.share_below_target >= 0.5 ? "danger" : c.share_below_target > 0 ? "warning" : "success"}
                    ariaLabel={`${c.name}: share of learners below target`}
                    className="mt-2"
                  />
                  <p className="mt-2 text-xs text-fg-muted">
                    Lowest mastery {pct(c.lowest_mastery)} · median {pct(c.median_mastery)} · {c.learners_declining} declining · based on {pluralize(c.evidence_count, "answer")}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </TabsContent>

        <TabsContent value="risk">
          {risks.loading ? (
            <SkeletonTable rows={5} />
          ) : risks.error ? (
            <ErrorState error={risks.error} onRetry={risks.refetch} />
          ) : atRisk.length === 0 ? (
            <EmptyState
              icon={AlertTriangle}
              title="Nobody is currently at risk"
              description="Risk is assessed from recorded evidence and activity. Run a scan after learners have answered questions."
            />
          ) : (
            <ul className="space-y-3" aria-label="At-risk learners">
              {atRisk.map((r) => (
                <RiskCard key={r.id} risk={r} onResolved={risks.refetch} />
              ))}
            </ul>
          )}
        </TabsContent>
      </Tabs>
    </AppShell>
  );
}

function RiskCard({ risk, onResolved }: { risk: RiskRecord; onResolved: () => void }) {
  const { toast } = useToast();
  const [busy, setBusy] = useState(false);
  const resolve = async () => {
    setBusy(true);
    try {
      await riskService.resolve(risk.id);
      onResolved();
    } catch (err) {
      toast({ title: "Could not resolve", description: err instanceof Error ? err.message : undefined, variant: "error" });
    } finally {
      setBusy(false);
    }
  };
  const reasons = risk.risk_details.length > 0 ? risk.risk_details.map((d) => d.description) : risk.risk_factors;

  return (
    <li className="rounded-lg border border-border p-4" data-risk-learner={risk.user_id}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="font-medium text-fg">{risk.learner_name}</p>
          <p className="text-xs text-fg-muted">
            {risk.course_title} · assessed {formatRelativeTime(risk.updated_at)}
          </p>
        </div>
        <span className={`rounded-full border px-2.5 py-0.5 text-xs font-medium ${getRiskColor(risk.risk_level)}`}>{risk.risk_level}</span>
      </div>
      <ul className="mt-3 list-disc space-y-0.5 pl-5 text-sm text-fg" aria-label="Why">
        {reasons.map((reason) => (
          <li key={reason}>{reason}</li>
        ))}
      </ul>
      {risk.recommended_actions.length > 0 && (
        <div className="mt-3">
          <p className="text-xs font-semibold uppercase tracking-wide text-fg-muted">Suggested next steps</p>
          <ul className="mt-1 list-disc space-y-0.5 pl-5 text-sm text-fg-muted">
            {risk.recommended_actions.map((a) => (
              <li key={a}>{a}</li>
            ))}
          </ul>
        </div>
      )}
      <div className="mt-3 flex justify-end">
        <Button variant="secondary" size="sm" onClick={resolve} disabled={busy}>
          Mark resolved
        </Button>
      </div>
      <Badge variant="neutral" size="sm" className="mt-2">
        {risk.risk_details.reduce((sum, d) => sum + d.points, 0)} risk points
      </Badge>
    </li>
  );
}
