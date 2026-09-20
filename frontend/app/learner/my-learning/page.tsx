"use client";

import React, { useState, useMemo } from "react";
import Link from "next/link";
import {
  BookOpen,
  CheckCircle2,
  Compass,
  PlayCircle,
  GraduationCap,
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
  Skeleton,
  EmptyState,
  ErrorState,
} from "@/components/ui";
import { apiClient } from "@/lib/api-client";
import { useApi } from "@/hooks/use-api";

interface Course {
  id: string;
  title: string;
  code: string;
  description: string;
  category: string;
  difficulty: string;
  rating: number;
  duration_minutes: number;
  thumbnail_url: string | null;
  instructor_name: string | null;
  is_enrolled: boolean;
  progress_pct: number;
}

export default function MyLearningPage() {
  const [filterTab, setFilterTab] = useState<"all" | "in_progress" | "completed">("all");

  const { data: allCourses, loading, error, refetch } = useApi<Course[]>(
    (signal) => apiClient.get<Course[]>("/api/v1/courses", { signal })
  );

  const enrolledCourses = useMemo(() => {
    if (!allCourses) return [];
    return allCourses.filter((c) => c.is_enrolled);
  }, [allCourses]);

  const filteredCourses = useMemo(() => {
    if (filterTab === "in_progress") {
      return enrolledCourses.filter((c) => (c.progress_pct || 0) < 100);
    }
    if (filterTab === "completed") {
      return enrolledCourses.filter((c) => (c.progress_pct || 0) >= 100);
    }
    return enrolledCourses;
  }, [enrolledCourses, filterTab]);

  return (
    <AppShell>
      <PageHeader
        title="My Learning"
        description="Pick up where you left off, track competency acquisition, and complete your curriculum goals."
        actions={
          <Link href="/explore">
            <Button variant="primary" size="sm" className="gap-1.5">
              <Compass className="h-4 w-4" />
              Explore More Courses
            </Button>
          </Link>
        }
      />

      {/* Tabs */}
      <div className="mb-6 flex gap-2 border-b border-border pb-3">
        <button
          onClick={() => setFilterTab("all")}
          className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
            filterTab === "all"
              ? "bg-surface-elevated text-accent border border-border shadow-sm"
              : "text-fg-muted hover:text-fg"
          }`}
        >
          All Enrolled ({enrolledCourses.length})
        </button>
        <button
          onClick={() => setFilterTab("in_progress")}
          className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
            filterTab === "in_progress"
              ? "bg-surface-elevated text-accent border border-border shadow-sm"
              : "text-fg-muted hover:text-fg"
          }`}
        >
          In Progress ({enrolledCourses.filter((c) => (c.progress_pct || 0) < 100).length})
        </button>
        <button
          onClick={() => setFilterTab("completed")}
          className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
            filterTab === "completed"
              ? "bg-surface-elevated text-accent border border-border shadow-sm"
              : "text-fg-muted hover:text-fg"
          }`}
        >
          Completed ({enrolledCourses.filter((c) => (c.progress_pct || 0) >= 100).length})
        </button>
      </div>

      {loading ? (
        <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Card key={i} className="overflow-hidden bg-surface-elevated">
              <Skeleton className="h-40 w-full" />
              <CardHeader className="space-y-2">
                <Skeleton className="h-5 w-3/4" />
                <Skeleton className="h-4 w-1/2" />
              </CardHeader>
              <CardContent>
                <Skeleton className="h-3 w-full" />
              </CardContent>
            </Card>
          ))}
        </div>
      ) : error ? (
        <ErrorState
          title="Could not load your courses"
          error={error}
          onRetry={refetch}
        />
      ) : filteredCourses.length === 0 ? (
        <EmptyState
          icon={BookOpen}
          title={
            filterTab === "completed"
              ? "No completed courses yet"
              : filterTab === "in_progress"
              ? "No active courses in progress"
              : "You are not enrolled in any courses"
          }
          description={
            filterTab === "all"
              ? "Browse the course catalog to enroll in comprehensive engineering and data programs."
              : "Browse courses or resume studying to see updates here."
          }
          action={
            <Link href="/explore">
              <Button variant="primary" size="sm" className="gap-2">
                <Compass className="h-4 w-4" />
                Explore Courses
              </Button>
            </Link>
          }
        />
      ) : (
        <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
          {filteredCourses.map((course) => {
            const pct = Math.round(course.progress_pct || 0);
            const isCompleted = pct >= 100;

            return (
              <Card
                key={course.id}
                className="group flex flex-col justify-between overflow-hidden border border-border bg-surface-elevated transition-all duration-200 hover:-translate-y-1 hover:border-accent/40 hover:shadow-lg"
              >
                <div>
                  <div className="relative h-40 w-full overflow-hidden bg-surface-subtle">
                    {course.thumbnail_url ? (
                      /* eslint-disable-next-line @next/next/no-img-element */
                      <img
                        src={course.thumbnail_url}
                        alt={course.title}
                        className="h-full w-full object-cover transition-transform duration-500 group-hover:scale-105"
                      />
                    ) : (
                      <div className="flex h-full w-full items-center justify-center bg-gradient-to-br from-accent/10 to-surface-subtle text-accent">
                        <GraduationCap className="h-14 w-14 opacity-40" />
                      </div>
                    )}

                    <div className="absolute left-3 top-3">
                      <Badge variant="neutral" className="backdrop-blur-md bg-surface/80">
                        {course.category}
                      </Badge>
                    </div>

                    <div className="absolute right-3 top-3">
                      {isCompleted ? (
                        <Badge variant="success" className="flex items-center gap-1 shadow-sm">
                          <CheckCircle2 className="h-3 w-3" />
                          Completed
                        </Badge>
                      ) : (
                        <Badge variant="neutral" className="backdrop-blur-md bg-surface/80 font-mono text-[11px]">
                          {pct}% Done
                        </Badge>
                      )}
                    </div>
                  </div>

                  <CardHeader className="space-y-1.5 pb-2">
                    <span className="font-mono text-xs text-fg-muted font-medium">
                      {course.code}
                    </span>
                    <CardTitle className="line-clamp-1 text-base font-semibold text-fg group-hover:text-accent transition-colors">
                      <Link href={`/courses/${course.id}`}>{course.title}</Link>
                    </CardTitle>
                    <CardDescription className="line-clamp-2 text-xs text-fg-muted leading-relaxed">
                      {course.description}
                    </CardDescription>
                  </CardHeader>

                  <CardContent className="space-y-2.5 pb-4">
                    <div className="flex justify-between text-xs font-medium text-fg-muted">
                      <span>Progress</span>
                      <span className="text-fg">{pct}%</span>
                    </div>
                    <Progress value={pct} size="sm" tone={isCompleted ? "success" : "primary"} />
                  </CardContent>
                </div>

                <CardFooter className="border-t border-border bg-surface-subtle/40 pt-3 pb-3 flex items-center justify-between">
                  <span className="text-[11px] text-fg-muted font-medium">
                    {course.instructor_name ?? ""}
                  </span>

                  <Link href={`/learner/learning?course_id=${course.id}`}>
                    <Button variant="primary" size="sm" className="h-8 gap-1.5 px-3 text-xs">
                      <PlayCircle className="h-3.5 w-3.5" />
                      {isCompleted ? "Review" : "Continue"}
                    </Button>
                  </Link>
                </CardFooter>
              </Card>
            );
          })}
        </div>
      )}
    </AppShell>
  );
}
