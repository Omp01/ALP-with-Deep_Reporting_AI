"use client";

import React from "react";
import Link from "next/link";
import {
  ArrowRight,
  BookOpen,
  Clock,
  Compass,
  GraduationCap,
  Lightbulb,
  PlayCircle,
  Sparkles,
} from "lucide-react";

import { AppShell, PageHeader } from "@/components/shell";
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  EmptyState,
  ErrorState,
  MasteryBar,
  Progress,
  Skeleton,
  SkeletonCard,
} from "@/components/ui";
import { itemKindLabel } from "@/components/player/course-outline";
import { useApi } from "@/hooks/use-api";
import { useAuth } from "@/hooks/use-auth";
import { formatDuration, formatRelativeTime } from "@/lib/utils";
import { learningService } from "@/services";
import type { LearnerHome, Recommendation } from "@/types/learning";

function greeting(hour: number): string {
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

function playerHref(courseId: string, itemId?: string | null): string {
  const query = new URLSearchParams({ course_id: courseId });
  if (itemId) query.set("item_id", itemId);
  return `/learner/learning?${query.toString()}`;
}

function recommendationHref(rec: Recommendation): string {
  return rec.kind === "content" ? playerHref(rec.course_id, rec.content_id) : `/courses/${rec.course_id}`;
}

function HomeSkeleton() {
  return (
    <div className="space-y-6" aria-busy="true" aria-label="Loading your learning home">
      <Skeleton className="h-40 w-full rounded-xl" />
      <div className="grid gap-6 lg:grid-cols-3">
        <SkeletonCard />
        <SkeletonCard />
        <SkeletonCard />
      </div>
    </div>
  );
}

function ContinueCard({ home }: { home: LearnerHome }) {
  const next = home.continue_learning;

  if (!next) {
    return (
      <Card>
        <CardContent className="pt-6">
          <EmptyState
            icon={GraduationCap}
            size="sm"
            title={home.stats.enrolled_courses > 0 ? "You have finished everything you enrolled in" : "Start your first course"}
            description="Browse the catalog to find something to learn next."
            action={
              <Link href="/explore">
                <Button>
                  <Compass aria-hidden="true" /> Explore courses
                </Button>
              </Link>
            }
          />
        </CardContent>
      </Card>
    );
  }

  const percent = Math.round(next.progress_percent);
  return (
    <Card className="border-primary-border">
      <CardContent className="flex flex-col gap-5 pt-6 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0 space-y-2">
          <p className="text-xs font-medium uppercase tracking-wide text-primary">Continue learning</p>
          <h2 className="text-xl font-semibold tracking-tight text-fg">{next.course_title}</h2>
          {next.item_title && (
            <p className="flex items-center gap-1.5 text-sm text-fg-muted">
              <PlayCircle className="size-4 shrink-0" aria-hidden="true" />
              <span className="truncate">
                {next.module_title ? `${next.module_title.replace(/^Module\s+\d+:\s*/i, "")} · ` : ""}
                {next.item_title}
              </span>
            </p>
          )}
          <div className="flex max-w-sm items-center gap-3 pt-1">
            <Progress value={percent} ariaLabel={`${next.course_title} progress`} className="flex-1" />
            <span className="text-xs font-medium tabular-nums text-fg">{percent}%</span>
          </div>
        </div>
        <Link href={playerHref(next.course_id, next.item_id)} className="shrink-0">
          <Button size="lg">
            Continue <ArrowRight aria-hidden="true" />
          </Button>
        </Link>
      </CardContent>
    </Card>
  );
}

export default function LearnerHomePage() {
  const { user } = useAuth();
  const { data: home, loading, error, refetch } = useApi<LearnerHome>((signal) => learningService.home(signal));

  const firstName = user?.full_name.split(" ")[0];
  const title = firstName ? `${greeting(new Date().getHours())}, ${firstName}` : greeting(new Date().getHours());

  return (
    <AppShell roles={["learner", "manager", "instructor", "org_admin", "system_admin"]}>
      <PageHeader
        title={title}
        description="Pick up where you left off. What you see next is based on what you have actually done."
      />

      {loading && <HomeSkeleton />}
      {!loading && error && <ErrorState error={error} onRetry={refetch} />}

      {!loading && !error && home && (
        <div className="space-y-6">
          <ContinueCard home={home} />

          <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {[
              ["Courses enrolled", String(home.stats.enrolled_courses)],
              ["Courses completed", String(home.stats.completed_courses)],
              ["Lessons completed", String(home.stats.completed_items)],
              ["Time learning", home.stats.time_spent_seconds > 0 ? formatDuration(home.stats.time_spent_seconds) : "—"],
            ].map(([label, value]) => (
              <div key={label} className="rounded-xl border border-border bg-surface-elevated px-4 py-3">
                <dt className="text-xs text-fg-muted">{label}</dt>
                <dd className="mt-0.5 text-xl font-semibold tabular-nums text-fg">{value}</dd>
              </div>
            ))}
          </dl>

          <div className="grid gap-6 lg:grid-cols-3">
            {/* Recommended */}
            <Card className="lg:col-span-2">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <Lightbulb className="size-4 text-primary" aria-hidden="true" /> Recommended for you
                </CardTitle>
                <CardDescription>Each suggestion says why you are seeing it.</CardDescription>
              </CardHeader>
              <CardContent>
                {home.recommendations.length === 0 ? (
                  <EmptyState size="sm" title="Nothing to suggest yet" description="Suggestions appear once there is published content you have not started." />
                ) : (
                  <ul className="divide-y divide-border">
                    {home.recommendations.map((rec) => (
                      <li key={`${rec.kind}-${rec.content_id ?? rec.course_id}`}>
                        <Link
                          href={recommendationHref(rec)}
                          className="flex items-start gap-3 py-3 hover:bg-surface focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary sm:-mx-2 sm:rounded-lg sm:px-2"
                        >
                          <span className="mt-0.5 rounded-lg bg-primary-light p-2 text-primary">
                            {rec.kind === "content" ? <BookOpen className="size-4" aria-hidden="true" /> : <GraduationCap className="size-4" aria-hidden="true" />}
                          </span>
                          <span className="min-w-0 flex-1">
                            <span className="block truncate text-sm font-medium text-fg">
                              {rec.content_title ?? rec.course_title}
                            </span>
                            <span className="block truncate text-xs text-fg-muted">
                              {rec.content_title
                                ? `${itemKindLabel({ content_type: rec.content_type ?? "", kind: "lesson" })} · ${rec.course_title}`
                                : "Course"}
                            </span>
                            <span className="mt-1 block text-xs text-fg">{rec.reason}</span>
                          </span>
                          <ArrowRight className="mt-1 size-4 shrink-0 text-fg-subtle" aria-hidden="true" />
                        </Link>
                      </li>
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>

            {/* Competencies */}
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Your competencies</CardTitle>
                <CardDescription>Estimated from your assessment answers.</CardDescription>
              </CardHeader>
              <CardContent>
                {home.competencies.length === 0 ? (
                  <EmptyState
                    size="sm"
                    title="No evidence yet"
                    description="Your competencies appear after you answer your first assessment questions."
                  />
                ) : (
                  <ul className="space-y-4">
                    {home.competencies.map((competency) => (
                      <li key={competency.id}>
                        <MasteryBar mastery={competency.mastery} label={competency.name} />
                        <p className="mt-1 text-xs text-fg-muted">
                          Based on {competency.evidence_count} {competency.evidence_count === 1 ? "answer" : "answers"}
                        </p>
                      </li>
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>
          </div>

          <div className="grid gap-6 lg:grid-cols-3">
            {/* Recent activity */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <Clock className="size-4 text-fg-muted" aria-hidden="true" /> Recent activity
                </CardTitle>
              </CardHeader>
              <CardContent>
                {home.recent_activity.length === 0 ? (
                  <EmptyState size="sm" title="No activity yet" description="Lessons you start or finish will show here." />
                ) : (
                  <ol className="space-y-3">
                    {home.recent_activity.map((activity, index) => (
                      <li key={`${activity.timestamp}-${index}`} className="text-sm">
                        <p className="text-fg">{activity.label}</p>
                        <p className="text-xs text-fg-muted">
                          {activity.course_title ? `${activity.course_title} · ` : ""}
                          {formatRelativeTime(activity.timestamp)}
                        </p>
                      </li>
                    ))}
                  </ol>
                )}
              </CardContent>
            </Card>

            {/* AI insight */}
            <Card className="lg:col-span-2">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <Sparkles className="size-4 text-primary" aria-hidden="true" /> AI learning insight
                </CardTitle>
              </CardHeader>
              <CardContent>
                {home.insight ? (
                  <div className="space-y-3">
                    <p className="text-sm leading-relaxed text-fg">{home.insight.narrative}</p>
                    <div className="flex flex-wrap items-center gap-3">
                      <Link href="/learner/insights">
                        <Button variant="secondary" size="sm">
                          See evidence
                        </Button>
                      </Link>
                      <span className="text-xs text-fg-muted">Generated {formatRelativeTime(home.insight.created_at)}</span>
                    </div>
                  </div>
                ) : (
                  <EmptyState
                    size="sm"
                    title="No insight generated yet"
                    description="Insights are written from your real activity, with the evidence behind each statement."
                    action={
                      <Link href="/learner/insights">
                        <Button variant="secondary" size="sm">
                          Open AI insights
                        </Button>
                      </Link>
                    }
                  />
                )}
              </CardContent>
            </Card>
          </div>

          {home.in_progress.length > 1 && (
            <section aria-labelledby="in-progress-heading">
              <h2 id="in-progress-heading" className="mb-3 text-base font-semibold text-fg">
                In progress
              </h2>
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {home.in_progress.map((course) => (
                  <Link key={course.course_id} href={playerHref(course.course_id)} className="group">
                    <Card className="h-full transition-shadow group-hover:shadow-md">
                      <CardContent className="space-y-3 pt-5">
                        <div className="flex items-center gap-2">
                          <Badge variant="primary">{course.category}</Badge>
                          <Badge className="capitalize">{course.difficulty}</Badge>
                        </div>
                        <h3 className="font-medium text-fg">{course.title}</h3>
                        <div>
                          <Progress value={course.progress_percent} ariaLabel={`${course.title} progress`} size="sm" />
                          <p className="mt-1.5 text-xs text-fg-muted">
                            {course.completed_items} of {course.total_items} lessons
                          </p>
                        </div>
                      </CardContent>
                    </Card>
                  </Link>
                ))}
              </div>
            </section>
          )}
        </div>
      )}
    </AppShell>
  );
}
