"use client";

import React, { Suspense, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowLeft, ChevronLeft, ChevronRight, GraduationCap, ListTree, Sparkles } from "lucide-react";

import { AppShell } from "@/components/shell";
import {
  Button,
  Dialog,
  EmptyState,
  ErrorState,
  Progress,
  Skeleton,
} from "@/components/ui";
import { CourseOutline } from "@/components/player/course-outline";
import { LessonView } from "@/components/player/lesson-view";
import { NextStepCard } from "@/components/player/next-step-card";
import { useApi } from "@/hooks/use-api";
import { LearningEventsProvider } from "@/hooks/use-learning-events";
import { useMediaQuery } from "@/hooks/use-media-query";
import { useToast } from "@/hooks/use-toast";
import { learningService } from "@/services";
import type { ContentProgressResult } from "@/types/learning";
import { CourseAIChat } from "@/components/course/course-ai-chat";

function LearningPlayer() {
  const router = useRouter();
  const params = useSearchParams();
  const { toastSuccess, toastError } = useToast();

  const courseParam = params.get("course_id");
  const itemParam = params.get("item_id");
  const isDesktop = useMediaQuery("(min-width: 1024px)");
  const [outlineOpen, setOutlineOpen] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);
  const [enrolling, setEnrolling] = useState(false);
  // How the learner arrived at the lesson on screen (`via` in the URL), reported with `lesson_opened`.
  const viaParam = params.get("via");
  const openedVia = (["outline", "resume", "next", "recommendation"] as const).find((v) => v === viaParam) ?? "direct";

  const go = useCallback(
    (courseId: string, itemId?: string | null, via: "outline" | "next" | "recommendation" | "direct" = "direct") => {
      const query = new URLSearchParams({ course_id: courseId });
      if (itemId) query.set("item_id", itemId);
      if (itemId && via !== "direct") query.set("via", via);
      router.push(`/learner/learning?${query.toString()}`);
    },
    [router]
  );

  // 1. No course chosen: continue where the learner left off.
  const home = useApi(
    (signal) => learningService.home(signal),
    { enabled: !courseParam }
  );
  useEffect(() => {
    const next = home.data?.continue_learning;
    if (!courseParam && next) {
      const query = new URLSearchParams({ course_id: next.course_id });
      if (next.item_id) query.set("item_id", next.item_id);
      router.replace(`/learner/learning?${query.toString()}`);
    }
  }, [courseParam, home.data, router]);

  // 2. The course outline and the learner's progress in it.
  const overview = useApi(
    (signal) => learningService.courseOverview(courseParam as string, signal),
    { deps: [courseParam], enabled: !!courseParam }
  );

  // No lesson chosen: open the resume point, else the first lesson.
  useEffect(() => {
    if (!courseParam || itemParam || !overview.data) return;
    const firstItem = overview.data.modules.flatMap((m) => m.items)[0]?.id;
    const target = overview.data.progress.resume_item_id ?? firstItem;
    if (target) router.replace(`/learner/learning?course_id=${courseParam}&item_id=${target}&via=resume`);
  }, [courseParam, itemParam, overview.data, router]);

  // 3. The lesson itself.
  const lesson = useApi(
    (signal) => learningService.player(itemParam as string, signal),
    { deps: [itemParam], enabled: !!itemParam }
  );

  const [adaptiveKey, setAdaptiveKey] = useState(0);
  const refreshAll = useCallback(() => {
    overview.refetch();
    lesson.refetch();
    setAdaptiveKey((k) => k + 1);      // the learner did something: ask the adaptive engine again
  }, [overview, lesson]);

  const onProgress = useCallback(
    (result: ContentProgressResult) => {
      if (result.status === "completed") {
        overview.refetch();
        setAdaptiveKey((k) => k + 1);
      }
    },
    [overview]
  );

  const enroll = async () => {
    if (!courseParam) return;
    setEnrolling(true);
    try {
      await learningService.enroll(courseParam);
      toastSuccess("You are enrolled", "Your progress will be saved as you learn.");
      overview.refetch();
    } catch (error) {
      toastError(error, "Could not enrol");
    } finally {
      setEnrolling(false);
    }
  };

  // ---- states ----------------------------------------------------------------------------
  if (!courseParam) {
    if (home.loading) return <PlayerSkeleton />;
    if (home.error) return <div className="p-8"><ErrorState error={home.error} onRetry={home.refetch} /></div>;
    return (
      <div className="mx-auto max-w-xl p-8">
        <EmptyState
          icon={GraduationCap}
          title="Nothing in progress"
          description="Pick a course to start learning. Your place is remembered, so you can always come back to it here."
          action={
            <Link href="/explore">
              <Button>Explore courses</Button>
            </Link>
          }
        />
      </div>
    );
  }

  if (overview.loading) return <PlayerSkeleton />;
  if (overview.error) {
    return (
      <div className="p-8">
        <ErrorState error={overview.error} onRetry={overview.refetch} />
      </div>
    );
  }
  const course = overview.data;
  if (!course) return <PlayerSkeleton />;

  if (course.progress.total_items === 0) {
    return (
      <div className="mx-auto max-w-xl p-8">
        <EmptyState
          icon={GraduationCap}
          title="This course has no published lessons yet"
          description="Check back soon, or explore other courses."
          action={
            <Link href="/explore">
              <Button variant="secondary">Explore courses</Button>
            </Link>
          }
        />
      </div>
    );
  }

  if (!course.is_enrolled && !course.is_preview) {
    return (
      <div className="mx-auto max-w-xl p-8">
        <EmptyState
          icon={GraduationCap}
          title={`Enrol to start ${course.course.title}`}
          description="Enrolling lets us save your progress and adapt what you see next."
          action={
            <Button onClick={enroll} disabled={enrolling}>
              {enrolling ? "Enrolling…" : "Enrol in this course"}
            </Button>
          }
          secondaryAction={
            <Link href={`/courses/${course.course.id}`}>
              <Button variant="ghost">View course details</Button>
            </Link>
          }
        />
      </div>
    );
  }

  const payload = lesson.data && lesson.data.item.id === itemParam ? lesson.data : null;
  const percent = Math.round(course.progress.percent);

  const outline = (
    <>
      {!course.is_preview && (
        <NextStepCard
          courseId={course.course.id}
          refreshKey={adaptiveKey}
          onOpen={(id) => {
            setOutlineOpen(false);
            go(course.course.id, id, "recommendation");
          }}
        />
      )}
      <CourseOutline
        modules={course.modules}
        activeId={itemParam}
        onSelect={(id) => {
          setOutlineOpen(false);
          go(course.course.id, id, "outline");
        }}
      />
    </>
  );

  const view = (
    <div className="flex h-[calc(100dvh-4rem)] flex-col overflow-hidden">
      {/* Header: where you are, and how far along */}
      <header className="flex shrink-0 items-center gap-3 border-b border-border bg-surface-elevated px-4 py-2.5">
        <Link
          href={`/courses/${course.course.id}`}
          aria-label="Back to course page"
          className="rounded-md p-1.5 text-fg-muted hover:bg-surface hover:text-fg focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary"
        >
          <ArrowLeft className="size-4" aria-hidden="true" />
        </Link>
        <div className="min-w-0 flex-1">
          <p className="truncate text-xs text-fg-muted">
            {course.course.title}
            {payload && <> &nbsp;/&nbsp; {payload.module_title}</>}
          </p>
          <h1 className="truncate text-sm font-semibold text-fg">{payload?.item.title ?? "Loading lesson…"}</h1>
        </div>
        <div className="hidden items-center gap-2 sm:flex" title={`${course.progress.completed_items} of ${course.progress.total_items} complete`}>
          <div className="w-32">
            <Progress value={percent} size="sm" ariaLabel="Course progress" />
          </div>
          <span className="w-9 text-right text-xs font-medium tabular-nums text-fg">{percent}%</span>
        </div>
        <Button
          variant="secondary"
          size="sm"
          onClick={() => setChatOpen((prev) => !prev)}
          className="border-primary/40 bg-primary/10 text-primary hover:bg-primary/20 hover:text-primary transition-colors flex items-center gap-1.5 shadow-sm"
        >
          <Sparkles className="size-3.5 animate-pulse" aria-hidden="true" />
          <span className="font-semibold">AI Mentor</span>
        </Button>
        {!isDesktop && (
          <Button variant="secondary" size="sm" onClick={() => setOutlineOpen(true)}>
            <ListTree aria-hidden="true" /> Contents
          </Button>
        )}
      </header>

      {course.is_preview && (
        <p className="shrink-0 bg-info-light px-4 py-1.5 text-center text-xs text-fg">
          Preview: you are viewing this as an author. Your progress here is not shown to learners.
        </p>
      )}

      <div className="flex min-h-0 flex-1">
        <main id="lesson" className="min-w-0 flex-1 overflow-y-auto bg-surface px-4 py-6 sm:px-8">
          {lesson.error && !payload ? (
            <ErrorState error={lesson.error} onRetry={lesson.refetch} />
          ) : !payload ? (
            <div className="mx-auto max-w-4xl space-y-4">
              <Skeleton className="aspect-video w-full rounded-xl" />
              <Skeleton className="h-6 w-2/3" />
              <Skeleton className="h-4 w-full" />
            </div>
          ) : (
            <LessonView
              key={payload.item.id}
              payload={payload}
              onProgress={onProgress}
              onServerCompleted={refreshAll}
              onContinue={() => payload.next_id && go(course.course.id, payload.next_id, "next")}
              openedVia={openedVia}
            />
          )}
        </main>

        {isDesktop && (
          <aside className="w-80 shrink-0 overflow-y-auto border-l border-border bg-surface-elevated p-3" aria-label="Course contents">
            <h2 className="px-2 pb-2 text-xs font-semibold uppercase tracking-wide text-fg-muted">Course contents</h2>
            {outline}
          </aside>
        )}
      </div>

      {/* Bottom bar: previous / where you are / next */}
      <footer className="flex shrink-0 items-center justify-between gap-3 border-t border-border bg-surface-elevated px-4 py-2.5">
        <Button
          variant="secondary"
          size="sm"
          disabled={!payload?.previous_id}
          onClick={() => payload?.previous_id && go(course.course.id, payload.previous_id, "next")}
        >
          <ChevronLeft aria-hidden="true" /> Previous
        </Button>
        <p className="text-xs text-fg-muted" aria-live="polite">
          {payload ? `Lesson ${payload.position} of ${payload.total}` : ""}
        </p>
        <Button
          variant={payload?.progress.status === "completed" ? "primary" : "secondary"}
          size="sm"
          disabled={!payload?.next_id}
          onClick={() => payload?.next_id && go(course.course.id, payload.next_id, "next")}
        >
          Next <ChevronRight aria-hidden="true" />
        </Button>
      </footer>

      {!isDesktop && (
        <Dialog open={outlineOpen} onClose={() => setOutlineOpen(false)} title="Course contents" variant="drawer" size="sm">
          {outline}
        </Dialog>
      )}

      {/* Floating AI Mentor button */}
      {!chatOpen && (
        <button
          type="button"
          onClick={() => setChatOpen(true)}
          aria-label="Open AI Course Mentor"
          className="fixed bottom-14 right-6 z-40 flex items-center gap-2 rounded-full bg-gradient-to-r from-primary to-primary-hover px-4 py-2.5 text-xs font-semibold text-white shadow-xl ring-2 ring-primary/30 transition-transform hover:scale-105 active:scale-95"
        >
          <Sparkles className="h-4 w-4 animate-pulse" />
          <span>Ask AI Mentor</span>
        </button>
      )}

      {/* Slide-over Course AI Chatbot */}
      <CourseAIChat
        courseId={course.course.id}
        courseTitle={course.course.title}
        currentItemId={itemParam}
        isOpen={chatOpen}
        onClose={() => setChatOpen(false)}
        onSelectLesson={(itemId) => {
          go(course.course.id, itemId, "recommendation");
        }}
      />
    </div>
  );

  // Reading and previewing as an author is not learning: no session, no events.
  if (course.is_preview) return view;
  return <LearningEventsProvider courseId={course.course.id}>{view}</LearningEventsProvider>;
}

function PlayerSkeleton() {
  return (
    <div className="mx-auto max-w-4xl space-y-4 p-8">
      <Skeleton className="aspect-video w-full rounded-xl" />
      <Skeleton className="h-6 w-1/2" />
      <Skeleton className="h-4 w-3/4" />
    </div>
  );
}

export default function LearnerLearningPage() {
  return (
    <AppShell bleed roles={["learner", "manager", "instructor", "org_admin", "system_admin"]}>
      <Suspense fallback={<PlayerSkeleton />}>
        <LearningPlayer />
      </Suspense>
    </AppShell>
  );
}
