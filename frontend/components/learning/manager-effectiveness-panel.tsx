"use client";

import React from "react";
import {
  BrainCircuit,
  Compass,
  AlertTriangle,
  CheckCircle2,
  Flame,
  Activity,
  Sparkles,
  Info,
  TrendingDown,
} from "lucide-react";
import { Badge } from "@/components/ui";
import type { ManagerPsychometricsEffectivenessReport } from "@/types/learning";

interface ManagerEffectivenessPanelProps {
  report?: ManagerPsychometricsEffectivenessReport | null;
  loading?: boolean;
}

export function ManagerEffectivenessPanel({
  report,
  loading = false,
}: ManagerEffectivenessPanelProps) {
  if (loading) {
    return (
      <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-6 animate-pulse space-y-4">
        <div className="h-6 w-1/3 bg-slate-800 rounded" />
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="h-24 bg-slate-800/60 rounded-xl" />
          ))}
        </div>
      </div>
    );
  }

  if (!report) {
    return null;
  }

  const dist = report.cohort_calibration_distribution || {};
  const totalCalibrated = Object.values(dist).reduce((a, b) => a + b, 0);
  const getPct = (count: number) =>
    totalCalibrated > 0 ? ((count / totalCalibrated) * 100).toFixed(0) : "0";

  const flaggedTopics = report.flagged_friction_topics || [];

  return (
    <div className="space-y-6">
      {/* 1. Header & Calibration Distribution */}
      <section className="rounded-2xl border border-indigo-500/30 bg-gradient-to-br from-indigo-950/30 via-slate-900/90 to-slate-900 p-6 shadow-xl backdrop-blur-md space-y-5">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
                <BrainCircuit className="h-3.5 w-3.5" />
                Psychometric Effectiveness Insights
              </span>
              <span className="text-[11px] text-slate-400 font-mono">Framework v1.0</span>
            </div>
            <h3 className="text-base font-bold text-white flex items-center gap-2">
              <span>Cohort Self-Calibration & Friction Analysis</span>
            </h3>
            <p className="text-xs text-slate-300 mt-0.5">
              Assesses cohort self-awareness calibration and flags curricular friction where mental effort significantly outpaces understanding.
            </p>
          </div>

          {/* Quick Cohort Summary stats */}
          <div className="flex items-center gap-3 shrink-0">
            <div className="bg-slate-950/60 border border-slate-800 rounded-xl px-3 py-2 text-right">
              <div className="text-[10px] uppercase font-semibold text-slate-400">Cohort Avg LEI</div>
              <div className="text-lg font-bold text-indigo-300">
                {report.avg_cohort_lei > 0 ? `${report.avg_cohort_lei.toFixed(1)}%` : "—"}
              </div>
            </div>
            <div className="bg-slate-950/60 border border-slate-800 rounded-xl px-3 py-2 text-right">
              <div className="text-[10px] uppercase font-semibold text-slate-400">Avg Confidence</div>
              <div className="text-lg font-bold text-emerald-300">
                {report.avg_cohort_confidence > 0 ? `${report.avg_cohort_confidence.toFixed(1)}%` : "—"}
              </div>
            </div>
          </div>
        </div>

        {/* Calibration Quadrant Breakdown Cards */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3.5 pt-1">
          {/* Calibrated Mastery */}
          <div className="rounded-xl border border-emerald-500/30 bg-emerald-950/20 p-4 relative overflow-hidden">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-emerald-300">Calibrated Mastery</span>
              <CheckCircle2 className="h-4 w-4 text-emerald-400" />
            </div>
            <div className="mt-2 flex items-baseline gap-2">
              <span className="text-2xl font-black text-white">{dist.calibrated_mastery || 0}</span>
              <span className="text-xs text-emerald-400/80">({getPct(dist.calibrated_mastery || 0)}%)</span>
            </div>
            <p className="mt-1 text-[11px] text-slate-300">
              High confidence validated by high objective mastery.
            </p>
          </div>

          {/* Blind Spot */}
          <div className="rounded-xl border border-amber-500/30 bg-amber-950/20 p-4 relative overflow-hidden">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-amber-300">Blind Spot (Overconfident)</span>
              <AlertTriangle className="h-4 w-4 text-amber-400" />
            </div>
            <div className="mt-2 flex items-baseline gap-2">
              <span className="text-2xl font-black text-white">{dist.blind_spot || 0}</span>
              <span className="text-xs text-amber-400/80">({getPct(dist.blind_spot || 0)}%)</span>
            </div>
            <p className="mt-1 text-[11px] text-slate-300">
              High confidence but lower objective scores. Assign precision quizzes.
            </p>
          </div>

          {/* Underestimated Competence */}
          <div className="rounded-xl border border-indigo-500/30 bg-indigo-950/20 p-4 relative overflow-hidden">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-indigo-300">Underestimated Competence</span>
              <Sparkles className="h-4 w-4 text-indigo-400" />
            </div>
            <div className="mt-2 flex items-baseline gap-2">
              <span className="text-2xl font-black text-white">{dist.underestimated_competence || 0}</span>
              <span className="text-xs text-indigo-400/80">({getPct(dist.underestimated_competence || 0)}%)</span>
            </div>
            <p className="mt-1 text-[11px] text-slate-300">
              High objective accuracy despite cautious self-assessments.
            </p>
          </div>

          {/* Accurate Struggle */}
          <div className="rounded-xl border border-blue-500/30 bg-blue-950/20 p-4 relative overflow-hidden">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-blue-300">Accurate Struggle</span>
              <Info className="h-4 w-4 text-blue-400" />
            </div>
            <div className="mt-2 flex items-baseline gap-2">
              <span className="text-2xl font-black text-white">{dist.accurate_struggle || 0}</span>
              <span className="text-xs text-blue-400/80">({getPct(dist.accurate_struggle || 0)}%)</span>
            </div>
            <p className="mt-1 text-[11px] text-slate-300">
              Self-aware of difficulty. Recommend targeted video remediation.
            </p>
          </div>
        </div>
      </section>

      {/* 2. Content Friction Index (CFI) Flags */}
      <section className="rounded-2xl border border-border bg-surface p-6 shadow-sm space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
          <div>
            <h3 className="text-base font-semibold text-fg flex items-center gap-2">
              <Flame className="size-4 text-orange-500" />
              <span>Content Friction Hotspots (CFI &gt; 70)</span>
            </h3>
            <p className="text-xs text-fg-muted mt-0.5">
              Identifies curriculum topics where high cognitive effort coincides with low understanding and elevated assessment retries.
            </p>
          </div>
          <Badge variant={flaggedTopics.length > 0 ? "warning" : "success"} size="sm">
            {flaggedTopics.length > 0 ? `${flaggedTopics.length} Hotspots Flagged` : "Zero Friction Hotspots"}
          </Badge>
        </div>

        {flaggedTopics.length === 0 ? (
          <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/5 p-4 flex items-center gap-3">
            <CheckCircle2 className="h-5 w-5 text-emerald-500 shrink-0" />
            <div className="text-xs text-fg">
              <span className="font-semibold text-emerald-600 dark:text-emerald-400">Curriculum Pacing Well-Balanced: </span>
              No topics in this cohort exceed the 70-point Content Friction threshold. Learner mental effort is manageable and well-aligned with retention.
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-1">
            {flaggedTopics.map((topicItem, idx) => (
              <div
                key={idx}
                className="rounded-xl border border-orange-500/30 bg-orange-950/10 p-4 space-y-3"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-semibold text-xs text-fg line-clamp-1">
                    {topicItem.topic || "Curriculum Unit"}
                  </span>
                  <span className="px-2 py-0.5 rounded-full text-xs font-bold bg-orange-500/20 text-orange-400 border border-orange-500/30 font-mono">
                    CFI: {topicItem.content_friction_index.toFixed(1)}
                  </span>
                </div>

                <div className="grid grid-cols-2 gap-2 text-[11px] bg-surface/60 rounded-lg p-2.5 border border-border/60">
                  <div>
                    <span className="text-fg-muted">Mental Effort:</span>{" "}
                    <span className="font-semibold text-fg">
                      {topicItem.breakdown.avg_effort?.toFixed(0)}%
                    </span>
                  </div>
                  <div>
                    <span className="text-fg-muted">Understanding:</span>{" "}
                    <span className="font-semibold text-fg">
                      {topicItem.breakdown.avg_understanding?.toFixed(0)}%
                    </span>
                  </div>
                  <div>
                    <span className="text-fg-muted">Error Rate:</span>{" "}
                    <span className="font-semibold text-fg">
                      {topicItem.breakdown.error_rate?.toFixed(0)}%
                    </span>
                  </div>
                  <div>
                    <span className="text-fg-muted">Retry Penalty:</span>{" "}
                    <span className="font-semibold text-fg">
                      {topicItem.breakdown.retry_penalty?.toFixed(0)}
                    </span>
                  </div>
                </div>

                <div className="text-[11px] text-fg-muted flex items-start gap-1.5">
                  <Info className="h-3.5 w-3.5 text-orange-400 shrink-0 mt-0.5" />
                  <span>
                    Suggested remediation: Review video pacing, insert a scaffolding checkpoint, or add supplementary code examples.
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
