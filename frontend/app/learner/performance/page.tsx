"use client";

import React, { useState } from "react";
import Link from "next/link";
import {
  TrendingUp,
  Award,
  Sparkles,
  RotateCcw,
  Target,
  PlayCircle,
  Calculator,
  ChevronDown,
  ChevronUp,
  HelpCircle,
  Filter,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  ArrowRight,
} from "lucide-react";

import { AppShell, PageHeader } from "@/components/shell";
import { Badge, Button, EmptyState, ErrorState, SkeletonText } from "@/components/ui";
import { useApi } from "@/hooks/use-api";
import { reportsService } from "@/services/reports";
import { PsychometricCalibrationView } from "@/components/learning/psychometric-calibration-view";
import type { QuestionAttemptDetail, TopicMasteryItem } from "@/types/learning";

const ROLES = ["learner", "manager", "instructor", "org_admin", "system_admin"] as const;

export default function LearnerPerformancePage() {
  const [filterType, setFilterType] = useState<string>("all");
  const [expandedItemId, setExpandedItemId] = useState<string | null>(null);

  const report = useApi((signal) => reportsService.getLearnerPerformance(undefined, signal));
  const calibration = useApi((signal) => reportsService.getLearnerCalibration(undefined, signal));

  const data = report.data;

  // Filter attempt history
  const filteredHistory = (data?.attempt_history ?? []).filter((item) => {
    if (filterType === "all") return true;
    return item.assessment_type === filterType;
  });

  const toggleExpand = (id: string) => {
    setExpandedItemId((prev) => (prev === id ? null : id));
  };

  return (
    <AppShell roles={[...ROLES]}>
      <PageHeader
        title="Performance & Score Transparency"
        description="Comprehensive attempt-decay scoring, mathematically explainable marks, and video-traceable remediation."
      />

      {report.loading ? (
        <div className="space-y-6">
          <SkeletonText lines={4} />
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="h-28 rounded-2xl bg-surface-muted animate-pulse" />
            ))}
          </div>
        </div>
      ) : report.error ? (
        <ErrorState error={report.error} onRetry={report.refetch} />
      ) : !data ? (
        <EmptyState
          title="No assessment records yet"
          description="Watch interactive video lessons, answer AI flashcards, and complete quizzes to generate your score report."
        />
      ) : (
        <div className="space-y-8 animate-in fade-in duration-300 pb-12">
          {/* Top Hero KPI Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {/* Overall Score */}
            <div className="relative overflow-hidden rounded-2xl border border-border bg-gradient-to-br from-primary/10 via-surface to-surface p-5 shadow-sm">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold uppercase tracking-wider text-fg-muted">
                  Overall Score
                </span>
                <span className="flex size-8 items-center justify-center rounded-xl bg-primary/20 text-primary">
                  <Award className="size-4" />
                </span>
              </div>
              <div className="mt-3 flex items-baseline gap-2">
                <span className="text-3xl font-bold tracking-tight text-fg">
                  {data.overall_score}%
                </span>
                <Badge variant={data.overall_score >= 75 ? "success" : "warning"} size="sm">
                  {data.improvement_trend}
                </Badge>
              </div>
              <p className="mt-2 text-[11px] text-fg-muted">
                Weighted: Quiz (40%), Assign (40%), Flashcards (20%)
              </p>
            </div>

            {/* First-Attempt Accuracy */}
            <div className="rounded-2xl border border-border bg-surface p-5 shadow-sm">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold uppercase tracking-wider text-fg-muted">
                  First-Attempt Accuracy
                </span>
                <span className="flex size-8 items-center justify-center rounded-xl bg-success/10 text-success">
                  <Target className="size-4" />
                </span>
              </div>
              <div className="mt-3 flex items-baseline gap-2">
                <span className="text-3xl font-bold tracking-tight text-fg">
                  {data.first_attempt_accuracy}%
                </span>
              </div>
              <p className="mt-2 text-[11px] text-fg-muted">
                Questions answered correctly without prior retries
              </p>
            </div>

            {/* Average Attempts */}
            <div className="rounded-2xl border border-border bg-surface p-5 shadow-sm">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold uppercase tracking-wider text-fg-muted">
                  Average Attempts
                </span>
                <span className="flex size-8 items-center justify-center rounded-xl bg-warning/10 text-warning">
                  <RotateCcw className="size-4" />
                </span>
              </div>
              <div className="mt-3 flex items-baseline gap-2">
                <span className="text-3xl font-bold tracking-tight text-fg">
                  {data.average_attempts}
                </span>
                <span className="text-xs text-fg-muted">tries / item</span>
              </div>
              <p className="mt-2 text-[11px] text-fg-muted">
                {data.questions_requiring_retries} questions required retries
              </p>
            </div>

            {/* AI Flashcard Mastery Score */}
            <div className="rounded-2xl border border-border bg-surface p-5 shadow-sm">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold uppercase tracking-wider text-fg-muted">
                  Flashcard Score
                </span>
                <span className="flex size-8 items-center justify-center rounded-xl bg-primary-100 text-primary dark:bg-primary-950">
                  <Sparkles className="size-4" />
                </span>
              </div>
              <div className="mt-3 flex items-baseline gap-2">
                <span className="text-3xl font-bold tracking-tight text-fg">
                  {data.flashcard_score !== null && data.flashcard_score !== undefined
                    ? `${data.flashcard_score}%`
                    : "N/A"}
                </span>
              </div>
              <p className="mt-2 text-[11px] text-fg-muted">
                Attempt-decay formula applied (fewer tries = higher marks)
              </p>
            </div>
          </div>

          {/* Psychometric Calibration, LEI, and 7-Stage Longitudinal Journey */}
          <PsychometricCalibrationView
            leiScore={data.lei_score}
            leiDetail={data.lei_detail}
            confidenceScore={data.confidence_score}
            objectiveScore={data.overall_score}
            confidenceGap={data.confidence_gap}
            calibrationQuadrant={data.calibration_quadrant}
            neutralRecommendation={data.neutral_recommendation}
            stageProgression={calibration.data?.stage_progression ?? []}
          />

          {/* Topic Mastery Section */}
          <section className="rounded-2xl border border-border bg-surface p-6 shadow-sm space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
              <div>
                <h2 className="text-base font-semibold text-fg flex items-center gap-2">
                  <Target className="size-4 text-primary" />
                  <span>Topic Mastery & Conceptual Strengths</span>
                </h2>
                <p className="text-xs text-fg-muted mt-0.5">
                  Concept breakdown derived directly from your flashcard comprehension checks and quizzes.
                </p>
              </div>

              {/* Badges for Quick Glance */}
              <div className="flex flex-wrap items-center gap-2">
                {data.strong_topics.length > 0 && (
                  <Badge variant="success" size="sm">
                    {data.strong_topics.length} Strong Topics
                  </Badge>
                )}
                {data.weak_topics.length > 0 && (
                  <Badge variant="warning" size="sm">
                    {data.weak_topics.length} Topics for Review
                  </Badge>
                )}
              </div>
            </div>

            {data.topic_mastery.length === 0 ? (
              <p className="text-xs text-fg-muted italic py-4 text-center">
                Answer interactive video checkpoints to populate your topic mastery map.
              </p>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3.5 pt-2">
                {data.topic_mastery.map((tm, idx) => (
                  <div
                    key={idx}
                    className="rounded-xl border border-border/80 bg-surface-muted/40 p-3.5 hover:border-primary/40 transition-colors"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-medium text-xs text-fg line-clamp-1">
                        {tm.topic}
                      </span>
                      <Badge
                        variant={
                          tm.status === "strong"
                            ? "success"
                            : tm.status === "weak"
                            ? "warning"
                            : "neutral"
                        }
                        size="sm"
                        className="capitalize"
                      >
                        {tm.status}
                      </Badge>
                    </div>

                    <div className="mt-3 flex items-center justify-between text-xs">
                      <span className="text-fg-muted">Mastery</span>
                      <span className="font-semibold text-fg">{tm.mastery_percent}%</span>
                    </div>

                    {/* Progress Bar */}
                    <div className="mt-1.5 h-1.5 w-full rounded-full bg-border/60 overflow-hidden">
                      <div
                        className={`h-full rounded-full ${
                          tm.status === "strong"
                            ? "bg-success"
                            : tm.status === "weak"
                            ? "bg-warning"
                            : "bg-primary"
                        }`}
                        style={{ width: `${tm.mastery_percent}%` }}
                      />
                    </div>

                    <div className="mt-2.5 flex items-center justify-between text-[11px] text-fg-muted">
                      <span>{tm.correct_count} / {tm.total_questions} questions correct</span>
                      <span>Avg: {tm.average_attempts} tries</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>

          {/* Question & Flashcard Drill-Down Table */}
          <section className="rounded-2xl border border-border bg-surface p-6 shadow-sm space-y-5">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div>
                <h2 className="text-base font-semibold text-fg flex items-center gap-2">
                  <Calculator className="size-4 text-primary" />
                  <span>Item Drill-Down & Mathematical Score Transparency</span>
                </h2>
                <p className="text-xs text-fg-muted mt-0.5">
                  Expand any item to inspect its exact calculation snapshot, formula expression, and video review link.
                </p>
              </div>

              {/* Filter tabs */}
              <div className="flex items-center gap-1.5 rounded-xl border border-border bg-surface-muted/60 p-1 text-xs">
                <button
                  type="button"
                  onClick={() => setFilterType("all")}
                  className={`px-3 py-1 rounded-lg font-medium transition-colors ${
                    filterType === "all"
                      ? "bg-surface text-fg shadow-sm"
                      : "text-fg-muted hover:text-fg"
                  }`}
                >
                  All ({data.attempt_history.length})
                </button>
                <button
                  type="button"
                  onClick={() => setFilterType("flashcard")}
                  className={`px-3 py-1 rounded-lg font-medium transition-colors ${
                    filterType === "flashcard"
                      ? "bg-surface text-fg shadow-sm"
                      : "text-fg-muted hover:text-fg"
                  }`}
                >
                  Flashcards
                </button>
                <button
                  type="button"
                  onClick={() => setFilterType("quiz")}
                  className={`px-3 py-1 rounded-lg font-medium transition-colors ${
                    filterType === "quiz"
                      ? "bg-surface text-fg shadow-sm"
                      : "text-fg-muted hover:text-fg"
                  }`}
                >
                  Quizzes
                </button>
              </div>
            </div>

            {filteredHistory.length === 0 ? (
              <p className="text-xs text-fg-muted italic py-6 text-center">
                No items match the selected filter.
              </p>
            ) : (
              <div className="divide-y divide-border/60 overflow-hidden rounded-xl border border-border">
                {filteredHistory.map((item) => {
                  const isExpanded = expandedItemId === item.id;
                  const hasCalc = !!item.calculation_details;
                  const hasRemediation = !!item.remediation;

                  return (
                    <div key={item.id} className="transition-colors hover:bg-surface-muted/20">
                      {/* Main row */}
                      <div
                        onClick={() => toggleExpand(item.id)}
                        className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-4 cursor-pointer select-none"
                      >
                        <div className="flex items-start gap-3 min-w-0 flex-1">
                          <span className="mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-lg bg-surface-muted border border-border text-fg-muted">
                            {item.first_attempt_correct ? (
                              <CheckCircle2 className="size-3.5 text-success" />
                            ) : (
                              <XCircle className="size-3.5 text-warning" />
                            )}
                          </span>

                          <div className="min-w-0 space-y-1">
                            <div className="flex flex-wrap items-center gap-2">
                              <span className="text-xs font-semibold text-fg line-clamp-1">
                                {item.title}
                              </span>
                              <Badge variant="neutral" size="sm" className="capitalize text-[10px]">
                                {item.assessment_type}
                              </Badge>
                              {item.topic && (
                                <span className="text-[10px] text-fg-muted px-1.5 py-0.5 rounded bg-surface-muted border border-border/60">
                                  {item.topic}
                                </span>
                              )}
                            </div>

                            <div className="flex items-center gap-3 text-[11px] text-fg-muted">
                              <span>
                                {item.attempts === 1
                                  ? "1st Attempt Success"
                                  : `${item.attempts} attempts taken`}
                              </span>
                              <span>·</span>
                              <span>Score: {item.score} / {item.max_score} pts</span>
                            </div>
                          </div>
                        </div>

                        <div className="flex items-center gap-3 shrink-0 self-end sm:self-center">
                          <span className="font-semibold text-xs text-fg">
                            {Math.round((item.score / (item.max_score || 1)) * 100)}%
                          </span>
                          <button
                            type="button"
                            className="flex items-center gap-1 text-[11px] font-medium text-primary hover:underline"
                          >
                            <span>Calculation Details</span>
                            {isExpanded ? (
                              <ChevronUp className="size-3.5" />
                            ) : (
                              <ChevronDown className="size-3.5" />
                            )}
                          </button>
                        </div>
                      </div>

                      {/* Expandable Explanation & Video Remediation */}
                      {isExpanded && (
                        <div className="px-4 pb-4 pt-1 bg-surface-muted/40 border-t border-border/40 text-xs space-y-3 animate-in fade-in duration-150">
                          {/* Mathematical Audit Snapshot */}
                          {hasCalc && (
                            <div className="rounded-xl border border-border/80 bg-surface p-3 space-y-2">
                              <div className="flex items-center justify-between text-xs font-semibold text-fg">
                                <span className="flex items-center gap-1.5">
                                  <Calculator className="size-3.5 text-primary" />
                                  <span>Mathematical Formula Snapshot</span>
                                </span>
                                <Badge variant="neutral" size="sm" className="font-mono text-[10px]">
                                  {item.calculation_details?.formula_id || "attempt_decay_v1"}
                                </Badge>
                              </div>

                              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-1 font-mono text-[11px]">
                                <div className="rounded bg-surface-muted p-2 border border-border/60">
                                  <span className="text-fg-muted text-[10px] block">Max Marks:</span>
                                  <span className="font-semibold text-fg">
                                    {item.calculation_details?.max_marks ?? item.max_score}
                                  </span>
                                </div>
                                <div className="rounded bg-surface-muted p-2 border border-border/60">
                                  <span className="text-fg-muted text-[10px] block">Attempt Count:</span>
                                  <span className="font-semibold text-fg">
                                    {item.calculation_details?.attempt_number ?? item.attempts}
                                  </span>
                                </div>
                                <div className="rounded bg-surface-muted p-2 border border-border/60">
                                  <span className="text-fg-muted text-[10px] block">Retry Penalty (P):</span>
                                  <span className="font-semibold text-fg">
                                    {item.calculation_details?.penalty_p ?? 0.25}
                                  </span>
                                </div>
                                <div className="rounded bg-surface-muted p-2 border border-border/60">
                                  <span className="text-fg-muted text-[10px] block">Score Awarded:</span>
                                  <span className="font-semibold text-success">
                                    {item.score} / {item.max_score}
                                  </span>
                                </div>
                              </div>

                              {item.calculation_details?.formula_expression && (
                                <div className="rounded bg-surface-muted/60 p-2 font-mono text-[11px] text-fg border border-border/40">
                                  <span className="text-fg-muted text-[10px] block">Formula Expression:</span>
                                  {item.calculation_details.formula_expression}
                                </div>
                              )}

                              {item.calculation_details?.reason && (
                                <p className="text-[11px] text-fg-muted italic">
                                  {item.calculation_details.reason}
                                </p>
                              )}
                            </div>
                          )}

                          {/* Video-Traceable Remediation Section */}
                          {hasRemediation && item.remediation && (
                            <div className="rounded-xl border border-primary/20 bg-primary/5 p-3 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
                              <div className="space-y-1">
                                <div className="flex items-center gap-2 font-semibold text-xs text-primary">
                                  <PlayCircle className="size-4" />
                                  <span>Review Topic: {item.remediation.topic}</span>
                                </div>
                                <p className="text-[11px] text-fg-muted">
                                  Video Section: <strong className="text-fg">{item.remediation.section_label}</strong> · {item.remediation.video_title}
                                </p>
                                {item.remediation.explanation && (
                                  <p className="text-[11px] text-fg-muted italic">
                                    &ldquo;{item.remediation.explanation}&rdquo;
                                  </p>
                                )}
                              </div>

                              <Link
                                href={item.remediation.action_url || `/learner/learning?item_id=${item.remediation.content_item_id}`}
                                className="shrink-0 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-primary text-primary-fg text-xs font-medium shadow-sm hover:opacity-90 transition-opacity"
                              >
                                <span>Watch Video Section</span>
                                <ArrowRight className="size-3" />
                              </Link>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </section>
        </div>
      )}
    </AppShell>
  );
}
