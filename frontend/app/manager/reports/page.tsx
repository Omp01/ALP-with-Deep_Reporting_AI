"use client";

import React, { useState } from "react";
import {
  CalendarClock,
  Code2,
  Mail,
  Users,
  Target,
  RotateCcw,
  Award,
  AlertTriangle,
  ChevronRight,
  TrendingDown,
  Sparkles,
  Calculator,
  Search,
} from "lucide-react";

import { AppShell, PageHeader } from "@/components/shell";
import { Alert, Badge, Button, EmptyState, ErrorState, SkeletonText, useToast } from "@/components/ui";
import { useApi } from "@/hooks/use-api";
import { formatDateTime } from "@/lib/utils";
import { reportsService, type Audience } from "@/services/reports";
import { ManagerEffectivenessPanel } from "@/components/learning/manager-effectiveness-panel";
import type { ManagerCohortLearnerSummary } from "@/types/learning";

const ROLES = ["manager", "instructor", "org_admin", "system_admin"] as const;

export default function ReportsAndDigestsPage() {
  const { toast } = useToast();
  const [activeTab, setActiveTab] = useState<"performance" | "digests">("performance");
  const [searchTerm, setSearchTerm] = useState("");

  // APIs
  const digests = useApi((signal) => reportsService.digests(signal));
  const schedules = useApi((signal) => reportsService.schedules(signal));
  const cohortPerformance = useApi((signal) => reportsService.getManagerPerformance(undefined, signal));
  const effectiveness = useApi((signal) => reportsService.getManagerEffectiveness(undefined, signal));

  const [busy, setBusy] = useState(false);
  const [snippet, setSnippet] = useState<string | null>(null);

  const run = async () => {
    setBusy(true);
    try {
      const result = await reportsService.generateDigest();
      toast({
        title: result.status === "success" ? "Digest generated" : "The digest could not be generated",
        variant: result.status === "success" ? "success" : "error",
      });
      digests.refetch();
    } catch (err) {
      toast({
        title: "The digest could not be generated",
        description: err instanceof Error ? err.message : undefined,
        variant: "error",
      });
    } finally {
      setBusy(false);
    }
  };

  const schedule = async (audience: Audience, cadence: "weekly" | "monthly", title: string) => {
    try {
      await reportsService.createSchedule({ title, audience, cadence });
      toast({ title: "Scheduled", description: `${title} will be generated ${cadence}.`, variant: "success" });
      schedules.refetch();
    } catch (err) {
      toast({ title: "Could not schedule", description: err instanceof Error ? err.message : undefined, variant: "error" });
    }
  };

  const embed = async () => {
    try {
      setSnippet((await reportsService.embedToken({ report: "skill-gaps", scope: "team" })).snippet);
    } catch (err) {
      toast({ title: "Could not create an embed token", description: err instanceof Error ? err.message : undefined, variant: "error" });
    }
  };

  const cohortData = cohortPerformance.data;

  // Filter roster
  const filteredRoster = (cohortData?.learner_roster ?? []).filter((l) => {
    if (!searchTerm) return true;
    return (
      l.user_name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      (l.user_email && l.user_email.toLowerCase().includes(searchTerm.toLowerCase()))
    );
  });

  return (
    <AppShell roles={[...ROLES]}>
      <PageHeader
        title="Manager Reports & Cohort Assessment"
        description="Comprehensive team reporting: attempt-based scoring analytics, cohort accuracy, weak topics, and cited digests."
        actions={
          activeTab === "digests" ? (
            <Button onClick={run} disabled={busy} data-testid="generate-digest">
              {busy ? "Generating…" : "Generate weekly digest now"}
            </Button>
          ) : undefined
        }
      />

      {/* Primary Tab Switcher */}
      <div className="mb-6 flex items-center gap-2 border-b border-border pb-2">
        <button
          type="button"
          onClick={() => setActiveTab("performance")}
          className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors ${
            activeTab === "performance"
              ? "bg-primary text-primary-fg shadow-sm"
              : "text-fg-muted hover:text-fg hover:bg-surface-muted"
          }`}
        >
          <Target className="size-3.5" />
          <span>Cohort Assessment & Score Analytics</span>
        </button>
        <button
          type="button"
          onClick={() => setActiveTab("digests")}
          className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors ${
            activeTab === "digests"
              ? "bg-primary text-primary-fg shadow-sm"
              : "text-fg-muted hover:text-fg hover:bg-surface-muted"
          }`}
        >
          <Mail className="size-3.5" />
          <span>Scheduled Digests & BI</span>
        </button>
      </div>

      {activeTab === "performance" ? (
        <div className="space-y-8 animate-in fade-in duration-300">
          {cohortPerformance.loading ? (
            <div className="space-y-4">
              <SkeletonText lines={3} />
              <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                {[1, 2, 3, 4].map((i) => (
                  <div key={i} className="h-28 rounded-2xl bg-surface-muted animate-pulse" />
                ))}
              </div>
            </div>
          ) : cohortPerformance.error ? (
            <ErrorState error={cohortPerformance.error} onRetry={cohortPerformance.refetch} />
          ) : !cohortData ? (
            <EmptyState
              title="No cohort data available"
              description="Your assigned team members have not attempted assessments or checkpoints yet."
            />
          ) : (
            <>
              {/* Cohort KPI Cards */}
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                <div className="rounded-2xl border border-border bg-surface p-5 shadow-sm">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold uppercase tracking-wider text-fg-muted">
                      Cohort Size
                    </span>
                    <span className="flex size-8 items-center justify-center rounded-xl bg-primary/10 text-primary">
                      <Users className="size-4" />
                    </span>
                  </div>
                  <div className="mt-3 text-3xl font-bold tracking-tight text-fg">
                    {cohortData.cohort_size}
                  </div>
                  <p className="mt-2 text-[11px] text-fg-muted">Active assigned learners in scope</p>
                </div>

                <div className="rounded-2xl border border-border bg-surface p-5 shadow-sm">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold uppercase tracking-wider text-fg-muted">
                      Avg Overall Score
                    </span>
                    <span className="flex size-8 items-center justify-center rounded-xl bg-success/10 text-success">
                      <Award className="size-4" />
                    </span>
                  </div>
                  <div className="mt-3 text-3xl font-bold tracking-tight text-fg">
                    {cohortData.avg_overall_score}%
                  </div>
                  <p className="mt-2 text-[11px] text-fg-muted">Across quizzes, flashcards, & assignments</p>
                </div>

                <div className="rounded-2xl border border-border bg-surface p-5 shadow-sm">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold uppercase tracking-wider text-fg-muted">
                      1st-Attempt Accuracy
                    </span>
                    <span className="flex size-8 items-center justify-center rounded-xl bg-primary-100 text-primary dark:bg-primary-950">
                      <Target className="size-4" />
                    </span>
                  </div>
                  <div className="mt-3 text-3xl font-bold tracking-tight text-fg">
                    {cohortData.avg_first_attempt_accuracy}%
                  </div>
                  <p className="mt-2 text-[11px] text-fg-muted">Cohort-wide first-attempt pass rate</p>
                </div>

                <div className="rounded-2xl border border-border bg-surface p-5 shadow-sm">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold uppercase tracking-wider text-fg-muted">
                      Avg Attempts
                    </span>
                    <span className="flex size-8 items-center justify-center rounded-xl bg-warning/10 text-warning">
                      <RotateCcw className="size-4" />
                    </span>
                  </div>
                  <div className="mt-3 text-3xl font-bold tracking-tight text-fg">
                    {cohortData.avg_attempts_per_item}
                  </div>
                  <p className="mt-2 text-[11px] text-fg-muted">Average tries per question/flashcard</p>
                </div>
              </div>

              {/* Learners Requiring Attention & Cohort Weak Topics */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Learners Requiring Attention */}
                <div className="rounded-2xl border border-border bg-surface p-5 shadow-sm space-y-4">
                  <div className="flex items-center justify-between">
                    <h3 className="text-sm font-semibold text-fg flex items-center gap-2">
                      <AlertTriangle className="size-4 text-warning" />
                      <span>Learners Requiring Attention</span>
                    </h3>
                    <Badge variant="warning" size="sm">
                      {cohortData.learners_requiring_attention.length} Flagged
                    </Badge>
                  </div>
                  <p className="text-xs text-fg-muted">
                    Learners experiencing low first-attempt accuracy (&lt;70%) or high attempt counts (&gt;1.8x).
                  </p>

                  {cohortData.learners_requiring_attention.length === 0 ? (
                    <p className="text-xs text-fg-muted italic py-4 text-center">
                      All cohort learners are currently on track!
                    </p>
                  ) : (
                    <ul className="divide-y divide-border/60">
                      {cohortData.learners_requiring_attention.map((l) => (
                        <li key={l.user_id} className="py-2.5 flex items-center justify-between text-xs">
                          <div>
                            <span className="font-semibold text-fg">{l.user_name}</span>
                            <div className="flex items-center gap-2 text-[11px] text-fg-muted mt-0.5">
                              <span>1st Accuracy: {l.first_attempt_accuracy}%</span>
                              <span>·</span>
                              <span>Avg Tries: {l.average_attempts}</span>
                            </div>
                          </div>
                          <Badge
                            variant={l.status === "at_risk" ? "danger" : "warning"}
                            size="sm"
                            className="capitalize"
                          >
                            {l.status.replace("_", " ")}
                          </Badge>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>

                {/* Cohort Weak Topics */}
                <div className="rounded-2xl border border-border bg-surface p-5 shadow-sm space-y-4">
                  <div className="flex items-center justify-between">
                    <h3 className="text-sm font-semibold text-fg flex items-center gap-2">
                      <TrendingDown className="size-4 text-warning" />
                      <span>Cohort Weak Topics & Repeated Mistakes</span>
                    </h3>
                    <span className="text-xs text-fg-muted font-medium">
                      {cohortData.cohort_weak_topics.length} Concepts
                    </span>
                  </div>
                  <p className="text-xs text-fg-muted">
                    Topics where multiple team learners triggered multiple retries or low accuracy.
                  </p>

                  {cohortData.cohort_weak_topics.length === 0 ? (
                    <p className="text-xs text-fg-muted italic py-4 text-center">
                      No cohort-wide struggle topics identified.
                    </p>
                  ) : (
                    <ul className="divide-y divide-border/60">
                      {cohortData.cohort_weak_topics.map((wt, idx) => (
                        <li key={idx} className="py-2.5 flex items-center justify-between text-xs">
                          <span className="font-medium text-fg line-clamp-1">{wt.topic}</span>
                          <div className="flex items-center gap-3 shrink-0 text-[11px]">
                            <span className="text-warning font-semibold">
                              {wt.struggling_learner_count} learners
                            </span>
                            <span className="text-fg-muted">
                              Avg: {wt.avg_attempts} tries
                            </span>
                          </div>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </div>

              {/* Psychometric Effectiveness & Content Friction Insights */}
              <ManagerEffectivenessPanel
                report={effectiveness.data}
                loading={effectiveness.loading}
              />

              {/* Complete Learner Performance Roster */}
              <section className="rounded-2xl border border-border bg-surface p-6 shadow-sm space-y-4">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                  <div>
                    <h3 className="text-base font-semibold text-fg flex items-center gap-2">
                      <Users className="size-4 text-primary" />
                      <span>Learner Assessment Roster</span>
                    </h3>
                    <p className="text-xs text-fg-muted mt-0.5">
                      Individual accuracy, retry averages, and explainable scoring drill-down.
                    </p>
                  </div>

                  {/* Search box */}
                  <div className="relative">
                    <Search className="absolute left-2.5 top-2.5 size-3.5 text-fg-muted" />
                    <input
                      type="text"
                      placeholder="Filter by learner name..."
                      value={searchTerm}
                      onChange={(e) => setSearchTerm(e.target.value)}
                      className="rounded-lg border border-border bg-surface-muted/60 pl-8 pr-3 py-1.5 text-xs text-fg placeholder:text-fg-muted focus:outline-none focus:ring-1 focus:ring-primary w-56"
                    />
                  </div>
                </div>

                <div className="overflow-x-auto rounded-xl border border-border">
                  <table className="w-full text-left text-xs">
                    <thead className="border-b border-border bg-surface-muted/80 text-[11px] font-semibold text-fg-muted uppercase tracking-wider">
                      <tr>
                        <th className="px-4 py-3">Learner</th>
                        <th className="px-4 py-3">Overall Score</th>
                        <th className="px-4 py-3">1st Attempt Accuracy</th>
                        <th className="px-4 py-3">Avg Attempts</th>
                        <th className="px-4 py-3">Items Completed</th>
                        <th className="px-4 py-3">Status</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border/60">
                      {filteredRoster.map((l) => (
                        <tr key={l.user_id} className="hover:bg-surface-muted/30 transition-colors">
                          <td className="px-4 py-3 font-medium text-fg">
                            <div>{l.user_name}</div>
                            {l.user_email && (
                              <div className="text-[10px] text-fg-muted">{l.user_email}</div>
                            )}
                          </td>
                          <td className="px-4 py-3 font-semibold text-fg">{l.overall_score}%</td>
                          <td className="px-4 py-3 text-fg">{l.first_attempt_accuracy}%</td>
                          <td className="px-4 py-3 text-fg">{l.average_attempts}</td>
                          <td className="px-4 py-3 text-fg-muted">{l.items_completed}</td>
                          <td className="px-4 py-3">
                            <Badge
                              variant={
                                l.status === "on_track"
                                  ? "success"
                                  : l.status === "at_risk"
                                  ? "danger"
                                  : "warning"
                              }
                              size="sm"
                              className="capitalize"
                            >
                              {l.status.replace("_", " ")}
                            </Badge>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            </>
          )}
        </div>
      ) : (
        /* Digests & Scheduled Reports Tab (Preserved original features) */
        <div className="space-y-8 animate-in fade-in duration-300">
          <Alert variant="info">
            <Mail className="mr-1 inline size-4" aria-hidden="true" /> Digests are stored and shown here. No email is sent: no mail server is configured.
          </Alert>

          <section aria-labelledby="digests-title">
            <h2 id="digests-title" className="mb-3 text-base font-semibold text-fg">
              Latest digests
            </h2>
            {digests.loading ? (
              <SkeletonText lines={4} />
            ) : digests.error ? (
              <ErrorState error={digests.error} onRetry={digests.refetch} />
            ) : (digests.data?.items ?? []).length === 0 ? (
              <EmptyState title="No digests yet" description="Generate one now, or schedule a weekly digest below." />
            ) : (
              <ul className="space-y-3">
                {(digests.data?.items ?? []).map((d) => (
                  <li key={d.id} className="rounded-lg border border-border p-4" data-digest-id={d.id}>
                    <div className="flex flex-wrap items-center gap-2 text-xs text-fg-muted">
                      <Badge variant={d.status === "success" ? "success" : "danger"} size="sm">
                        {d.status}
                      </Badge>
                      <span>{formatDateTime(d.generated_at)}</span>
                      <span>· {d.audience}</span>
                    </div>
                    <pre className="mt-2 whitespace-pre-wrap font-sans text-sm text-fg">{d.content}</pre>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section aria-labelledby="schedules-title">
            <h2 id="schedules-title" className="mb-3 flex items-center gap-2 text-base font-semibold text-fg">
              <CalendarClock className="size-4" aria-hidden="true" /> Schedules
            </h2>
            <div className="mb-3 flex flex-wrap gap-2">
              <Button variant="secondary" size="sm" onClick={() => schedule("team", "weekly", "Weekly team digest")}>
                Schedule weekly team digest
              </Button>
              <Button variant="secondary" size="sm" onClick={() => schedule("ld", "weekly", "Weekly L&D digest")}>
                Schedule weekly L&amp;D digest
              </Button>
              <Button variant="secondary" size="sm" onClick={() => schedule("organization", "monthly", "Monthly organization capability report")}>
                Schedule monthly organization report
              </Button>
            </div>
            {(schedules.data?.items ?? []).length > 0 && (
              <ul className="space-y-1 text-sm text-fg-muted">
                {(schedules.data?.items ?? []).map((s) => (
                  <li key={s.id}>
                    {s.title} ({s.cadence}) · next {s.next_run_at ? formatDateTime(s.next_run_at) : "—"}
                  </li>
                ))}
              </ul>
            )}
            <p className="mt-2 text-xs text-fg-muted">You can only schedule reports you are allowed to ask for; the roles that may do so are the same as for the insight pages.</p>
          </section>

          <section aria-labelledby="embed-title">
            <h2 id="embed-title" className="mb-3 flex items-center gap-2 text-base font-semibold text-fg">
              <Code2 className="size-4" aria-hidden="true" /> Embed skill gaps in another page
            </h2>
            <Button variant="secondary" size="sm" onClick={embed}>
              Create an embed snippet
            </Button>
            {snippet && (
              <pre className="mt-3 overflow-x-auto rounded-lg bg-surface-raised p-3 text-xs" data-testid="embed-snippet">
                {snippet}
              </pre>
            )}
            <p className="mt-2 text-xs text-fg-muted">The token is scoped to your team&apos;s skill gaps, expires, and works only for this widget.</p>
          </section>
        </div>
      )}
    </AppShell>
  );
}
