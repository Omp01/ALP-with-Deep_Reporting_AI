/**
 * Learning sessions and event reporting (services/api/app/api/v1/learning_sessions.py, events.py).
 */

import { apiClient } from "@/lib/api-client";
import type { EventDraft } from "@/lib/event-reporter";

export interface LearningSessionInfo {
  session_id: string;
  course_id: string | null;
  status?: "created" | "resumed";
  state: "active" | "idle" | "ended";
  started_at: string;
  last_activity_at: string;
  ended_at: string | null;
  end_reason: string | null;
  duration_seconds: number;
}

export interface LearningEventRecord {
  id: string;
  event_type: string;
  user_id: string;
  session_id: string | null;
  course_id: string | null;
  module_id: string | null;
  content_id: string | null;
  assessment_id: string | null;
  question_id: string | null;
  competency_id: string | null;
  payload: Record<string, unknown>;
  timestamp: string;
  received_at: string | null;
}

export interface SessionDetail extends LearningSessionInfo {
  user_id: string;
  context: Record<string, unknown>;
  summary: {
    events: number;
    by_type: Record<string, number>;
    content_items_touched: number;
    questions_answered: number;
    questions_correct: number;
  };
}

export interface EventQuery {
  user_id?: string;
  session_id?: string;
  course_id?: string;
  content_id?: string;
  competency_id?: string;
  event_type?: string;
  since?: string;
  until?: string;
  order?: "asc" | "desc";
  limit?: number;
  cursor?: string;
}

export const eventsService = {
  startSession(courseId: string, context: Record<string, unknown> = {}): Promise<LearningSessionInfo> {
    return apiClient.post<LearningSessionInfo>("/api/v1/learning/sessions/start", { course_id: courseId, context });
  },

  heartbeat(sessionId: string): Promise<LearningSessionInfo> {
    return apiClient.post<LearningSessionInfo>(`/api/v1/learning/sessions/${sessionId}/heartbeat`);
  },

  /** `keepalive` lets the request finish even while the page is being closed. */
  endSession(sessionId: string, options: { keepalive?: boolean } = {}): Promise<LearningSessionInfo> {
    return apiClient.post<LearningSessionInfo>(`/api/v1/learning/sessions/${sessionId}/end`, {}, { keepalive: options.keepalive });
  },

  reportBatch(events: Array<EventDraft & { idempotency_key: string; timestamp: string; session_id?: string }>, options: { keepalive?: boolean } = {}) {
    return apiClient.post("/api/v1/events/batch", { events }, { keepalive: options.keepalive });
  },

  // ---- reading the store (admins, managers, and learners for their own) -------------------------
  events(query: EventQuery, signal?: AbortSignal): Promise<{ items: LearningEventRecord[]; next_cursor: string | null }> {
    return apiClient.get("/api/v1/events", { params: { ...query }, signal });
  },

  sessions(
    query: { user_id?: string; course_id?: string; active?: boolean; limit?: number; offset?: number },
    signal?: AbortSignal
  ): Promise<{ items: LearningSessionInfo[] & { user_id?: string }[] }> {
    return apiClient.get("/api/v1/learning/sessions", { params: { ...query }, signal });
  },

  session(sessionId: string, signal?: AbortSignal): Promise<SessionDetail> {
    return apiClient.get<SessionDetail>(`/api/v1/learning/sessions/${sessionId}`, { signal });
  },

  sessionEvents(sessionId: string, signal?: AbortSignal) {
    return apiClient.get<{ session: LearningSessionInfo; items: LearningEventRecord[]; next_cursor: string | null }>(
      `/api/v1/learning/sessions/${sessionId}/events`,
      { params: { limit: 500 }, signal }
    );
  },

  stats(query: { course_id?: string; since?: string; until?: string }, signal?: AbortSignal) {
    return apiClient.get<{
      total_events: number;
      breakdown: Record<string, number>;
      by_day: { date: string; count: number }[];
      learners: number;
      sessions: number;
    }>("/api/v1/events/stats", { params: { ...query }, signal });
  },
};
