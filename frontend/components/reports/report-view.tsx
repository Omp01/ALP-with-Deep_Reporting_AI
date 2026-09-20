"use client";

import React, { useState } from "react";
import { FileSearch, RefreshCw, ShieldCheck, Sparkles } from "lucide-react";

import { AppShell, PageHeader } from "@/components/shell";
import { Alert, Badge, Button, Dialog, EmptyState, ErrorState, Skeleton, SkeletonText } from "@/components/ui";
import { useApi } from "@/hooks/use-api";
import { formatDateTime } from "@/lib/utils";
import type { Role } from "@/lib/auth";
import { reportsService, type Audience, type Claim, type EvidenceRecord, type Report } from "@/services/reports";

const TYPE_LABEL: Record<string, string> = {
  OBSERVATION: "Observation",
  CORRELATION: "Association",
  PLAUSIBLE_EXPLANATION: "Possible explanation",
  CAUSAL_CLAIM: "Causal claim",
};

/** A recorded value made readable. Probabilities are shown as stored (0.43), never rescaled. */
function show(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : String(Number(value.toFixed(4)));
  if (Array.isArray(value)) return value.map(show).join(", ") || "—";
  if (typeof value === "object")
    return (
      Object.entries(value as Record<string, unknown>)
        .map(([k, v]) => `${k.replaceAll("_", " ")}: ${show(v)}`)
        .join("; ") || "—"
    );
  return String(value);
}

function EvidenceItem({ reportId, id }: { reportId: string; id: string }) {
  const record = useApi<EvidenceRecord>((signal) => reportsService.evidence(reportId, id, signal), { deps: [reportId, id] });
  if (record.loading) return <SkeletonText lines={3} />;
  if (record.error || !record.data) return <ErrorState error={record.error} onRetry={record.refetch} />;
  const r = record.data;
  const d = r.data;
  const hidden = r.type === "update" ? ["previous_mastery", "new_mastery", "signal", "weight"] : [];
  return (
    <div className="rounded-lg border border-border p-3 text-sm" data-evidence-id={r.id}>
      <p className="font-medium text-fg">{r.label}</p>
      <p className="text-xs text-fg-muted">
        {r.type}
        {r.occurred_at ? ` · ${formatDateTime(r.occurred_at)}` : ""}
      </p>
      {r.type === "update" && (
        <p className="mt-2 tabular-nums">
          Previous mastery <strong>{show(d.previous_mastery ?? "start")}</strong> → new mastery <strong>{show(d.new_mastery)}</strong> (signal {show(d.signal)}, weight {show(d.weight)})
        </p>
      )}
      <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-xs">
        {Object.entries(d)
          .filter(([k]) => !hidden.includes(k))
          .map(([k, v]) => (
            <React.Fragment key={k}>
              <dt className="text-fg-muted">{k.replaceAll("_", " ")}</dt>
              <dd className="break-words text-fg">{show(v)}</dd>
            </React.Fragment>
          ))}
      </dl>
    </div>
  );
}

/** The evidence drawer: everything a claim cites, exactly as it was when the report was written. */
export function EvidenceDrawer({ reportId, claim, onClose }: { reportId: string; claim: Claim | null; onClose: () => void }) {
  return (
    <Dialog open={claim !== null} onClose={onClose} title="Evidence" variant="drawer" size="lg">
      {claim && (
        <div className="space-y-4" data-testid="evidence-drawer">
          <p className="text-sm text-fg">{claim.claim}</p>
          <p className="text-xs text-fg-muted">
            {TYPE_LABEL[claim.claim_type] ?? claim.claim_type} · confidence {Math.round(claim.confidence * 100)}% (how much evidence stands behind it, not a probability that it is true)
          </p>
          <div className="space-y-3">
            {claim.evidence_ids.map((id) => (
              <EvidenceItem key={id} reportId={reportId} id={id} />
            ))}
          </div>
        </div>
      )}
    </Dialog>
  );
}

function ClaimRow({ claim, onOpen }: { claim: Claim; onOpen: (c: Claim) => void }) {
  return (
    <li className="rounded-lg border border-border p-4" data-claim-type={claim.claim_type} data-claim-source={claim.source}>
      <p className="text-sm text-fg">{claim.claim}</p>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <Badge variant={claim.claim_type === "OBSERVATION" ? "neutral" : "info"} size="sm">
          {TYPE_LABEL[claim.claim_type] ?? claim.claim_type}
        </Badge>
        {claim.source === "ai" && (
          <Badge variant="primary" size="sm">
            AI interpretation
          </Badge>
        )}
        <Button variant="secondary" size="sm" onClick={() => onOpen(claim)} data-testid="open-evidence">
          <FileSearch aria-hidden="true" /> Evidence {claim.evidence_ids.length}
        </Button>
      </div>
    </li>
  );
}

/**
 * One reporting experience. The audience decides what is asked and shown; the mechanism is the same everywhere: every claim cites
 * evidence, the evidence opens in a drawer, and what failed validation is listed, not hidden.
 */
export function ReportPage({ audience, title, description, roles, scopeId }: { audience: Audience; title: string; description: string; roles: Role[]; scopeId?: string }) {
  const [useAi, setUseAi] = useState(true);
  const [open, setOpen] = useState<Claim | null>(null);
  const [nonce, setNonce] = useState(0);
  const report = useApi<Report>((signal) => { void signal; return reportsService.generate({ audience, scope_id: scopeId, use_ai: useAi, force: nonce > 0 }); }, { deps: [audience, scopeId, useAi, nonce] });

  return (
    <AppShell roles={roles}>
      <PageHeader
        title={title}
        description={description}
        actions={
          <div className="flex items-center gap-2">
            <label className="flex items-center gap-1.5 text-xs text-fg-muted">
              <input type="checkbox" checked={useAi} onChange={(e) => setUseAi(e.target.checked)} className="accent-[var(--color-primary)]" data-testid="use-ai" /> Use AI interpretation
            </label>
            <Button variant="secondary" size="sm" onClick={() => setNonce((n) => n + 1)} disabled={report.loading || report.refreshing} data-testid="regenerate">
              <RefreshCw aria-hidden="true" /> Regenerate
            </Button>
          </div>
        }
      />
      {report.loading ? (
        <div className="space-y-3" aria-busy="true">
          <Skeleton className="h-16 w-full" />
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-24 w-full" />
        </div>
      ) : report.error || !report.data ? (
        <ErrorState error={report.error} onRetry={report.refetch} />
      ) : (
        <ReportBody report={report.data} onOpen={setOpen} />
      )}
      {report.data && <EvidenceDrawer reportId={report.data.id} claim={open} onClose={() => setOpen(null)} />}
    </AppShell>
  );
}

export function ReportBody({ report, onOpen }: { report: Report; onOpen: (c: Claim) => void }) {
  const ordered = [...report.claims].sort((a, b) => Number(a.source === "ai") - Number(b.source === "ai"));
  return (
    <div className="space-y-5" data-testid="report" data-report-id={report.id}>
      <div className="flex flex-wrap items-center gap-2 text-xs text-fg-muted">
        <Badge variant={report.generated_by === "ai" ? "primary" : "neutral"} size="sm">
          {report.generated_by === "ai" ? <Sparkles className="mr-1 size-3" aria-hidden="true" /> : <ShieldCheck className="mr-1 size-3" aria-hidden="true" />}
          {report.generated_by === "ai" ? "AI-assisted, citations validated" : "Computed from stored data, no AI"}
        </Badge>
        <span>{report.scope.scope_label}</span>
        <span>
          · {formatDateTime(report.scope.period_start)} to {formatDateTime(report.scope.period_end)}
        </span>
        <span>· {report.counts.records} evidence records</span>
        {report.cached && <span>· reused from {formatDateTime(report.created_at)}</span>}
      </div>

      {report.ai_status === "unavailable" || report.ai_status === "invalid" ? (
        <Alert variant="warning" title="The AI interpretation is not included">
          {report.ai_note ?? "The reporting model did not answer."} The findings below are computed from stored data and are complete without it.
        </Alert>
      ) : report.ai_note ? (
        <Alert variant="info">{report.ai_note}</Alert>
      ) : null}

      {report.summary && (
        <section aria-label="Summary" className="rounded-lg bg-surface-raised p-4 text-sm text-fg" data-testid="report-summary">
          {report.summary}
        </section>
      )}

      {ordered.length === 0 ? (
        <EmptyState title="Nothing to report yet" description={report.notes[0] ?? "There is not enough recorded evidence for this scope."} />
      ) : (
        <ul className="space-y-3" aria-label="Findings">
          {ordered.map((c, i) => (
            <ClaimRow key={`${i}-${c.claim.slice(0, 20)}`} claim={c} onOpen={onOpen} />
          ))}
        </ul>
      )}

      {report.notes.length > 0 && ordered.length > 0 && <p className="text-xs text-fg-muted">{report.notes.join(" ")}</p>}

      {report.rejected_claims.length > 0 && (
        <details className="rounded-lg border border-border p-4 text-sm" data-testid="rejected-claims">
          <summary className="cursor-pointer font-medium text-fg">{report.rejected_claims.length} statement(s) were refused by citation validation</summary>
          <p className="mt-2 text-xs text-fg-muted">These were proposed but could not be supported by the evidence, so they are not part of the report.</p>
          <ul className="mt-2 space-y-2">
            {report.rejected_claims.map((c, i) => (
              <li key={i} className="text-xs text-fg-muted">
                <span className="text-fg">{c.claim}</span> — {(c.flags ?? []).join("; ")}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
