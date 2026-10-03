"use client";

import React, { useEffect, useState } from "react";
import {
  Activity,
  AlertCircle,
  AlertTriangle,
  ArrowDownRight,
  ArrowRight,
  ArrowUpRight,
  Award,
  BookOpen,
  CheckCircle2,
  ChevronRight,
  Clock,
  FileText,
  Filter,
  HelpCircle,
  Layers,
  RefreshCw,
  Search,
  ShieldAlert,
  Sparkles,
  TrendingDown,
  TrendingUp,
  UserCheck,
  Users,
  X,
} from "lucide-react";

import {
  Alert,
  Badge,
  Button,
  Card,
  Dialog,
  EmptyState,
  ErrorState,
  Skeleton,
} from "@/components/ui";
import { apiClient } from "@/lib/api-client";
import {
  analyticsService,
  AssessmentIntelligenceResponse,
  BottleneckModule,
  BottlenecksResponse,
  QuestionIntelligenceItem,
  SilentStrugglerItem,
  SilentStrugglersResponse,
  WhatChangedResponse,
} from "@/services/analytics";
import { EvidenceExplorer } from "./evidence-explorer";
import { InvestigationPanel } from "./investigation-panel";
import { FlowchartReportPanel } from "./flowchart-report-panel";

interface TeamOption {
  id: string;
  name: string;
  member_count: number;
}

interface CourseOption {
  id: string;
  title: string;
}

export function LearningIntelligenceCenter() {
  // --- Filter State ---
  const [days, setDays] = useState<number>(14);
  const [selectedTeamId, setSelectedTeamId] = useState<string>("");
  const [selectedCourseId, setSelectedCourseId] = useState<string>("");

  // --- Evidence Explorer State ---
  const [explorerEvidenceId, setExplorerEvidenceId] = useState<string | null>(null);
  const [explorerClaimContext, setExplorerClaimContext] = useState<{
    statement?: string;
    category?: string;
  } | undefined>(undefined);

  // --- Dropdown Options ---
  const [teams, setTeams] = useState<TeamOption[]>([]);
  const [courses, setCourses] = useState<CourseOption[]>([]);

  // --- Data States ---
  const [whatChanged, setWhatChanged] = useState<WhatChangedResponse | null>(null);
  const [silentStrugglers, setSilentStrugglers] = useState<SilentStrugglersResponse | null>(null);
  const [bottlenecks, setBottlenecks] = useState<BottlenecksResponse | null>(null);
  const [assessmentIntel, setAssessmentIntel] = useState<AssessmentIntelligenceResponse | null>(null);

  // --- Loading & Error States ---
  const [loadingWhatChanged, setLoadingWhatChanged] = useState(true);
  const [loadingStrugglers, setLoadingStrugglers] = useState(true);
  const [loadingBottlenecks, setLoadingBottlenecks] = useState(true);
  const [loadingAssessment, setLoadingAssessment] = useState(true);

  const [errorWhatChanged, setErrorWhatChanged] = useState<string | null>(null);
  const [errorStrugglers, setErrorStrugglers] = useState<string | null>(null);
  const [errorBottlenecks, setErrorBottlenecks] = useState<string | null>(null);
  const [errorAssessment, setErrorAssessment] = useState<string | null>(null);

  // --- Detail Drawer / Modal State ---
  const [selectedDetail, setSelectedDetail] = useState<{
    title: string;
    type: "what_changed" | "struggler" | "bottleneck" | "question";
    data: any;
  } | null>(null);

  // --- 1. Load Filter Options (Teams & Courses) ---
  useEffect(() => {
    async function loadOptions() {
      try {
        const [tList, cList] = await Promise.all([
          apiClient.get<TeamOption[]>("/api/v1/teams").catch(() => []),
          apiClient.get<CourseOption[]>("/api/v1/courses").catch(() => []),
        ]);
        setTeams(tList);
        setCourses(cList);
        if (tList.length > 0 && !selectedTeamId) {
          setSelectedTeamId(tList[0].id);
        }
      } catch (err) {
        console.error("Failed to load filter options", err);
      }
    }
    loadOptions();
  }, []);

  // --- 2. Fetch Deterministic Analytics ---
  const fetchAllAnalytics = async () => {
    const teamParam = selectedTeamId || undefined;
    const courseParam = selectedCourseId || undefined;

    // What Changed
    setLoadingWhatChanged(true);
    setErrorWhatChanged(null);
    analyticsService
      .getWhatChanged({ days, team_id: teamParam, course_id: courseParam })
      .then((res) => setWhatChanged(res))
      .catch((err) => setErrorWhatChanged(err.message || "Failed to load What Changed analytics"))
      .finally(() => setLoadingWhatChanged(false));

    // Silent Strugglers
    setLoadingStrugglers(true);
    setErrorStrugglers(null);
    analyticsService
      .getSilentStrugglers({ team_id: teamParam })
      .then((res) => setSilentStrugglers(res))
      .catch((err) => setErrorStrugglers(err.message || "Failed to load Silent Struggler signals"))
      .finally(() => setLoadingStrugglers(false));

    // Bottlenecks
    setLoadingBottlenecks(true);
    setErrorBottlenecks(null);
    analyticsService
      .getBottlenecks({ team_id: teamParam, course_id: courseParam })
      .then((res) => setBottlenecks(res))
      .catch((err) => setErrorBottlenecks(err.message || "Failed to load Learning Bottlenecks"))
      .finally(() => setLoadingBottlenecks(false));

    // Assessment Intelligence
    setLoadingAssessment(true);
    setErrorAssessment(null);
    analyticsService
      .getAssessmentIntelligence({ team_id: teamParam, course_id: courseParam })
      .then((res) => setAssessmentIntel(res))
      .catch((err) => setErrorAssessment(err.message || "Failed to load Assessment Intelligence"))
      .finally(() => setLoadingAssessment(false));
  };

  useEffect(() => {
    fetchAllAnalytics();
  }, [days, selectedTeamId, selectedCourseId]);

  // Scroll helper for summary cards
  const scrollToSection = (id: string) => {
    const el = document.getElementById(id);
    if (el) el.scrollIntoView({ behavior: "smooth" });
  };

  return (
    <div className="space-y-8">
      {/* SECTION A — HEADER & FILTERS */}
      <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-xs">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6">
          <div>
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-indigo-50 text-indigo-700 text-xs font-semibold mb-2 border border-indigo-200">
              <Sparkles className="w-3.5 h-3.5 text-indigo-600" />
              Learning Intelligence Center
            </div>
            <h1 className="text-2xl font-bold text-slate-900 tracking-tight">
              Learning Intelligence
            </h1>
            <p className="text-sm text-slate-500 mt-1">
              Understand what is changing across your team's learning and competency development.
            </p>
          </div>

          {/* Filter Bar */}
          <div className="flex flex-wrap items-center gap-3">
            {/* Days Window */}
            <div className="flex items-center gap-1.5 bg-slate-50 border border-slate-200 rounded-xl px-3 py-1.5 text-xs font-medium text-slate-700">
              <Clock className="w-3.5 h-3.5 text-slate-400" />
              <span>Period:</span>
              <select
                value={days}
                onChange={(e) => setDays(Number(e.target.value))}
                className="bg-transparent font-semibold text-indigo-600 focus:outline-hidden"
              >
                <option value={7}>Last 7 Days</option>
                <option value={14}>Last 14 Days</option>
                <option value={30}>Last 30 Days</option>
                <option value={90}>Last 90 Days</option>
              </select>
            </div>

            {/* Team Filter */}
            {teams.length > 0 && (
              <div className="flex items-center gap-1.5 bg-slate-50 border border-slate-200 rounded-xl px-3 py-1.5 text-xs font-medium text-slate-700">
                <Users className="w-3.5 h-3.5 text-slate-400" />
                <select
                  value={selectedTeamId}
                  onChange={(e) => setSelectedTeamId(e.target.value)}
                  className="bg-transparent font-semibold text-slate-900 focus:outline-hidden"
                >
                  <option value="">All Remit Teams</option>
                  {teams.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.name} ({t.member_count})
                    </option>
                  ))}
                </select>
              </div>
            )}

            {/* Course Filter */}
            {courses.length > 0 && (
              <div className="flex items-center gap-1.5 bg-slate-50 border border-slate-200 rounded-xl px-3 py-1.5 text-xs font-medium text-slate-700">
                <BookOpen className="w-3.5 h-3.5 text-slate-400" />
                <select
                  value={selectedCourseId}
                  onChange={(e) => setSelectedCourseId(e.target.value)}
                  className="bg-transparent font-semibold text-slate-900 focus:outline-hidden"
                >
                  <option value="">All Courses</option>
                  {courses.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.title}
                    </option>
                  ))}
                </select>
              </div>
            )}

            {/* Refresh Button */}
            <Button
              variant="outline"
              size="sm"
              onClick={fetchAllAnalytics}
              className="gap-1.5 text-xs"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              Refresh
            </Button>
          </div>
        </div>
      </div>

      {/* SECTION A.1 — AI INVESTIGATION MODE */}
      <InvestigationPanel
        teamId={selectedTeamId || undefined}
        courseId={selectedCourseId || undefined}
        onOpenEvidence={(eid) => {
          setExplorerEvidenceId(eid);
          setExplorerClaimContext({ statement: "Investigation Evidence Citation" });
        }}
      />

      {/* SECTION A.2 — FLOWCHART BI REPORTS */}
      <FlowchartReportPanel
        teamId={selectedTeamId || undefined}
        courseId={selectedCourseId || undefined}
        onOpenEvidence={(eid) => {
          setExplorerEvidenceId(eid);
          setExplorerClaimContext({ statement: "Flowchart Evidence Citation" });
        }}
      />

      {/* SECTION B — WHAT CHANGED? */}
      <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-xs space-y-4">
        <div className="flex items-center justify-between pb-3 border-b border-slate-100">
          <div className="flex items-center gap-2">
            <Activity className="w-5 h-5 text-indigo-600" />
            <div>
              <h2 className="text-lg font-bold text-slate-900">What Changed?</h2>
              <p className="text-xs text-slate-500">
                Deterministic period-over-period comparison across mastery, assessment, and activity.
              </p>
            </div>
          </div>
        </div>

        {loadingWhatChanged ? (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <Skeleton className="h-28 rounded-xl" />
            <Skeleton className="h-28 rounded-xl" />
            <Skeleton className="h-28 rounded-xl" />
          </div>
        ) : errorWhatChanged ? (
          <ErrorState error={errorWhatChanged} onRetry={fetchAllAnalytics} />
        ) : !whatChanged ? (
          <EmptyState title="No period data" description="Insufficient telemetry to compute temporal changes." />
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {/* 1. Competency Mastery Movement */}
            <div
              onClick={() =>
                setSelectedDetail({
                  title: "Competency Mastery Movement",
                  type: "what_changed",
                  data: whatChanged.competency,
                })
              }
              className="p-4 rounded-xl border border-slate-200 bg-slate-50/50 hover:bg-white hover:border-indigo-300 transition-all cursor-pointer shadow-2xs"
            >
              <div className="flex items-center justify-between text-xs font-semibold text-slate-400 mb-2">
                <span>Competency Mastery</span>
                <Award className="w-4 h-4 text-indigo-500" />
              </div>
              <div className="flex items-baseline gap-2">
                <span className="text-2xl font-bold text-slate-900">
                  {whatChanged.competency.current_avg_mastery !== null
                    ? `${(whatChanged.competency.current_avg_mastery * 100).toFixed(1)}%`
                    : "—"}
                </span>
                <span className="text-xs text-slate-500">
                  from{" "}
                  {whatChanged.competency.previous_avg_mastery !== null
                    ? `${(whatChanged.competency.previous_avg_mastery * 100).toFixed(1)}%`
                    : "—"}
                </span>
              </div>
              <div className="mt-2 flex items-center justify-between text-xs">
                {whatChanged.competency.mastery_delta !== null ? (
                  <span
                    className={`font-semibold inline-flex items-center gap-0.5 ${
                      whatChanged.competency.mastery_delta >= 0
                        ? "text-emerald-600"
                        : "text-red-600"
                    }`}
                  >
                    {whatChanged.competency.mastery_delta >= 0 ? (
                      <TrendingUp className="w-3.5 h-3.5" />
                    ) : (
                      <TrendingDown className="w-3.5 h-3.5" />
                    )}
                    {whatChanged.competency.mastery_delta > 0 ? "+" : ""}
                    {(whatChanged.competency.mastery_delta * 100).toFixed(1)}%
                  </span>
                ) : (
                  <span className="text-slate-400">No delta</span>
                )}
                <span className="text-[11px] text-indigo-600 hover:underline">
                  {whatChanged.competency.updates_count_current} updates →
                </span>
              </div>
            </div>

            {/* 2. Assessment Performance */}
            <div
              onClick={() =>
                setSelectedDetail({
                  title: "Assessment Accuracy & Volume",
                  type: "what_changed",
                  data: whatChanged.assessment,
                })
              }
              className="p-4 rounded-xl border border-slate-200 bg-slate-50/50 hover:bg-white hover:border-indigo-300 transition-all cursor-pointer shadow-2xs"
            >
              <div className="flex items-center justify-between text-xs font-semibold text-slate-400 mb-2">
                <span>Assessment Accuracy</span>
                <CheckCircle2 className="w-4 h-4 text-emerald-500" />
              </div>
              <div className="flex items-baseline gap-2">
                <span className="text-2xl font-bold text-slate-900">
                  {whatChanged.assessment.current_accuracy_rate !== null
                    ? `${(whatChanged.assessment.current_accuracy_rate * 100).toFixed(1)}%`
                    : "—"}
                </span>
                <span className="text-xs text-slate-500">
                  from{" "}
                  {whatChanged.assessment.previous_accuracy_rate !== null
                    ? `${(whatChanged.assessment.previous_accuracy_rate * 100).toFixed(1)}%`
                    : "—"}
                </span>
              </div>
              <div className="mt-2 flex items-center justify-between text-xs">
                {whatChanged.assessment.accuracy_delta !== null ? (
                  <span
                    className={`font-semibold inline-flex items-center gap-0.5 ${
                      whatChanged.assessment.accuracy_delta >= 0
                        ? "text-emerald-600"
                        : "text-red-600"
                    }`}
                  >
                    {whatChanged.assessment.accuracy_delta >= 0 ? (
                      <TrendingUp className="w-3.5 h-3.5" />
                    ) : (
                      <TrendingDown className="w-3.5 h-3.5" />
                    )}
                    {whatChanged.assessment.accuracy_delta > 0 ? "+" : ""}
                    {(whatChanged.assessment.accuracy_delta * 100).toFixed(1)}%
                  </span>
                ) : (
                  <span className="text-slate-400">No delta</span>
                )}
                <span className="text-[11px] text-slate-500">
                  {whatChanged.assessment.current_attempt_volume} attempts
                </span>
              </div>
            </div>

            {/* 3. Learning Activity Count */}
            <div
              onClick={() =>
                setSelectedDetail({
                  title: "Learning Telemetry Events",
                  type: "what_changed",
                  data: whatChanged.activity,
                })
              }
              className="p-4 rounded-xl border border-slate-200 bg-slate-50/50 hover:bg-white hover:border-indigo-300 transition-all cursor-pointer shadow-2xs"
            >
              <div className="flex items-center justify-between text-xs font-semibold text-slate-400 mb-2">
                <span>Learning Activity Telemetry</span>
                <Activity className="w-4 h-4 text-blue-500" />
              </div>
              <div className="flex items-baseline gap-2">
                <span className="text-2xl font-bold text-slate-900">
                  {whatChanged.activity.current_event_count}
                </span>
                <span className="text-xs text-slate-500">events recorded</span>
              </div>
              <div className="mt-2 flex items-center justify-between text-xs">
                <span
                  className={`font-semibold inline-flex items-center gap-0.5 ${
                    whatChanged.activity.event_count_delta >= 0
                      ? "text-emerald-600"
                      : "text-amber-600"
                  }`}
                >
                  {whatChanged.activity.event_count_delta >= 0 ? "+" : ""}
                  {whatChanged.activity.event_count_delta} vs prev period
                </span>
                <span className="text-[11px] text-slate-400">Telemetry logs</span>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* SECTION C — WHAT NEEDS ATTENTION? */}
      <div className="space-y-4">
        <h2 className="text-lg font-bold text-slate-900 flex items-center gap-2">
          <AlertCircle className="w-5 h-5 text-amber-500" />
          What Needs Attention?
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {/* Card 1: Silent Strugglers */}
          <div
            onClick={() => scrollToSection("silent-strugglers-section")}
            className="p-5 bg-white border border-slate-200 hover:border-amber-400 rounded-2xl shadow-2xs transition-all cursor-pointer group"
          >
            <div className="flex items-center justify-between text-slate-400 mb-3">
              <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                Silent Strugglers
              </span>
              <ShieldAlert className="w-5 h-5 text-amber-500 group-hover:scale-110 transition-transform" />
            </div>
            <div className="text-3xl font-bold text-slate-900">
              {loadingStrugglers ? "—" : silentStrugglers?.total_strugglers_found ?? 0}
            </div>
            <div className="text-xs text-amber-700 font-medium mt-2 flex items-center justify-between">
              <span>High completion / low mastery</span>
              <ArrowRight className="w-3.5 h-3.5 group-hover:translate-x-1 transition-transform" />
            </div>
          </div>

          {/* Card 2: Skill Risk */}
          <div
            onClick={() => scrollToSection("competency-risk-section")}
            className="p-5 bg-white border border-slate-200 hover:border-red-400 rounded-2xl shadow-2xs transition-all cursor-pointer group"
          >
            <div className="flex items-center justify-between text-slate-400 mb-3">
              <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                Skill Risk Radar
              </span>
              <AlertTriangle className="w-5 h-5 text-red-500 group-hover:scale-110 transition-transform" />
            </div>
            <div className="text-3xl font-bold text-red-600">
              {loadingWhatChanged
                ? "—"
                : whatChanged?.competency.mastery_delta !== null &&
                  whatChanged?.competency.mastery_delta! < 0
                ? "Risk Detected"
                : "Monitored"}
            </div>
            <div className="text-xs text-red-700 font-medium mt-2 flex items-center justify-between">
              <span>Competency mastery deficits</span>
              <ArrowRight className="w-3.5 h-3.5 group-hover:translate-x-1 transition-transform" />
            </div>
          </div>

          {/* Card 3: Bottlenecks */}
          <div
            onClick={() => scrollToSection("bottlenecks-section")}
            className="p-5 bg-white border border-slate-200 hover:border-indigo-400 rounded-2xl shadow-2xs transition-all cursor-pointer group"
          >
            <div className="flex items-center justify-between text-slate-400 mb-3">
              <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                Learning Bottlenecks
              </span>
              <Layers className="w-5 h-5 text-indigo-500 group-hover:scale-110 transition-transform" />
            </div>
            <div className="text-3xl font-bold text-indigo-900">
              {loadingBottlenecks ? "—" : bottlenecks?.bottlenecks_detected ?? 0}
            </div>
            <div className="text-xs text-indigo-700 font-medium mt-2 flex items-center justify-between">
              <span>Modules with path friction</span>
              <ArrowRight className="w-3.5 h-3.5 group-hover:translate-x-1 transition-transform" />
            </div>
          </div>

          {/* Card 4: Assessment Signals */}
          <div
            onClick={() => scrollToSection("assessment-intelligence-section")}
            className="p-5 bg-white border border-slate-200 hover:border-emerald-400 rounded-2xl shadow-2xs transition-all cursor-pointer group"
          >
            <div className="flex items-center justify-between text-slate-400 mb-3">
              <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                Assessment Signals
              </span>
              <HelpCircle className="w-5 h-5 text-emerald-500 group-hover:scale-110 transition-transform" />
            </div>
            <div className="text-3xl font-bold text-slate-900">
              {loadingAssessment ? "—" : assessmentIntel?.total_questions_analyzed ?? 0}
            </div>
            <div className="text-xs text-slate-500 font-medium mt-2 flex items-center justify-between">
              <span>Questions with high error signal</span>
              <ArrowRight className="w-3.5 h-3.5 group-hover:translate-x-1 transition-transform" />
            </div>
          </div>
        </div>
      </div>

      {/* SECTION D — SILENT STRUGGLERS */}
      <div id="silent-strugglers-section" className="bg-white border border-slate-200 rounded-2xl p-6 shadow-xs space-y-4">
        <div className="flex items-center justify-between pb-3 border-b border-slate-100">
          <div className="flex items-center gap-2">
            <ShieldAlert className="w-5 h-5 text-amber-500" />
            <div>
              <h2 className="text-lg font-bold text-slate-900">Silent Struggler Detection</h2>
              <p className="text-xs text-slate-500">
                Learners progressing normally according to completion/activity but demonstrating weak Bayesian mastery.
              </p>
            </div>
          </div>
          <span className="text-xs font-semibold px-2.5 py-1 bg-amber-50 text-amber-800 border border-amber-200 rounded-full">
            Threshold: Progress ≥ 70% & Mastery &lt; 55%
          </span>
        </div>

        {loadingStrugglers ? (
          <Skeleton className="h-40 rounded-xl" />
        ) : errorStrugglers ? (
          <ErrorState error={errorStrugglers} onRetry={fetchAllAnalytics} />
        ) : !silentStrugglers || silentStrugglers.silent_strugglers.length === 0 ? (
          <div className="text-center py-8 bg-emerald-50/50 rounded-xl border border-emerald-100">
            <CheckCircle2 className="w-8 h-8 text-emerald-600 mx-auto mb-2" />
            <h3 className="text-sm font-semibold text-emerald-900">No Silent Strugglers Detected</h3>
            <p className="text-xs text-emerald-700 mt-1">
              All learners with high course completion demonstrate corresponding competency mastery.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="bg-slate-50 text-slate-500 uppercase text-[11px] font-semibold border-b border-slate-200">
                <tr>
                  <th className="px-4 py-3">Learner</th>
                  <th className="px-4 py-3 text-right">Completion</th>
                  <th className="px-4 py-3 text-right">Mastery</th>
                  <th className="px-4 py-3">Key Deficit</th>
                  <th className="px-4 py-3">Diagnostic Reason</th>
                  <th className="px-4 py-3 text-center">Evidence</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {silentStrugglers.silent_strugglers.map((item) => (
                  <tr
                    key={item.user_id}
                    onClick={() =>
                      setSelectedDetail({
                        title: `Silent Struggler: ${item.learner_name}`,
                        type: "struggler",
                        data: item,
                      })
                    }
                    className="hover:bg-slate-50/70 cursor-pointer transition-colors"
                  >
                    <td className="px-4 py-3 font-semibold text-slate-900">
                      {item.learner_name}
                      <span className="block text-[11px] font-normal text-slate-400">
                        Risk Level: {item.risk_level}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right font-mono font-semibold text-slate-700">
                      {item.completion_percent.toFixed(1)}%
                    </td>
                    <td className="px-4 py-3 text-right font-mono font-bold text-amber-600">
                      {(item.mastery_score * 100).toFixed(1)}%
                    </td>
                    <td className="px-4 py-3 text-xs text-slate-700">
                      {item.competencies.length > 0 ? (
                        <span className="px-2 py-0.5 rounded bg-amber-50 text-amber-800 border border-amber-200 font-medium">
                          {item.competencies[0].competency}
                        </span>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td className="px-4 py-3 text-xs text-slate-600 max-w-xs">
                      {item.reasons[0] || "Completion is high but mastery lags."}
                    </td>
                    <td className="px-4 py-3 text-center">
                      <div className="flex flex-wrap items-center justify-center gap-1">
                        {item.evidence_ids.length > 0 ? (
                          item.evidence_ids.map((id) => (
                            <button
                              key={id}
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation();
                                setExplorerEvidenceId(id);
                                setExplorerClaimContext({
                                  statement: `Silent Struggler: ${item.learner_name}`,
                                  category: "Silent Struggler Signal",
                                });
                              }}
                              className="text-[11px] font-mono text-indigo-700 bg-indigo-50 hover:bg-indigo-100 border border-indigo-200 px-2 py-0.5 rounded font-semibold transition-colors cursor-pointer"
                            >
                              [E-{id.replace(/^evidence_/, "").slice(0, 6).toUpperCase()}]
                            </button>
                          ))
                        ) : (
                          <span className="text-xs text-slate-400">No Evidence</span>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* SECTION E — LEARNING BOTTLENECKS */}
      <div id="bottlenecks-section" className="bg-white border border-slate-200 rounded-2xl p-6 shadow-xs space-y-4">
        <div className="flex items-center justify-between pb-3 border-b border-slate-100">
          <div className="flex items-center gap-2">
            <Layers className="w-5 h-5 text-indigo-600" />
            <div>
              <h2 className="text-lg font-bold text-slate-900">Learning Path Friction & Bottlenecks</h2>
              <p className="text-xs text-slate-500">
                Points in the learning path where learners systematically struggle or encounter retry friction.
              </p>
            </div>
          </div>
        </div>

        {loadingBottlenecks ? (
          <Skeleton className="h-40 rounded-xl" />
        ) : errorBottlenecks ? (
          <ErrorState error={errorBottlenecks} onRetry={fetchAllAnalytics} />
        ) : !bottlenecks || bottlenecks.modules.length === 0 ? (
          <EmptyState title="No Bottlenecks Detected" description="All module learning paths show normal progression." />
        ) : (
          <div className="space-y-3">
            {bottlenecks.modules.map((mod) => (
              <div
                key={mod.module_id}
                onClick={() =>
                  setSelectedDetail({
                    title: `Module Bottleneck: ${mod.module_title}`,
                    type: "bottleneck",
                    data: mod,
                  })
                }
                className={`p-4 rounded-xl border transition-all cursor-pointer ${
                  mod.is_bottleneck
                    ? "bg-amber-50/40 border-amber-200 hover:border-amber-400"
                    : "bg-slate-50/40 border-slate-200 hover:border-slate-300"
                }`}
              >
                <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                  <div>
                    <div className="flex items-center gap-2">
                      <h3 className="font-bold text-slate-900 text-sm">{mod.module_title}</h3>
                      {mod.is_bottleneck ? (
                        <span className="px-2 py-0.5 rounded-full text-[10px] font-bold uppercase bg-amber-100 text-amber-800 border border-amber-300">
                          Bottleneck Flag
                        </span>
                      ) : (
                        <span className="px-2 py-0.5 rounded-full text-[10px] font-bold uppercase bg-slate-100 text-slate-700">
                          Normal Path
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-slate-500 mt-0.5">Course: {mod.course_title}</p>
                  </div>

                  <div className="flex items-center gap-6 text-xs">
                    <div>
                      <span className="text-slate-400 block text-[10px]">Exposed Learners</span>
                      <span className="font-bold text-slate-800">{mod.affected_learners}</span>
                    </div>
                    <div>
                      <span className="text-slate-400 block text-[10px]">Completion</span>
                      <span className="font-bold text-slate-800">
                        {(mod.completion_rate * 100).toFixed(0)}%
                      </span>
                    </div>
                    <div>
                      <span className="text-slate-400 block text-[10px]">Quiz Correctness</span>
                      <span className="font-bold text-slate-800">
                        {(mod.correctness_rate * 100).toFixed(0)}%
                      </span>
                    </div>
                    <div>
                      <span className="text-slate-400 block text-[10px]">Retry Rate</span>
                      <span className="font-bold text-slate-800">
                        {(mod.retry_rate * 100).toFixed(0)}%
                      </span>
                    </div>
                  </div>
                </div>

                {/* Signals & Evidence Pills */}
                <div className="mt-3 pt-3 border-t border-slate-200/60 flex flex-wrap items-center justify-between gap-2">
                  <div className="flex flex-wrap items-center gap-1.5">
                    {mod.signals.map((sig, i) => (
                      <span
                        key={i}
                        className="px-2 py-0.5 rounded text-[11px] font-medium bg-white border border-slate-200 text-slate-700 shadow-2xs"
                      >
                        {sig}
                      </span>
                    ))}
                    {mod.evidence_ids.map((id) => (
                      <button
                        key={id}
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          setExplorerEvidenceId(id);
                          setExplorerClaimContext({
                            statement: `Module Bottleneck: ${mod.module_title}`,
                            category: "Learning Path Friction Signal",
                          });
                        }}
                        className="text-[11px] font-mono text-indigo-700 bg-indigo-50 hover:bg-indigo-100 border border-indigo-200 px-2 py-0.5 rounded font-semibold transition-colors cursor-pointer"
                      >
                        [E-{id.replace(/^evidence_/, "").slice(0, 6).toUpperCase()}]
                      </button>
                    ))}
                  </div>
                  <span className="text-[11px] font-semibold text-indigo-600 hover:underline">
                    View Module Telemetry →
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* SECTION F — ASSESSMENT INTELLIGENCE */}
      <div id="assessment-intelligence-section" className="bg-white border border-slate-200 rounded-2xl p-6 shadow-xs space-y-4">
        <div className="flex items-center justify-between pb-3 border-b border-slate-100">
          <div className="flex items-center gap-2">
            <HelpCircle className="w-5 h-5 text-indigo-600" />
            <div>
              <h2 className="text-lg font-bold text-slate-900">Assessment Question Intelligence</h2>
              <p className="text-xs text-slate-500">
                Factual question-level performance, response accuracy, and attempt retry counts.
              </p>
            </div>
          </div>
        </div>

        {loadingAssessment ? (
          <Skeleton className="h-40 rounded-xl" />
        ) : errorAssessment ? (
          <ErrorState error={errorAssessment} onRetry={fetchAllAnalytics} />
        ) : !assessmentIntel || assessmentIntel.questions.length === 0 ? (
          <EmptyState title="No Assessment Signals" description="No question attempt records are available for this filter scope." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="bg-slate-50 text-slate-500 uppercase text-[11px] font-semibold border-b border-slate-200">
                <tr>
                  <th className="px-4 py-3">Question</th>
                  <th className="px-4 py-3">Quiz</th>
                  <th className="px-4 py-3 text-right">Responses</th>
                  <th className="px-4 py-3 text-right">Accuracy Rate</th>
                  <th className="px-4 py-3 text-right">Avg Attempt</th>
                  <th className="px-4 py-3 text-right">Avg Time</th>
                  <th className="px-4 py-3 text-center">Signal</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {assessmentIntel.questions.map((q) => (
                  <tr
                    key={q.question_id}
                    onClick={() =>
                      setSelectedDetail({
                        title: `Question Analysis: ${q.question_text.slice(0, 50)}...`,
                        type: "question",
                        data: q,
                      })
                    }
                    className="hover:bg-slate-50/70 cursor-pointer transition-colors"
                  >
                    <td className="px-4 py-3 font-medium text-slate-900 max-w-sm truncate">
                      {q.question_text}
                    </td>
                    <td className="px-4 py-3 text-xs text-slate-600">{q.quiz_title}</td>
                    <td className="px-4 py-3 text-right font-mono font-semibold text-slate-700">
                      {q.total_responses}
                    </td>
                    <td className="px-4 py-3 text-right font-mono font-bold">
                      <span
                        className={
                          q.correctness_rate < 0.50
                            ? "text-red-600"
                            : q.correctness_rate < 0.70
                            ? "text-amber-600"
                            : "text-emerald-600"
                        }
                      >
                        {(q.correctness_rate * 100).toFixed(1)}%
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-xs text-slate-600">
                      {q.average_attempt_number.toFixed(1)}
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-xs text-slate-600">
                      {q.average_time_seconds.toFixed(0)}s
                    </td>
                    <td className="px-4 py-3 text-center">
                      {q.correctness_rate < 0.50 ? (
                        <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-red-100 text-red-800 border border-red-200">
                          High Error
                        </span>
                      ) : q.average_attempt_number > 1.5 ? (
                        <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-100 text-amber-800 border border-amber-200">
                          High Retry
                        </span>
                      ) : (
                        <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-100 text-emerald-800 border border-emerald-200">
                          Normal
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* DETAIL DIALOG / MODAL */}
      <Dialog
        open={selectedDetail !== null}
        onClose={() => setSelectedDetail(null)}
        title={selectedDetail?.title || "Analytics Detail"}
        size="lg"
      >
        {selectedDetail && (
          <div className="space-y-4">
            <div className="p-4 bg-slate-50 rounded-xl border border-slate-200 font-mono text-xs text-slate-800 overflow-x-auto max-h-96">
              <pre>{JSON.stringify(selectedDetail.data, null, 2)}</pre>
            </div>
            <div className="flex justify-end gap-2 pt-3 border-t border-slate-200">
              <Button variant="outline" size="sm" onClick={() => setSelectedDetail(null)}>
                Close
              </Button>
            </div>
          </div>
        )}
      </Dialog>

      {/* EVIDENCE EXPLORER DRAWER */}
      <EvidenceExplorer
        evidenceId={explorerEvidenceId}
        onClose={() => setExplorerEvidenceId(null)}
        claimContext={explorerClaimContext}
      />
    </div>
  );
}
