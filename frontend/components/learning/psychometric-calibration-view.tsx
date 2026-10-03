"use client";

import React from "react";
import {
  BrainCircuit,
  Compass,
  Sparkles,
  Target,
  Layers,
  ArrowRight,
  CheckCircle2,
  AlertCircle,
  HelpCircle,
  TrendingUp,
  Activity,
  Check,
  Flame,
} from "lucide-react";
import { Badge } from "@/components/ui";
import type {
  LearningEvidenceIndexDetail,
  LearnerTopicProgressionItem,
} from "@/types/learning";

interface PsychometricCalibrationViewProps {
  leiScore?: number | null;
  leiDetail?: LearningEvidenceIndexDetail | null;
  confidenceScore?: number | null;
  objectiveScore: number;
  confidenceGap?: number | null;
  calibrationQuadrant?: string | null;
  neutralRecommendation?: string | null;
  stageProgression?: LearnerTopicProgressionItem[];
}

const QUADRANTS = [
  {
    id: "blind_spot",
    title: "Blind Spot",
    subtitle: "High Subjective Confidence / Developing Objective Mastery",
    description: "Subjective confidence exceeds current objective assessment scores. Focus on precision checks and closing conceptual gaps.",
    borderActive: "border-amber-500/80 bg-gradient-to-br from-amber-500/15 via-slate-900 to-slate-900 shadow-amber-500/10",
    badgeVariant: "warning" as const,
  },
  {
    id: "calibrated_mastery",
    title: "Calibrated Mastery",
    subtitle: "High Subjective Confidence / High Objective Mastery",
    description: "Strong self-awareness and validated retention. Confidence is strongly substantiated by verified assessment evidence.",
    borderActive: "border-emerald-500/80 bg-gradient-to-br from-emerald-500/15 via-slate-900 to-slate-900 shadow-emerald-500/10",
    badgeVariant: "success" as const,
  },
  {
    id: "accurate_struggle",
    title: "Accurate Struggle",
    subtitle: "Developing Confidence / Developing Mastery",
    description: "Self-assessed difficulty aligns with objective challenges. Targeted concept reviews and scaffolding are recommended.",
    borderActive: "border-blue-500/80 bg-gradient-to-br from-blue-500/15 via-slate-900 to-slate-900 shadow-blue-500/10",
    badgeVariant: "secondary" as const,
  },
  {
    id: "underestimated_competence",
    title: "Underestimated Competence",
    subtitle: "Developing Confidence / High Objective Mastery",
    description: "Objective scores consistently outpace personal confidence ratings. You are performing significantly better than you estimate.",
    borderActive: "border-indigo-500/80 bg-gradient-to-br from-indigo-500/15 via-slate-900 to-slate-900 shadow-indigo-500/10",
    badgeVariant: "primary" as const,
  },
];

const STAGES_ORDER = [
  { key: "before_course", label: "1. Baseline Expectations", icon: "🌱" },
  { key: "during_course", label: "2. Cognitive Effort", icon: "⚡" },
  { key: "after_topic", label: "3. Topic Verification", icon: "📌" },
  { key: "after_video", label: "4. Video Understanding", icon: "🎥" },
  { key: "after_assessment", label: "5. Retention & Recall", icon: "📝" },
  { key: "end_of_module", label: "6. Module Autonomy", icon: "🏆" },
  { key: "end_of_course", label: "7. Application Readiness", icon: "🚀" },
];

export function PsychometricCalibrationView({
  leiScore,
  leiDetail,
  confidenceScore,
  objectiveScore,
  confidenceGap,
  calibrationQuadrant,
  neutralRecommendation,
  stageProgression = [],
}: PsychometricCalibrationViewProps) {
  const effConfidence = confidenceScore ?? 50.0;
  const effGap = confidenceGap ?? effConfidence - objectiveScore;
  const currentQuadrant = calibrationQuadrant || "calibrated_mastery";

  // Map stage progressions for easy lookup
  const progressionMap = new Map(stageProgression.map((p) => [p.stage, p]));

  return (
    <div className="space-y-6">
      {/* 1. Header Banner & LEI Summary */}
      <div className="relative overflow-hidden rounded-2xl border border-indigo-500/30 bg-gradient-to-r from-indigo-950/40 via-slate-900/90 to-purple-950/30 p-6 shadow-xl backdrop-blur-md">
        <div className="flex flex-col lg:flex-row items-start lg:items-center justify-between gap-6">
          <div className="space-y-2 max-w-2xl">
            <div className="flex items-center gap-2">
              <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
                <BrainCircuit className="h-3.5 w-3.5" />
                Psychometric Learning Calibration
              </span>
              <span className="text-xs text-slate-400 font-mono">Model v1.0.0</span>
            </div>
            <h2 className="text-xl font-bold tracking-tight text-white flex items-center gap-2">
              <span>Confidence & Evidence Calibration</span>
            </h2>
            <p className="text-xs text-slate-300 leading-relaxed">
              Synthesizes subjective self-assessment signals across 7 learning stages with objective performance data. Built on non-diagnostic, growth-oriented learning analytics.
            </p>
          </div>

          {/* LEI Metric Box */}
          <div className="flex items-center gap-4 bg-slate-950/60 border border-indigo-500/20 rounded-xl p-4 shadow-inner">
            <div className="space-y-1">
              <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                Learning Evidence Index (LEI)
              </div>
              <div className="flex items-baseline gap-2">
                <span className="text-3xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-indigo-400 to-purple-300">
                  {leiScore !== null && leiScore !== undefined ? leiScore.toFixed(1) : "—"}
                </span>
                <span className="text-xs text-slate-500">/ 100</span>
              </div>
              <div className="text-[10px] text-indigo-300/80">
                Balanced multi-construct index
              </div>
            </div>
          </div>
        </div>

        {/* Dynamic Weight Decomposition (LEI Breakdown) */}
        {leiDetail && (
          <div className="mt-5 pt-4 border-t border-slate-800/80 grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
            {Object.entries(leiDetail.components).map(([k, comp]) => {
              const label = k.replace(/_/g, " ").replace("evidence", "").trim();
              return (
                <div key={k} className="bg-slate-900/60 rounded-lg p-2.5 border border-slate-800 text-xs">
                  <div className="text-[10px] uppercase font-semibold text-slate-400 truncate">
                    {label}
                  </div>
                  <div className="flex items-baseline justify-between mt-1">
                    <span className="font-bold text-slate-200">{comp.raw_value.toFixed(1)}%</span>
                    <span className="text-[10px] text-slate-500">
                      w: {(comp.normalized_weight * 100).toFixed(0)}%
                    </span>
                  </div>
                  <div className="mt-1.5 h-1 rounded-full bg-slate-800 overflow-hidden">
                    <div
                      className="h-full bg-indigo-500 rounded-full transition-all duration-500"
                      style={{ width: `${Math.min(100, comp.raw_value)}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* 2. Calibration 2x2 Matrix & Gap Analysis */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left: 2x2 Matrix (7 cols) */}
        <div className="lg:col-span-7 rounded-2xl border border-slate-800 bg-slate-900/80 p-5 shadow-sm space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-sm font-semibold text-white flex items-center gap-2">
                <Compass className="h-4 w-4 text-indigo-400" />
                <span>Confidence-Performance Calibration Matrix</span>
              </h3>
              <p className="text-xs text-slate-400 mt-0.5">
                Maps self-assessed confidence against verified assessment scores.
              </p>
            </div>
            <div className="flex items-center gap-2 text-xs font-mono">
              <span className="text-slate-400">Δ Gap:</span>
              <span
                className={`font-bold px-2 py-0.5 rounded ${
                  effGap > 15
                    ? "bg-amber-500/20 text-amber-300"
                    : effGap < -15
                    ? "bg-indigo-500/20 text-indigo-300"
                    : "bg-emerald-500/20 text-emerald-300"
                }`}
              >
                {effGap > 0 ? `+${effGap.toFixed(1)}` : effGap.toFixed(1)}%
              </span>
            </div>
          </div>

          {/* 2x2 Grid */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2">
            {QUADRANTS.map((quad) => {
              const isSelected = currentQuadrant === quad.id;
              return (
                <div
                  key={quad.id}
                  className={`relative rounded-xl border p-4 transition-all duration-300 ${
                    isSelected
                      ? `${quad.borderActive} shadow-lg ring-1 ring-indigo-500/30 scale-[1.01]`
                      : "border-slate-800/80 bg-slate-950/40 opacity-70 hover:opacity-100"
                  }`}
                >
                  {isSelected && (
                    <div className="absolute top-3 right-3 flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-indigo-500/20 text-indigo-300 border border-indigo-500/40">
                      <Check className="h-3 w-3" />
                      Active
                    </div>
                  )}
                  <h4 className="text-xs font-bold text-slate-100">{quad.title}</h4>
                  <div className="text-[10px] text-slate-400 font-medium mt-0.5 mb-2">
                    {quad.subtitle}
                  </div>
                  <p className="text-[11px] text-slate-300 leading-relaxed">
                    {quad.description}
                  </p>
                </div>
              );
            })}
          </div>

          {/* Growth Recommendation Box */}
          {neutralRecommendation && (
            <div className="mt-4 rounded-xl border border-indigo-500/20 bg-indigo-950/20 p-3.5 flex items-start gap-3">
              <Sparkles className="h-4 w-4 text-indigo-400 shrink-0 mt-0.5" />
              <div className="text-xs text-indigo-200">
                <span className="font-semibold text-white">Learning Recommendation: </span>
                {neutralRecommendation}
              </div>
            </div>
          )}
        </div>

        {/* Right: Confidence vs Performance Balance Meter (5 cols) */}
        <div className="lg:col-span-5 rounded-2xl border border-slate-800 bg-slate-900/80 p-5 shadow-sm space-y-4 flex flex-col justify-between">
          <div>
            <h3 className="text-sm font-semibold text-white flex items-center gap-2">
              <Activity className="h-4 w-4 text-indigo-400" />
              <span>Alignment Metrics</span>
            </h3>
            <p className="text-xs text-slate-400 mt-0.5">
              Comparison of self-confidence and objective marks.
            </p>

            <div className="space-y-4 mt-5">
              {/* Confidence Bar */}
              <div>
                <div className="flex justify-between text-xs mb-1">
                  <span className="text-slate-300 font-medium">Average Confidence</span>
                  <span className="font-bold text-indigo-300">{effConfidence.toFixed(1)}%</span>
                </div>
                <div className="h-2 rounded-full bg-slate-800 overflow-hidden">
                  <div
                    className="h-full bg-gradient-to-r from-indigo-500 to-purple-500 rounded-full transition-all duration-500"
                    style={{ width: `${Math.min(100, Math.max(0, effConfidence))}%` }}
                  />
                </div>
              </div>

              {/* Performance Bar */}
              <div>
                <div className="flex justify-between text-xs mb-1">
                  <span className="text-slate-300 font-medium">Objective Performance</span>
                  <span className="font-bold text-emerald-300">{objectiveScore.toFixed(1)}%</span>
                </div>
                <div className="h-2 rounded-full bg-slate-800 overflow-hidden">
                  <div
                    className="h-full bg-gradient-to-r from-emerald-500 to-teal-400 rounded-full transition-all duration-500"
                    style={{ width: `${Math.min(100, Math.max(0, objectiveScore))}%` }}
                  />
                </div>
              </div>

              {/* Self-Awareness Alignment Score */}
              <div className="pt-3 border-t border-slate-800/80">
                <div className="flex justify-between text-xs mb-1">
                  <span className="text-slate-300 font-medium">Self-Awareness Index</span>
                  <span className="font-bold text-slate-200">
                    {Math.max(0, 100 - Math.abs(effGap) * 2).toFixed(1)}%
                  </span>
                </div>
                <div className="text-[10px] text-slate-500">
                  Measures closeness of subjective estimation to demonstrated capability.
                </div>
              </div>
            </div>
          </div>

          <div className="rounded-xl bg-slate-950/50 p-3 border border-slate-800 text-[11px] text-slate-400">
            💡 Educational Note: High self-awareness enables learners to study more efficiently, allocate revision time optimally, and avoid unverified assumptions.
          </div>
        </div>
      </div>

      {/* 3. 7-Stage Longitudinal Learning Journey Progression */}
      <div className="rounded-2xl border border-slate-800 bg-slate-900/80 p-5 shadow-sm space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
          <div>
            <h3 className="text-sm font-semibold text-white flex items-center gap-2">
              <Layers className="h-4 w-4 text-indigo-400" />
              <span>7-Stage Longitudinal Learning Journey</span>
            </h3>
            <p className="text-xs text-slate-400 mt-0.5">
              Tracks progression across all 7 contextual learning milestones.
            </p>
          </div>
          <span className="text-xs text-indigo-400 font-mono">
            {stageProgression.length} Signals Captured
          </span>
        </div>

        {/* Horizontal Timeline */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-7 gap-2.5 pt-2">
          {STAGES_ORDER.map((stage) => {
            const prog = progressionMap.get(stage.key);
            const isCompleted = prog?.status === "completed" || prog?.status === "active";
            const scoreVal = prog?.confidence_score ?? prog?.perceived_understanding;

            return (
              <div
                key={stage.key}
                className={`rounded-xl border p-3 flex flex-col justify-between transition-all ${
                  isCompleted
                    ? "border-indigo-500/40 bg-indigo-950/20 text-slate-200"
                    : "border-slate-800 bg-slate-950/40 text-slate-500"
                }`}
              >
                <div>
                  <div className="flex items-center justify-between gap-1 mb-1.5">
                    <span className="text-base">{stage.icon}</span>
                    {isCompleted ? (
                      <CheckCircle2 className="h-3.5 w-3.5 text-indigo-400" />
                    ) : (
                      <span className="h-2 w-2 rounded-full bg-slate-700" />
                    )}
                  </div>
                  <div className="text-[11px] font-bold tracking-tight line-clamp-1">
                    {stage.label}
                  </div>
                </div>

                <div className="mt-3 pt-2 border-t border-slate-800/60">
                  {scoreVal !== null && scoreVal !== undefined ? (
                    <div className="flex items-baseline justify-between">
                      <span className="text-[10px] text-slate-400">Score</span>
                      <span className="text-xs font-bold text-indigo-300">
                        {scoreVal.toFixed(0)}%
                      </span>
                    </div>
                  ) : (
                    <span className="text-[10px] text-slate-500 italic">
                      {isCompleted ? "Recorded" : "Upcoming"}
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
