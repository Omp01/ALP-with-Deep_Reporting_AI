"use client";

import React, { useMemo, useState } from "react";
import { Activity, Clock, Users } from "lucide-react";

import { AppShell, PageHeader } from "@/components/shell";
import {
  Badge,
  Button,
  Dialog,
  EmptyState,
  ErrorState,
  Input,
  Select,
  SkeletonTable,
  Stat,
  StatGrid,
  Table,
  TableContainer,
  TBody,
  TD,
  TH,
  THead,
  TR,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui";
import { useApi } from "@/hooks/use-api";
import { apiClient } from "@/lib/api-client";
import { formatDateTime, formatDuration, pluralize } from "@/lib/utils";
import { contentAdminService, eventsService } from "@/services";
import type { LearningEventRecord, LearningSessionInfo } from "@/services/events";

const ROLES = ["org_admin", "instructor", "manager"] as const;
const PAGE = 50;

const EVENT_TYPES = [
  "lesson_opened", "content_started", "content_completed", "video_started", "video_paused", "video_resumed", "video_progress",
  "video_completed", "article_opened", "article_completed", "assessment_started", "retry_started", "question_shown",
  "question_answered", "assessment_completed", "assignment_opened", "assignment_submitted", "assignment_graded",
  "session_started", "session_completed",
];

const label = (type: string) => type.replaceAll("_", " ");

function toneOf(type: string): "neutral" | "info" | "success" | "warning" {
  if (type.endsWith("_completed") || type === "question_answered" || type === "assignment_graded") return "success";
  if (type.startsWith("session")) return "neutral";
  if (type.endsWith("_started") || type.endsWith("_opened")) return "info";
  return "neutral";
}

/** One line saying what the event was about, taken from the payload the server stored. */
function summary(e: LearningEventRecord): string {
  const p = e.payload as Record<string, unknown>;
  if (e.event_type === "question_answered") {
    const bits = [p.is_correct ? "correct" : p.answered === false ? "left blank" : "incorrect"];
    if (typeof p.response_time_ms === "number") bits.push(`${(p.response_time_ms / 1000).toFixed(1)} s`);
    if (typeof p.difficulty === "number") bits.push(`difficulty ${p.difficulty}`);
    if (p.attempt_number) bits.push(`attempt ${String(p.attempt_number)}`);
    return bits.join(" · ");
  }
  if (e.event_type === "assessment_completed") return `score ${String(p.score)}% · ${p.passed ? "passed" : "not passed"}`;
  if (e.event_type.startsWith("video_") && typeof p.position_seconds === "number") return `at ${formatDuration(p.position_seconds as number)}`;
  if (e.event_type === "content_completed" || e.event_type === "content_started") return `${String(p.title ?? p.content_type ?? "")}`;
  if (e.event_type === "session_completed") return `${String(p.reason)} · ${formatDuration(Number(p.duration_seconds ?? 0))}`;
  if (e.event_type === "assignment_graded") return `score ${String(p.score)}`;
  if (e.event_type === "lesson_opened") return `via ${String(p.source ?? "direct")}`;
  return "";
}

function useNames() {
  const users = useApi(async (signal) => apiClient.get<{ id: string; full_name: string }[]>("/api/v1/users", { params: { limit: 100 }, signal }));
  const courses = useApi((signal) => contentAdminService.courses(signal));
  return useMemo(() => {
    const user = new Map((users.data ?? []).map((u) => [u.id, u.full_name]));
    const course = new Map((courses.data ?? []).map((c) => [c.id, c.title]));
    return {
      user: (id: string) => user.get(id) ?? `Learner ${id.slice(0, 8)}`,
      course: (id: string | null) => (id ? course.get(id) ?? "Course" : "—"),
      courses: courses.data ?? [],
    };
  }, [users.data, courses.data]);
}

export default function LearningActivityPage() {
  const names = useNames();
  const [course, setCourse] = useState("");
  const [type, setType] = useState("");
  const [since, setSince] = useState("");
  const [extra, setExtra] = useState<LearningEventRecord[]>([]);
  const [cursor, setCursor] = useState<string | null | undefined>(undefined);
  const [openSession, setOpenSession] = useState<string | null>(null);

  const sinceIso = since ? new Date(since).toISOString() : undefined;

  const stats = useApi((signal) => eventsService.stats({ course_id: course || undefined, since: sinceIso }, signal), { deps: [course, sinceIso] });
  const events = useApi(
    (signal) => eventsService.events({ course_id: course || undefined, event_type: type || undefined, since: sinceIso, limit: PAGE }, signal),
    { deps: [course, type, sinceIso] }
  );
  const sessions = useApi(
    (signal) => eventsService.sessions({ course_id: course || undefined, limit: 50 }, signal),
    { deps: [course] }
  );

  const items = [...(events.data?.items ?? []), ...extra];
  const nextCursor = cursor === undefined ? events.data?.next_cursor ?? null : cursor;

  const resetPaging = () => {
    setExtra([]);
    setCursor(undefined);
  };
  const loadMore = async () => {
    if (!nextCursor) return;
    const page = await eventsService.events({ course_id: course || undefined, event_type: type || undefined, since: sinceIso, limit: PAGE, cursor: nextCursor });
    setExtra((previous) => [...previous, ...page.items]);
    setCursor(page.next_cursor);
  };

  return (
    <AppShell roles={[...ROLES]}>
      <PageHeader
        title="Learning Activity"
        description="What learners actually did, as the platform recorded it. Events are evidence: they are added, never edited or deleted. You see the learners you are responsible for."
      />

      <StatGrid>
        <Stat label="Events" value={stats.data ? stats.data.total_events.toLocaleString() : "—"} icon={Activity} />
        <Stat label="Learners" value={stats.data ? stats.data.learners.toLocaleString() : "—"} icon={Users} />
        <Stat label="Sessions" value={stats.data ? stats.data.sessions.toLocaleString() : "—"} icon={Clock} />
      </StatGrid>

      <div className="my-5 grid gap-3 sm:grid-cols-3">
        <Select
          aria-label="Course"
          value={course}
          onChange={(e) => {
            setCourse(e.target.value);
            resetPaging();
          }}
          options={[{ value: "", label: "All courses" }, ...names.courses.map((c) => ({ value: c.id, label: c.title }))]}
        />
        <Select
          aria-label="Event type"
          value={type}
          onChange={(e) => {
            setType(e.target.value);
            resetPaging();
          }}
          options={[{ value: "", label: "All event types" }, ...EVENT_TYPES.map((t) => ({ value: t, label: label(t) }))]}
        />
        <Input
          aria-label="Since"
          type="date"
          value={since}
          onChange={(e) => {
            setSince(e.target.value);
            resetPaging();
          }}
        />
      </div>

      <Tabs defaultValue="events">
        <TabsList aria-label="Activity views">
          <TabsTrigger value="events">Events</TabsTrigger>
          <TabsTrigger value="sessions">Sessions</TabsTrigger>
        </TabsList>

        <TabsContent value="events">
          {events.loading ? (
            <SkeletonTable rows={8} />
          ) : events.error ? (
            <ErrorState error={events.error} onRetry={events.refetch} />
          ) : items.length === 0 ? (
            <EmptyState icon={Activity} title="No events match" description="Nothing has been recorded for these filters yet. Events appear as learners open lessons, watch videos and answer questions." />
          ) : (
            <>
              <TableContainer>
                <Table caption="Learning events">
                  <THead>
                    <TR>
                      <TH>When</TH>
                      <TH>Learner</TH>
                      <TH>Event</TH>
                      <TH>Detail</TH>
                      <TH>Course</TH>
                    </TR>
                  </THead>
                  <TBody>
                    {items.map((e) => (
                      <TR key={e.id} onClick={e.session_id ? () => setOpenSession(e.session_id) : undefined}>
                        <TD className="whitespace-nowrap text-fg-muted">{formatDateTime(e.timestamp)}</TD>
                        <TD>{names.user(e.user_id)}</TD>
                        <TD>
                          <Badge variant={toneOf(e.event_type)} size="sm" data-event-type={e.event_type}>
                            {label(e.event_type)}
                          </Badge>
                        </TD>
                        <TD className="text-fg-muted">{summary(e)}</TD>
                        <TD className="text-fg-muted">{names.course(e.course_id)}</TD>
                      </TR>
                    ))}
                  </TBody>
                </Table>
              </TableContainer>
              <div className="mt-4 flex items-center justify-between text-sm text-fg-muted">
                <span>{pluralize(items.length, "event")} shown</span>
                {nextCursor && (
                  <Button variant="secondary" size="sm" onClick={loadMore}>
                    Load more
                  </Button>
                )}
              </div>
            </>
          )}
        </TabsContent>

        <TabsContent value="sessions">
          {sessions.loading ? (
            <SkeletonTable rows={6} />
          ) : sessions.error ? (
            <ErrorState error={sessions.error} onRetry={sessions.refetch} />
          ) : (sessions.data?.items ?? []).length === 0 ? (
            <EmptyState icon={Clock} title="No sessions yet" description="A session starts when a learner opens a course and ends when they leave or go quiet." />
          ) : (
            <TableContainer>
              <Table caption="Learning sessions">
                <THead>
                  <TR>
                    <TH>Started</TH>
                    <TH>Learner</TH>
                    <TH>Course</TH>
                    <TH>Length</TH>
                    <TH>State</TH>
                  </TR>
                </THead>
                <TBody>
                  {(sessions.data?.items ?? []).map((raw) => {
                    const s = raw as LearningSessionInfo & { user_id: string };
                    return (
                      <TR key={s.session_id} onClick={() => setOpenSession(s.session_id)}>
                        <TD className="whitespace-nowrap text-fg-muted">{formatDateTime(s.started_at)}</TD>
                        <TD>{names.user(s.user_id)}</TD>
                        <TD className="text-fg-muted">{names.course(s.course_id)}</TD>
                        <TD>{formatDuration(s.duration_seconds)}</TD>
                        <TD>
                          <Badge variant={s.state === "active" ? "success" : s.state === "idle" ? "warning" : "neutral"} size="sm">
                            {s.state === "ended" ? `ended (${s.end_reason})` : s.state}
                          </Badge>
                        </TD>
                      </TR>
                    );
                  })}
                </TBody>
              </Table>
            </TableContainer>
          )}
        </TabsContent>
      </Tabs>

      <SessionDrawer sessionId={openSession} onClose={() => setOpenSession(null)} names={names} />
    </AppShell>
  );
}

function SessionDrawer({
  sessionId,
  onClose,
  names,
}: {
  sessionId: string | null;
  onClose: () => void;
  names: { user: (id: string) => string; course: (id: string | null) => string };
}) {
  return (
    <Dialog open={sessionId !== null} onClose={onClose} title="Session" variant="drawer" size="lg">
      {sessionId && <SessionBody key={sessionId} sessionId={sessionId} names={names} />}
    </Dialog>
  );
}

function SessionBody({ sessionId, names }: { sessionId: string; names: { user: (id: string) => string; course: (id: string | null) => string } }) {
  const detail = useApi((signal) => eventsService.session(sessionId, signal), { deps: [sessionId] });
  const timeline = useApi((signal) => eventsService.sessionEvents(sessionId, signal), { deps: [sessionId] });

  if (detail.loading || timeline.loading) return <SkeletonTable rows={5} />;
  if (detail.error || !detail.data) return <ErrorState error={detail.error} onRetry={detail.refetch} />;
  const s = detail.data;

  return (
    <div className="space-y-5" data-testid="session-detail">
      <div>
        <p className="text-sm font-medium text-fg">{names.user(s.user_id)}</p>
        <p className="text-xs text-fg-muted">
          {names.course(s.course_id)} · started {formatDateTime(s.started_at)} · {formatDuration(s.duration_seconds)}
          {s.ended_at ? ` · ended (${s.end_reason})` : ` · ${s.state}`}
        </p>
      </div>

      <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
        {[
          ["Events", s.summary.events],
          ["Items touched", s.summary.content_items_touched],
          ["Questions answered", s.summary.questions_answered],
          ["Answered correctly", s.summary.questions_correct],
        ].map(([k, v]) => (
          <div key={String(k)} className="rounded-lg border border-border p-3">
            <dt className="text-xs text-fg-muted">{k}</dt>
            <dd className="text-lg font-semibold text-fg">{v}</dd>
          </div>
        ))}
      </dl>

      <ol className="space-y-2" aria-label="Session timeline">
        {(timeline.data?.items ?? []).map((e) => (
          <li key={e.id} className="flex items-start gap-3 text-sm" data-event-type={e.event_type}>
            <span className="w-20 shrink-0 pt-0.5 text-xs tabular-nums text-fg-muted">
              {new Date(e.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
            </span>
            <span className="min-w-0">
              <Badge variant={toneOf(e.event_type)} size="sm">
                {label(e.event_type)}
              </Badge>
              {summary(e) && <span className="ml-2 text-fg-muted">{summary(e)}</span>}
            </span>
          </li>
        ))}
      </ol>
    </div>
  );
}
