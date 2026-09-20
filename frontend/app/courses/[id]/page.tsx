"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import {
  CheckCircle2,
  CircleHelp,
  CircleX,
  Clock,
  GraduationCap,
  Layers,
  Star,
  Users,
} from "lucide-react";

import { AppShell } from "@/components/shell";
import {
  Badge,
  Breadcrumb,
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
} from "@/components/ui";
import { itemIcon, itemKindLabel } from "@/components/player/course-outline";
import { useApi } from "@/hooks/use-api";
import { useToast } from "@/hooks/use-toast";
import { formatDuration, formatMinutes, pluralize } from "@/lib/utils";
import { learningService } from "@/services";
import type { CourseOverview } from "@/types/learning";

function playerHref(courseId: string, itemId?: string | null): string {
  const query = new URLSearchParams({ course_id: courseId });
  if (itemId) query.set("item_id", itemId);
  return `/learner/learning?${query.toString()}`;
}

function DetailSkeleton() {
  return (
    <div className="space-y-6" aria-busy="true" aria-label="Loading course">
      <Skeleton className="h-8 w-2/3" />
      <Skeleton className="h-4 w-full max-w-2xl" />
      <div className="grid gap-6 lg:grid-cols-3">
        <Skeleton className="h-64 lg:col-span-2" />
        <Skeleton className="h-64" />
      </div>
    </div>
  );
}

export default function CourseDetailPage() {
  const params = useParams();
  const router = useRouter();
  const courseId = params.id as string;
  const { toastSuccess, toastError } = useToast();
  const [enrolling, setEnrolling] = useState(false);

  const { data, loading, error, refetch } = useApi<CourseOverview>(
    (signal) => learningService.courseOverview(courseId, signal),
    { deps: [courseId] }
  );

  const enrollAndStart = async () => {
    if (!data) return;
    setEnrolling(true);
    try {
      await learningService.enroll(courseId);
      toastSuccess("You are enrolled", `Welcome to ${data.course.title}.`);
      router.push(playerHref(courseId, data.progress.resume_item_id));
    } catch (err) {
      toastError(err, "Could not enrol");
      setEnrolling(false);
    }
  };

  return (
    <AppShell>
      <Breadcrumb
        className="mb-4"
        items={[{ label: "Explore", href: "/explore" }, { label: data?.course.title ?? "Course" }]}
      />

      {loading && <DetailSkeleton />}
      {!loading && error && <ErrorState error={error} onRetry={refetch} />}

      {!loading && !error && data && (
        <CourseDetail data={data} enrolling={enrolling} onEnroll={enrollAndStart} />
      )}
    </AppShell>
  );
}

function CourseDetail({
  data,
  enrolling,
  onEnroll,
}: {
  data: CourseOverview;
  enrolling: boolean;
  onEnroll: () => void;
}) {
  const { course, progress } = data;
  const started = progress.completed_items > 0 || progress.time_spent_seconds > 0;
  const finished = progress.total_items > 0 && progress.completed_items >= progress.total_items;
  const percent = Math.round(progress.percent);

  return (
    <div className="grid gap-8 lg:grid-cols-3">
      {/* Main column */}
      <div className="space-y-8 lg:col-span-2">
        <header className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="primary">{course.category}</Badge>
            <Badge className="capitalize">{course.difficulty}</Badge>
            <span className="font-mono text-xs text-fg-muted">{course.code}</span>
            {data.is_preview && <Badge variant="warning">Preview</Badge>}
          </div>
          <h1 className="text-3xl font-semibold tracking-tight text-fg">{course.title}</h1>
          {course.description && <p className="max-w-2xl text-base leading-relaxed text-fg-muted">{course.description}</p>}

          <ul className="flex flex-wrap items-center gap-x-5 gap-y-2 text-sm text-fg-muted">
            {course.instructor_name && (
              <li className="flex items-center gap-1.5">
                <GraduationCap className="size-4" aria-hidden="true" /> {course.instructor_name}
              </li>
            )}
            {course.duration_minutes !== null && (
              <li className="flex items-center gap-1.5">
                <Clock className="size-4" aria-hidden="true" /> {formatMinutes(course.duration_minutes)}
              </li>
            )}
            <li className="flex items-center gap-1.5">
              <Layers className="size-4" aria-hidden="true" />
              {pluralize(course.module_count, "module")} · {pluralize(course.item_count, "item")}
            </li>
            {course.enrollment_count > 0 && (
              <li className="flex items-center gap-1.5">
                <Users className="size-4" aria-hidden="true" /> {pluralize(course.enrollment_count, "learner")} enrolled
              </li>
            )}
            {course.rating !== null && (
              <li className="flex items-center gap-1.5">
                <Star className="size-4 fill-amber-400 text-amber-400" aria-hidden="true" /> {course.rating.toFixed(1)}
              </li>
            )}
          </ul>
        </header>

        {data.objectives.length > 0 && (
          <section aria-labelledby="learn-heading">
            <h2 id="learn-heading" className="mb-3 text-lg font-semibold text-fg">
              What you will learn
            </h2>
            <ul className="grid gap-2.5 sm:grid-cols-2">
              {data.objectives.map((objective) => (
                <li key={objective} className="flex items-start gap-2.5 text-sm text-fg">
                  <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-success" aria-hidden="true" />
                  <span>{objective}</span>
                </li>
              ))}
            </ul>
            {data.objectives_source === "competency_descriptions" && (
              <p className="mt-2 text-xs text-fg-muted">Taken from the competencies this course develops.</p>
            )}
          </section>
        )}

        <section aria-labelledby="content-heading">
          <h2 id="content-heading" className="mb-3 text-lg font-semibold text-fg">
            Course content
          </h2>
          {data.modules.length === 0 ? (
            <EmptyState size="sm" title="No content yet" description="This course has no published lessons." />
          ) : (
            <div className="space-y-3">
              {data.modules.map((module, index) => (
                <Card key={module.id}>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-base">
                      {index + 1}. {module.title.replace(/^Module\s+\d+:\s*/i, "")}
                    </CardTitle>
                    <CardDescription>
                      {pluralize(module.lessons, "lesson")}
                      {module.assessments > 0 && ` · ${pluralize(module.assessments, "assessment")}`}
                      {module.known_duration_seconds > 0 && ` · ${formatDuration(module.known_duration_seconds)}`}
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <ul className="divide-y divide-border">
                      {module.items.map((item) => {
                        const Icon = itemIcon(item);
                        const done = item.progress_status === "completed";
                        const row = (
                          <span className="flex items-center gap-3 py-2 text-sm">
                            {done ? (
                              <CheckCircle2 className="size-4 shrink-0 text-success" aria-label="Completed" />
                            ) : (
                              <Icon className="size-4 shrink-0 text-fg-subtle" aria-hidden="true" />
                            )}
                            <span className="min-w-0 flex-1 truncate text-fg">{item.title}</span>
                            <span className="shrink-0 text-xs text-fg-muted">
                              {itemKindLabel(item)}
                              {item.duration_seconds > 0 && ` · ${formatDuration(item.duration_seconds)}`}
                            </span>
                          </span>
                        );
                        return (
                          <li key={item.id}>
                            {data.is_enrolled || data.is_preview ? (
                              <Link href={playerHref(course.id, item.id)} className="block hover:bg-surface">
                                {row}
                              </Link>
                            ) : (
                              row
                            )}
                          </li>
                        );
                      })}
                    </ul>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </section>

        {data.competencies.length > 0 && (
          <section aria-labelledby="skills-heading">
            <h2 id="skills-heading" className="mb-3 text-lg font-semibold text-fg">
              Competencies developed
            </h2>
            <div className="grid gap-3 sm:grid-cols-2">
              {data.competencies.map((competency) => (
                <Card key={competency.id}>
                  <CardContent className="space-y-2 pt-5">
                    <div className="flex items-start justify-between gap-2">
                      <h3 className="text-sm font-medium text-fg">{competency.name}</h3>
                      {competency.domain && <Badge>{competency.domain}</Badge>}
                    </div>
                    {competency.mastery !== null ? (
                      <MasteryBar mastery={competency.mastery} label="Your mastery" />
                    ) : (
                      <p className="text-xs text-fg-muted">No evidence yet. Answer this course&apos;s assessments to see yours.</p>
                    )}
                    <p className="text-xs text-fg-muted">Target: {Math.round(competency.target_mastery * 100)}%</p>
                  </CardContent>
                </Card>
              ))}
            </div>
          </section>
        )}
      </div>

      {/* Side column */}
      <aside className="space-y-4 lg:sticky lg:top-24 lg:self-start">
        <Card>
          <CardContent className="space-y-4 pt-5">
            {data.is_enrolled ? (
              <>
                <div>
                  <div className="mb-1.5 flex items-baseline justify-between">
                    <span className="text-sm font-medium text-fg">{finished ? "Completed" : "Your progress"}</span>
                    <span className="text-sm font-semibold tabular-nums text-fg">{percent}%</span>
                  </div>
                  <Progress value={percent} ariaLabel="Course progress" />
                  <p className="mt-1.5 text-xs text-fg-muted">
                    {progress.completed_items} of {progress.total_items} complete
                    {progress.time_spent_seconds > 0 && ` · ${formatDuration(progress.time_spent_seconds)} learning`}
                  </p>
                </div>
                <Link href={playerHref(course.id, progress.resume_item_id)}>
                  <Button className="w-full" size="lg">
                    {finished ? "Review course" : started ? "Continue" : "Start course"}
                  </Button>
                </Link>
                {progress.resume_item_title && !finished && (
                  <p className="text-xs text-fg-muted">
                    {started ? "Next: " : "First lesson: "}
                    {progress.resume_item_title}
                  </p>
                )}
              </>
            ) : data.is_preview ? (
              <Link href={playerHref(course.id, progress.resume_item_id)}>
                <Button className="w-full" size="lg" variant="secondary">
                  Open preview
                </Button>
              </Link>
            ) : (
              <>
                <Button className="w-full" size="lg" onClick={onEnroll} disabled={enrolling || progress.total_items === 0}>
                  {enrolling ? "Enrolling…" : "Enrol and start"}
                </Button>
                {progress.total_items === 0 && (
                  <p className="text-xs text-fg-muted">This course has no published lessons yet.</p>
                )}
              </>
            )}
          </CardContent>
        </Card>

        {data.prerequisites.length > 0 && (
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base">Before you start</CardTitle>
              <CardDescription>This course builds on these skills.</CardDescription>
            </CardHeader>
            <CardContent>
              <ul className="space-y-3">
                {data.prerequisites.map((prerequisite) => (
                  <li key={prerequisite.competency_id} className="flex items-start gap-2.5 text-sm">
                    {prerequisite.met === true ? (
                      <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-success" aria-label="You meet this" />
                    ) : prerequisite.met === false ? (
                      <CircleX className="mt-0.5 size-4 shrink-0 text-warning" aria-label="Not yet met" />
                    ) : (
                      <CircleHelp className="mt-0.5 size-4 shrink-0 text-fg-subtle" aria-label="Not yet assessed" />
                    )}
                    <span>
                      <span className="block text-fg">{prerequisite.name}</span>
                      <span className="block text-xs text-fg-muted">
                        {prerequisite.mastery !== null
                          ? `Your mastery ${Math.round(prerequisite.mastery * 100)}% · ${Math.round(prerequisite.min_mastery * 100)}% recommended`
                          : `Not assessed yet · ${Math.round(prerequisite.min_mastery * 100)}% recommended`}
                      </span>
                    </span>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
        )}
      </aside>
    </div>
  );
}
