"use client";

import React, { useState, useMemo } from "react";
import Link from "next/link";
import {
  HelpCircle,
  CheckCircle2,
  AlertTriangle,
  Clock,
  ArrowRight,
  RotateCcw,
  Sparkles,
  Award,
  Layers,
  Search,
} from "lucide-react";

import { AppShell, PageHeader } from "@/components/shell";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
  CardFooter,
  Badge,
  Button,
  Progress,
  Input,
  Stat,
  StatGrid,
  Skeleton,
  EmptyState,
  ErrorState,
} from "@/components/ui";
import { apiClient } from "@/lib/api-client";
import { useApi } from "@/hooks/use-api";

interface LearnerQuizItem {
  quiz_id: string;
  content_item_id: string | null;
  course_id: string;
  course_title: string;
  module_id?: string | null;
  module_title?: string | null;
  title: string;
  passing_score: number;
  time_limit_mins: number;
  questions_count: number;
  is_adaptive: boolean;
  attempts_count: number;
  best_score: number | null;
  passed: boolean;
  last_attempt_at?: string | null;
}

export default function LearnerAssessmentsPage() {
  const [searchQuery, setSearchQuery] = useState("");
  const [filterTab, setFilterTab] = useState<"all" | "passed" | "retake" | "unattempted">("all");

  const { data: quizzes, loading, error, refetch } = useApi<LearnerQuizItem[]>(
    (signal) => apiClient.get<LearnerQuizItem[]>("/api/v1/quizzes/learner/summary", { signal })
  );

  // Stats calculation
  const stats = useMemo(() => {
    if (!quizzes) return { total: 0, passed: 0, avgScore: 0, pending: 0 };
    const total = quizzes.length;
    const passed = quizzes.filter((q) => q.passed).length;
    const completedWithScore = quizzes.filter((q) => q.best_score !== null);
    const avgScore =
      completedWithScore.length > 0
        ? Math.round(
            completedWithScore.reduce((acc, q) => acc + (q.best_score || 0), 0) /
              completedWithScore.length
          )
        : 0;
    const pending = quizzes.filter((q) => q.attempts_count === 0).length;
    return { total, passed, avgScore, pending };
  }, [quizzes]);

  // Filtered quizzes
  const filteredQuizzes = useMemo(() => {
    if (!quizzes) return [];
    return quizzes.filter((q) => {
      // Search
      const matchesSearch =
        q.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
        q.course_title.toLowerCase().includes(searchQuery.toLowerCase());
      if (!matchesSearch) return false;

      // Filter tab
      if (filterTab === "passed") return q.passed;
      if (filterTab === "retake") return q.attempts_count > 0 && !q.passed;
      if (filterTab === "unattempted") return q.attempts_count === 0;
      return true;
    });
  }, [quizzes, searchQuery, filterTab]);

  return (
    <AppShell roles={["learner", "instructor", "org_admin", "system_admin"]}>
      <div className="space-y-6">
        {/* Header */}
        <PageHeader
          title="Assessments & Knowledge Checks"
          description="Evaluate your competency mastery, review attempt histories, and earn validated knowledge evidence."
        />

        {/* High-Level Overview Stats */}
        <StatGrid columns={4}>
          <Stat
            label="Total Quizzes"
            value={loading ? "—" : stats.total}
            icon={HelpCircle}
          />
          <Stat
            label="Passed & Validated"
            value={loading ? "—" : stats.passed}
            icon={CheckCircle2}
          />
          <Stat
            label="Average Mastery"
            value={loading ? "—" : `${stats.avgScore}%`}
            icon={Award}
          />
          <Stat
            label="Pending Assessments"
            value={loading ? "—" : stats.pending}
            icon={Clock}
          />
        </StatGrid>

        {/* Filter Controls & Search */}
        <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-4">
          <div className="flex items-center gap-1.5 p-1 rounded-xl bg-surface-raised border border-border">
            <Button
              variant={filterTab === "all" ? "secondary" : "ghost"}
              size="sm"
              onClick={() => setFilterTab("all")}
              className="text-xs"
            >
              All ({quizzes?.length || 0})
            </Button>
            <Button
              variant={filterTab === "passed" ? "secondary" : "ghost"}
              size="sm"
              onClick={() => setFilterTab("passed")}
              className="text-xs text-success"
            >
              Passed ({quizzes?.filter((q) => q.passed).length || 0})
            </Button>
            <Button
              variant={filterTab === "retake" ? "secondary" : "ghost"}
              size="sm"
              onClick={() => setFilterTab("retake")}
              className="text-xs text-warning"
            >
              Needs Retake ({quizzes?.filter((q) => q.attempts_count > 0 && !q.passed).length || 0})
            </Button>
            <Button
              variant={filterTab === "unattempted" ? "secondary" : "ghost"}
              size="sm"
              onClick={() => setFilterTab("unattempted")}
              className="text-xs"
            >
              Not Started ({quizzes?.filter((q) => q.attempts_count === 0).length || 0})
            </Button>
          </div>

          <div className="relative w-full sm:w-72">
            <Search className="w-4 h-4 text-fg-muted absolute left-3 top-1/2 -translate-y-1/2" />
            <Input
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search assessment or course..."
              className="pl-9 h-9 text-xs"
            />
          </div>
        </div>

        {/* Loading Skeleton */}
        {loading && (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {[1, 2, 3, 4, 5, 6].map((n) => (
              <Card key={n} className="border-border">
                <CardHeader>
                  <Skeleton className="h-4 w-24 mb-2" />
                  <Skeleton className="h-6 w-full" />
                </CardHeader>
                <CardContent>
                  <Skeleton className="h-16 w-full" />
                </CardContent>
                <CardFooter>
                  <Skeleton className="h-9 w-full" />
                </CardFooter>
              </Card>
            ))}
          </div>
        )}

        {/* Error State */}
        {error && !loading && (
          <ErrorState
            error={error}
            onRetry={refetch}
          />
        )}

        {/* Empty State */}
        {!loading && !error && filteredQuizzes.length === 0 && (
          <EmptyState
            title="No Assessments Found"
            description={
              searchQuery
                ? "No quizzes match your search criteria. Try a different query."
                : "No assessments are available for your current course enrollments."
            }
            action={
              <Link href="/explore">
                <Button variant="primary">Browse Courses</Button>
              </Link>
            }
          />
        )}

        {/* Quizzes Grid */}
        {!loading && !error && filteredQuizzes.length > 0 && (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {filteredQuizzes.map((quiz) => {
              const hasAttempts = quiz.attempts_count > 0;
              const isPassed = quiz.passed;

              return (
                <Card
                  key={quiz.quiz_id}
                  className="flex flex-col justify-between border-border hover:border-border-focus transition-all shadow-sm"
                >
                  <CardHeader className="pb-3">
                    <div className="flex items-center justify-between gap-2 mb-1.5">
                      <Badge variant="neutral" className="text-[11px] truncate max-w-[180px]">
                        {quiz.course_title}
                      </Badge>
                      {isPassed ? (
                        <Badge variant="success">
                          <CheckCircle2 className="w-3.5 h-3.5 mr-1" /> Passed
                        </Badge>
                      ) : hasAttempts ? (
                        <Badge variant="warning">
                          <AlertTriangle className="w-3.5 h-3.5 mr-1" /> Needs Retake
                        </Badge>
                      ) : (
                        <Badge variant="neutral">Not Started</Badge>
                      )}
                    </div>

                    <CardTitle className="text-base font-semibold text-fg line-clamp-2 leading-snug">
                      {quiz.title}
                    </CardTitle>

                    {quiz.module_title && (
                      <CardDescription className="text-xs text-fg-muted mt-1 flex items-center gap-1">
                        <Layers className="w-3 h-3" /> {quiz.module_title}
                      </CardDescription>
                    )}
                  </CardHeader>

                  <CardContent className="space-y-4 pt-1">
                    {/* Score / Performance display */}
                    <div className="p-3 rounded-xl bg-surface-raised border border-border">
                      <div className="flex items-center justify-between text-xs text-fg-muted mb-1.5">
                        <span>Best Score</span>
                        <span className="font-mono font-semibold text-fg">
                          {quiz.best_score !== null ? `${quiz.best_score}%` : "—"}
                        </span>
                      </div>
                      <Progress
                        value={quiz.best_score || 0}
                        tone={isPassed ? "success" : "primary"}
                        className="h-1.5"
                      />
                      <div className="flex items-center justify-between text-[11px] text-fg-muted mt-2">
                        <span>Pass mark: {quiz.passing_score}%</span>
                        <span>{quiz.attempts_count} attempts</span>
                      </div>
                    </div>

                    {/* Metadata tags */}
                    <div className="flex items-center gap-3 text-xs text-fg-muted">
                      <div className="flex items-center gap-1">
                        <HelpCircle className="w-3.5 h-3.5" />
                        <span>{quiz.questions_count} questions</span>
                      </div>
                      <div className="flex items-center gap-1">
                        <Clock className="w-3.5 h-3.5" />
                        <span>{quiz.time_limit_mins} mins</span>
                      </div>
                      {quiz.is_adaptive && (
                        <div className="flex items-center gap-1 text-primary">
                          <Sparkles className="w-3.5 h-3.5" />
                          <span>Adaptive</span>
                        </div>
                      )}
                    </div>
                  </CardContent>

                  <CardFooter className="pt-2 border-t border-border">
                    <Link
                      href={`/learner/learning?course_id=${quiz.course_id}${quiz.content_item_id ? `&item_id=${quiz.content_item_id}` : ""}`}
                      className="w-full"
                    >
                      <Button
                        variant={isPassed ? "secondary" : "primary"}
                        className="w-full text-xs font-medium"
                      >
                        {isPassed ? (
                          <>
                            <RotateCcw className="w-3.5 h-3.5 mr-1.5" /> Review Assessment
                          </>
                        ) : hasAttempts ? (
                          <>
                            <RotateCcw className="w-3.5 h-3.5 mr-1.5" /> Retake Assessment
                          </>
                        ) : (
                          <>
                            Begin Assessment <ArrowRight className="w-3.5 h-3.5 ml-1.5" />
                          </>
                        )}
                      </Button>
                    </Link>
                  </CardFooter>
                </Card>
              );
            })}
          </div>
        )}
      </div>
    </AppShell>
  );
}
