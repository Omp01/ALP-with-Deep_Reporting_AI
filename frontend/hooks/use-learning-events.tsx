"use client";

import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef } from "react";

import { EventReporter, type EventDraft, type LearnerEventType } from "@/lib/event-reporter";
import { eventsService } from "@/services/events";

/** How often a still-open player tells the server the learner is here (a long reading sends no other events). */
const HEARTBEAT_MS = 60_000;

export interface LearningEvents {
  /** The current session, once started. Events sent before that join one the server starts implicitly. */
  sessionId: string | null;
  /** Report an interaction. Never throws and never blocks; failures are retried in the background. */
  report: (
    type: LearnerEventType,
    refs?: { contentId?: string | null; questionId?: string | null },
    payload?: Record<string, unknown>
  ) => void;
}

const NOOP: LearningEvents = { sessionId: null, report: () => undefined };
const Context = createContext<LearningEvents>(NOOP);

/**
 * Wraps a course player: starts (or resumes) the learner's learning session for the course, reports
 * what they do in it, keeps it alive, and ends it when the page is closed. A session that is never
 * ended (a closed laptop) is closed by the server at its last activity.
 *
 * Outside a provider `useLearningEvents()` is a no-op, so components that report events also work
 * anywhere else they are rendered.
 */
export function LearningEventsProvider({ courseId, children }: { courseId: string; children: React.ReactNode }) {
  const sessionRef = useRef<string | null>(null);
  const reporterRef = useRef<EventReporter | null>(null);
  // React runs a child's effects before its parent's. A lesson that mounts in the same render as this provider
  // reports before the reporter exists; those events wait here (with the time they happened) instead of being lost.
  const early = useRef<EventDraft[]>([]);
  const [sessionId, setSessionId] = React.useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const openSession = async () => {
      try {
        const session = await eventsService.startSession(courseId, { source: "player" });
        if (cancelled) return;
        sessionRef.current = session.session_id;
        setSessionId(session.session_id);
      } catch {
        // No session id: events are still reported and the server attaches its own implicit session.
        sessionRef.current = null;
      }
    };

    const reporter = new EventReporter({
      transport: { send: (events, options) => eventsService.reportBatch(events, options).then(() => undefined) },
      getSessionId: () => sessionRef.current,
      onSessionInvalid: openSession,
    });
    reporterRef.current = reporter;
    for (const draft of early.current.splice(0)) reporter.report(draft);
    void openSession().then(() => reporter.flush());

    const heartbeat = setInterval(() => {
      const id = sessionRef.current;
      if (!id || document.visibilityState !== "visible") return;
      eventsService.heartbeat(id).catch(() => {
        // Ended or unknown (for example after a long sleep): begin a fresh session.
        void openSession();
      });
    }, HEARTBEAT_MS);

    const onHide = () => {
      if (document.visibilityState === "hidden") void reporter.flush({ keepalive: true });
    };
    const onPageHide = () => {
      void reporter.flush({ keepalive: true });
      const id = sessionRef.current;
      if (id) void eventsService.endSession(id, { keepalive: true }).catch(() => undefined);
    };
    document.addEventListener("visibilitychange", onHide);
    window.addEventListener("pagehide", onPageHide);

    return () => {
      cancelled = true;
      clearInterval(heartbeat);
      document.removeEventListener("visibilitychange", onHide);
      window.removeEventListener("pagehide", onPageHide);
      reporter.dispose();
      reporterRef.current = null;
    };
  }, [courseId]);

  const report = useCallback<LearningEvents["report"]>((type, refs, payload) => {
    const draft: EventDraft = {
      event_type: type,
      content_id: refs?.contentId ?? undefined,
      question_id: refs?.questionId ?? undefined,
      payload,
      occurred_at: new Date().toISOString(),
    };
    if (reporterRef.current) reporterRef.current.report(draft);
    else early.current.push(draft);
  }, []);

  const value = useMemo(() => ({ sessionId, report }), [sessionId, report]);
  return <Context.Provider value={value}>{children}</Context.Provider>;
}

export function useLearningEvents(): LearningEvents {
  return useContext(Context);
}
