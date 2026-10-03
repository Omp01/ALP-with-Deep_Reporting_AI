"use client";

import React, { useState } from "react";
import {
  Sparkles,
  Search,
  AlertTriangle,
  CheckCircle2,
  FileText,
  Loader2,
  HelpCircle,
  ShieldCheck,
  ArrowRight,
  Info,
} from "lucide-react";
import { Alert, Badge, Button, Card } from "@/components/ui";
import { reportsService, InvestigationResponse, Claim } from "@/services/reports";

interface InvestigationPanelProps {
  teamId?: string;
  courseId?: string;
  onOpenEvidence: (evidenceId: string) => void;
}

const SAMPLE_QUESTIONS = [
  "Why are learners struggling with SQL JOINs?",
  "Why did completion drop this week?",
  "What is causing repeated retries in Module 4?",
  "Which competency gaps are hidden behind high completion?",
];

export function InvestigationPanel({
  teamId,
  courseId,
  onOpenEvidence,
}: InvestigationPanelProps) {
  const [question, setQuestion] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<InvestigationResponse | null>(null);

  const handleInvestigate = async (qText?: string) => {
    const queryToUse = qText || question;
    if (!queryToUse.trim()) return;

    setLoading(true);
    setError(null);

    try {
      const response = await reportsService.investigate({
        question: queryToUse.trim(),
        team_id: teamId,
        course_id: courseId,
        days: 30,
      });
      setResult(response);
    } catch (err: any) {
      console.error("Investigation failed:", err);
      const msg =
        err?.response?.data?.detail?.message ||
        err?.message ||
        "The investigation could not be generated. Please try again.";
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card className="p-6 bg-gradient-to-br from-neutral-900/90 via-neutral-900 to-indigo-950/40 border border-indigo-500/20 shadow-xl rounded-xl space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-neutral-800 pb-4">
        <div className="flex items-center gap-3">
          <div className="p-2.5 rounded-lg bg-indigo-500/10 border border-indigo-500/30 text-indigo-400">
            <Sparkles className="w-5 h-5 animate-pulse" />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-neutral-100 flex items-center gap-2">
              AI Investigation Mode
              <Badge variant="primary" className="bg-indigo-950 text-indigo-300 border-indigo-700/50 text-xs">
                Grounded Deep Analytics
              </Badge>
            </h2>
            <p className="text-xs text-neutral-400">
              Ask questions about team friction, competency gaps, or bottleneck friction grounded strictly in validated evidence.
            </p>
          </div>
        </div>
      </div>

      {/* Input Box & Suggested Chips */}
      <div className="space-y-3">
        <div className="flex gap-2">
          <div className="relative flex-1">
            <Search className="absolute left-3.5 top-3 w-4 h-4 text-neutral-400" />
            <input
              type="text"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleInvestigate()}
              placeholder="e.g. Why are learners struggling with SQL JOINs?"
              disabled={loading}
              className="w-full bg-neutral-950/80 border border-neutral-700/60 rounded-lg pl-10 pr-4 py-2.5 text-sm text-neutral-100 placeholder-neutral-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 focus:border-indigo-500 transition-all"
            />
          </div>
          <Button
            onClick={() => handleInvestigate()}
            disabled={loading || !question.trim()}
            className="bg-indigo-600 hover:bg-indigo-500 text-white font-medium px-5 py-2.5 rounded-lg flex items-center gap-2 transition-all shadow-md shadow-indigo-950"
          >
            {loading ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                Investigating...
              </>
            ) : (
              <>
                Investigate
                <ArrowRight className="w-4 h-4" />
              </>
            )}
          </Button>
        </div>

        {/* Suggested questions */}
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className="text-neutral-400 flex items-center gap-1 font-medium">
            <HelpCircle className="w-3.5 h-3.5 text-indigo-400" /> Suggested:
          </span>
          {SAMPLE_QUESTIONS.map((q, idx) => (
            <button
              key={idx}
              onClick={() => {
                setQuestion(q);
                handleInvestigate(q);
              }}
              disabled={loading}
              className="px-2.5 py-1 rounded-full bg-neutral-800/80 hover:bg-indigo-950/80 border border-neutral-700/60 hover:border-indigo-500/40 text-neutral-300 hover:text-indigo-200 transition-all text-left"
            >
              {q}
            </button>
          ))}
        </div>
      </div>

      {/* Loading state indicator */}
      {loading && (
        <div className="p-6 rounded-lg bg-neutral-950/60 border border-neutral-800 text-center space-y-3">
          <div className="inline-flex items-center justify-center p-3 rounded-full bg-indigo-500/10 text-indigo-400">
            <Loader2 className="w-6 h-6 animate-spin" />
          </div>
          <div className="space-y-1">
            <p className="text-sm font-medium text-neutral-200">Conducting Evidence-Grounded Investigation...</p>
            <div className="flex justify-center items-center gap-4 text-xs text-neutral-400 pt-1">
              <span className="flex items-center gap-1">
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" /> Analyzing evidence package
              </span>
              <span className="flex items-center gap-1">
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" /> Checking competency patterns
              </span>
              <span className="flex items-center gap-1">
                <CheckCircle2 className="w-3.5 h-3.5 text-indigo-400 animate-pulse" /> Validating citations
              </span>
            </div>
          </div>
        </div>
      )}

      {/* Error state */}
      {error && (
        <Alert variant="danger" className="bg-red-950/40 border-red-500/30 text-red-200">
          <AlertTriangle className="w-4 h-4 text-red-400 shrink-0" />
          <div>
            <p className="font-medium text-sm">Investigation Error</p>
            <p className="text-xs text-red-300/90 mt-0.5">{error}</p>
          </div>
        </Alert>
      )}

      {/* Investigation Results Display */}
      {result && !loading && (
        <div className="space-y-6 pt-2 border-t border-neutral-800/80">
          {/* Answer Summary */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-neutral-200 uppercase tracking-wider text-xs">
                Grounded Explanation
              </h3>
              {result.model && (
                <Badge variant="neutral" className="text-[10px] text-neutral-400 border-neutral-700">
                  Model: {result.model}
                </Badge>
              )}
            </div>
            <div className="p-4 rounded-lg bg-neutral-950/80 border border-neutral-800 text-sm text-neutral-200 leading-relaxed">
              {result.summary || "No conclusive summary generated for this evidence window."}
            </div>
          </div>

          {/* Validated Claims */}
          {result.claims && result.claims.length > 0 && (
            <div className="space-y-3">
              <h3 className="text-xs font-semibold text-neutral-400 uppercase tracking-wider">
                Evidence-Grounded Claims & Observations ({result.claims.length})
              </h3>
              <div className="space-y-2.5">
                {result.claims.map((claim: Claim, idx: number) => (
                  <div
                    key={idx}
                    className="p-3.5 rounded-lg bg-neutral-950/60 border border-neutral-800 hover:border-neutral-700 transition-all space-y-2"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <p className="text-sm text-neutral-200 font-medium">{claim.claim}</p>
                      <Badge
                        variant="info"
                        className={
                          claim.claim_type === "OBSERVATION"
                            ? "bg-blue-950 text-blue-300 border-blue-800/40 text-[10px]"
                            : claim.claim_type === "PLAUSIBLE_EXPLANATION"
                            ? "bg-purple-950 text-purple-300 border-purple-800/40 text-[10px]"
                            : "bg-amber-950 text-amber-300 border-amber-800/40 text-[10px]"
                        }
                      >
                        {claim.claim_type}
                      </Badge>
                    </div>

                    {/* Evidence Badges */}
                    {claim.evidence_ids && claim.evidence_ids.length > 0 && (
                      <div className="flex items-center gap-1.5 flex-wrap pt-1">
                        <span className="text-[11px] text-neutral-400 flex items-center gap-1">
                          <FileText className="w-3 h-3 text-indigo-400" /> Evidence:
                        </span>
                        {claim.evidence_ids.map((eid) => (
                          <button
                            key={eid}
                            onClick={() => onOpenEvidence(eid)}
                            className="px-2 py-0.5 rounded bg-indigo-950/70 hover:bg-indigo-900 border border-indigo-700/50 text-indigo-300 hover:text-indigo-100 text-[11px] font-mono transition-all flex items-center gap-1"
                          >
                            [{eid}]
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Limitations */}
          {result.limits && result.limits.length > 0 && (
            <div className="p-3.5 rounded-lg bg-amber-950/20 border border-amber-800/30 text-xs text-amber-300 space-y-1">
              <div className="flex items-center gap-1.5 font-semibold text-amber-200">
                <Info className="w-4 h-4 text-amber-400" /> Scope & Data Limitations
              </div>
              <ul className="list-disc list-inside space-y-0.5 text-amber-300/80 pl-1">
                {result.limits.map((lim, i) => (
                  <li key={i}>{lim}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Causality Guardrail Notice */}
          <div className="flex items-center gap-2 p-3 rounded-lg bg-neutral-950/40 border border-neutral-800 text-xs text-neutral-400">
            <ShieldCheck className="w-4 h-4 text-emerald-400 shrink-0" />
            <span>
              <strong>Causality Guardrail Enforced:</strong> All claims are strictly verified against calculated evidence. Correlation is distinguished from causation.
            </span>
          </div>
        </div>
      )}
    </Card>
  );
}
