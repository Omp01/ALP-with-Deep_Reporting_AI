"use client";

import React, { useEffect, useState } from "react";
import {
  Activity,
  AlertCircle,
  ArrowRight,
  Award,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clock,
  Code,
  Compass,
  FileText,
  HelpCircle,
  Layers,
  Link as LinkIcon,
  RefreshCw,
  ShieldCheck,
  User,
  X,
} from "lucide-react";

import {
  Alert,
  Badge,
  Button,
  Dialog,
  EmptyState,
  ErrorState,
  Skeleton,
} from "@/components/ui";
import { formatDateTime } from "@/lib/utils";
import {
  DetailedEvidenceRecord,
  Explanation,
  masteryService,
} from "@/services/mastery";

interface EvidenceExplorerProps {
  evidenceId: string | null;
  onClose: () => void;
  claimContext?: {
    statement?: string;
    category?: string;
  };
}

export function EvidenceExplorer({
  evidenceId,
  onClose,
  claimContext,
}: EvidenceExplorerProps) {
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [record, setRecord] = useState<DetailedEvidenceRecord | null>(null);
  const [explanation, setExplanation] = useState<Explanation | null>(null);
  const [showRawEvent, setShowRawEvent] = useState<boolean>(false);

  useEffect(() => {
    if (!evidenceId) {
      setRecord(null);
      setExplanation(null);
      setError(null);
      return;
    }

    async function loadEvidence() {
      setLoading(true);
      setError(null);
      try {
        const data = await masteryService.getEvidenceDetail(evidenceId!);
        setRecord(data);

        // Optionally load full competency explanation if learner & competency are available
        if (data.user_id && data.competency_id) {
          try {
            const exp = await masteryService.explain(data.user_id, data.competency_id);
            setExplanation(exp);
          } catch {
            // Explanation is optional contextual data
          }
        }
      } catch (err: any) {
        setError(err.message || "Failed to load evidence record");
      } finally {
        setLoading(false);
      }
    }

    loadEvidence();
  }, [evidenceId]);

  const cleanId = evidenceId ? evidenceId.replace(/^evidence_/, "") : "";
  const displayId = cleanId ? `E-${cleanId.slice(0, 8).toUpperCase()}` : "";

  return (
    <Dialog
      open={evidenceId !== null}
      onClose={onClose}
      title={`Evidence Explorer — ${displayId}`}
      variant="drawer"
      size="lg"
    >
      <div className="space-y-6 text-sm" data-testid="evidence-explorer-drawer">
        {/* Claim Context Header (if opened from an insight/claim) */}
        {claimContext?.statement && (
          <div className="p-4 bg-indigo-50/60 border border-indigo-100 rounded-xl space-y-1.5">
            <div className="flex items-center gap-2 text-xs font-semibold text-indigo-900 uppercase tracking-wider">
              <ShieldCheck className="w-4 h-4 text-indigo-600" />
              Cited Claim Connection
            </div>
            <p className="text-sm font-medium text-indigo-950">{claimContext.statement}</p>
            {claimContext.category && (
              <span className="inline-block px-2 py-0.5 rounded text-[11px] font-semibold bg-indigo-100 text-indigo-800">
                {claimContext.category}
              </span>
            )}
          </div>
        )}

        {loading ? (
          <div className="space-y-4 py-4">
            <Skeleton className="h-16 rounded-xl" />
            <Skeleton className="h-32 rounded-xl" />
            <Skeleton className="h-48 rounded-xl" />
          </div>
        ) : error ? (
          <ErrorState error={error} onRetry={() => setRecord(null)} />
        ) : !record ? (
          <EmptyState
            title="No Supporting Evidence"
            description="The selected evidence reference could not be located in the audit trail."
          />
        ) : (
          <div className="space-y-6">
            {/* 1. Evidence Header Summary */}
            <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 space-y-3">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <span className="text-xs font-mono font-bold text-indigo-600 bg-indigo-50 px-2 py-0.5 rounded border border-indigo-200">
                    {displayId}
                  </span>
                  <h3 className="font-bold text-slate-900 text-base mt-1.5 capitalize">
                    {record.source_type.replace(/_/g, " ")}
                  </h3>
                  <p className="text-xs text-slate-500 mt-0.5 flex items-center gap-2">
                    <Clock className="w-3.5 h-3.5 text-slate-400" />
                    <span>Recorded: {formatDateTime(record.occurred_at)}</span>
                  </p>
                </div>
                <Badge
                  variant={record.signal >= 0.7 ? "success" : record.signal < 0.5 ? "danger" : "warning"}
                  size="md"
                >
                  Signal: {(record.signal * 100).toFixed(0)}%
                </Badge>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-3 border-t border-slate-200/60 text-xs">
                <div>
                  <span className="text-slate-400 block text-[10px]">Grader Confidence</span>
                  <span className="font-semibold text-slate-800">
                    {(record.confidence * 100).toFixed(0)}%
                  </span>
                </div>
                <div>
                  <span className="text-slate-400 block text-[10px]">Attempt Number</span>
                  <span className="font-semibold text-slate-800">
                    {record.attempt_number || 1}
                  </span>
                </div>
                <div>
                  <span className="text-slate-400 block text-[10px]">Response Time</span>
                  <span className="font-semibold text-slate-800">
                    {record.response_time_ms
                      ? `${(record.response_time_ms / 1000).toFixed(1)}s`
                      : "—"}
                  </span>
                </div>
                <div>
                  <span className="text-slate-400 block text-[10px]">Difficulty</span>
                  <span className="font-semibold text-slate-800">
                    {record.difficulty !== null ? record.difficulty.toFixed(2) : "Standard"}
                  </span>
                </div>
              </div>
            </div>

            {/* 2. Observed Data */}
            <div className="space-y-2">
              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500 flex items-center gap-1.5">
                <CheckCircle2 className="w-4 h-4 text-slate-600" />
                Observed Telemetry Data
              </h4>

              <div className="p-4 bg-white border border-slate-200 rounded-xl space-y-3">
                {record.error_type && (
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-slate-500 font-medium">Error Classification:</span>
                    <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-red-50 text-red-700 border border-red-200 capitalize">
                      {record.error_type.replace(/_/g, " ")}
                    </span>
                  </div>
                )}

                {record.evidence_quote && (
                  <div className="p-3 bg-slate-50 border-l-4 border-indigo-500 text-xs font-mono text-slate-800 rounded-r-lg">
                    <span className="font-sans text-[10px] text-slate-400 block uppercase font-bold mb-1">
                      Learner Response Quote:
                    </span>
                    "{record.evidence_quote}"
                  </div>
                )}

                {record.source && Object.keys(record.source).length > 0 && (
                  <div className="space-y-1 pt-2 border-t border-slate-100">
                    <span className="text-xs font-semibold text-slate-700">Source Attributes:</span>
                    <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-1.5 text-xs pt-1">
                      {Object.entries(record.source).map(([k, v]) => (
                        <div key={k} className="flex flex-col">
                          <dt className="text-[10px] text-slate-400 uppercase font-semibold">
                            {k.replace(/_/g, " ")}
                          </dt>
                          <dd className="font-mono text-slate-800 truncate">
                            {typeof v === "object" ? JSON.stringify(v) : String(v)}
                          </dd>
                        </div>
                      ))}
                    </dl>
                  </div>
                )}
              </div>
            </div>

            {/* 3. Source Trace Hierarchy */}
            <div className="space-y-2">
              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500 flex items-center gap-1.5">
                <Compass className="w-4 h-4 text-slate-600" />
                Source Trace Hierarchy
              </h4>
              <div className="p-4 bg-slate-900 text-slate-100 rounded-xl font-mono text-xs overflow-x-auto space-y-2">
                <div className="flex items-center gap-2 text-slate-400">
                  <span className="px-1.5 py-0.5 bg-slate-800 rounded text-[10px]">TENANT</span>
                  <span>Org Scope: {record.org_id || "Tenant Scope"}</span>
                </div>
                <div className="pl-3 border-l-2 border-slate-700 space-y-2">
                  <div className="flex items-center gap-2 text-slate-300">
                    <span className="px-1.5 py-0.5 bg-indigo-950 text-indigo-400 border border-indigo-800 rounded text-[10px]">
                      LEARNER
                    </span>
                    <span>User ID: {record.user_id}</span>
                  </div>
                  <div className="pl-3 border-l-2 border-slate-700 space-y-2">
                    <div className="flex items-center gap-2 text-slate-300">
                      <span className="px-1.5 py-0.5 bg-emerald-950 text-emerald-400 border border-emerald-800 rounded text-[10px]">
                        COMPETENCY
                      </span>
                      <span>Competency ID: {record.competency_id}</span>
                    </div>
                    {record.session_id && (
                      <div className="pl-3 border-l-2 border-slate-700 text-slate-400">
                        <span>Session ID: {record.session_id}</span>
                      </div>
                    )}
                    {record.source_event_id && (
                      <div className="pl-3 border-l-2 border-indigo-500 text-indigo-300 font-bold">
                        <span>Telemetry Event ID: {record.source_event_id}</span>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </div>

            {/* 4. Evidence Timeline & BKT State Updates (if available) */}
            {explanation && explanation.chain.length > 0 && (
              <div className="space-y-2">
                <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500 flex items-center gap-1.5">
                  <Activity className="w-4 h-4 text-slate-600" />
                  Competency Mastery Timeline Updates
                </h4>
                <div className="space-y-2 max-h-60 overflow-y-auto pr-1">
                  {explanation.chain.map((step) => {
                    const isTarget = step.evidence_id === record.id;
                    return (
                      <div
                        key={step.update_id}
                        className={`p-3 rounded-lg border text-xs transition-all ${
                          isTarget
                            ? "bg-indigo-50 border-indigo-300 shadow-2xs"
                            : "bg-white border-slate-200"
                        }`}
                      >
                        <div className="flex items-center justify-between gap-2 font-medium text-slate-800">
                          <span>
                            Step #{step.sequence}: {step.summary}
                          </span>
                          <span className="font-mono text-[11px] text-slate-500">
                            {step.previous_mastery !== null
                              ? (step.previous_mastery * 100).toFixed(1)
                              : "Prior"}
                            % →{" "}
                            <strong className="text-indigo-600">
                              {(step.new_mastery * 100).toFixed(1)}%
                            </strong>
                          </span>
                        </div>
                        <div className="text-[10px] text-slate-400 mt-1 flex items-center gap-2">
                          <span>Recorded: {formatDateTime(step.occurred_at)}</span>
                          <span>·</span>
                          <span>Method: {step.method}</span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* 5. Raw Event Payload Inspection */}
            {record.source_event_id && (
              <div className="pt-2 border-t border-slate-200">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setShowRawEvent(!showRawEvent)}
                  className="gap-1.5 text-xs"
                >
                  <Code className="w-3.5 h-3.5" />
                  {showRawEvent ? "Hide Event Payload" : "View Raw Event Payload"}
                </Button>

                {showRawEvent && (
                  <div className="mt-3 p-3 bg-slate-900 text-slate-200 rounded-xl font-mono text-xs overflow-x-auto max-h-48">
                    <pre>
                      {JSON.stringify(
                        {
                          event_id: record.source_event_id,
                          event_type: record.source_type,
                          user_id: record.user_id,
                          session_id: record.session_id,
                          occurred_at: record.occurred_at,
                          payload: record.source,
                        },
                        null,
                        2
                      )}
                    </pre>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </Dialog>
  );
}
