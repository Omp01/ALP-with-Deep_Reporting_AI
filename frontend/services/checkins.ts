/**
 * Login check-in (services/api/app/api/v1/checkins.py): an AI-written quiz on the learner's own course material,
 * a short self-report, scores and a report. Only the learner can read their own check-ins.
 */

import { apiClient } from "@/lib/api-client";

export type CheckinStatus = "generating" | "ready" | "completed" | "skipped" | "failed";

export interface CheckinQuestion {
  id: string;
  text: string;
  content_title: string | null;
  options: { id: string; text: string }[];
}

export interface Statement {
  id: string;
  text: string;
}

export interface ReviewRow {
  question_id: string;
  question: string;
  your_answer: string | null;
  correct_answer: string;
  correct: boolean;
  answered: boolean;
  explanation: string;
  source_quote: string;
  content_title: string | null;
}

export interface ConstructScore {
  label: string;
  scored: boolean;
  score?: number;
  band?: "low" | "moderate" | "high";
  higher_is: "better" | "worse";
  meaning?: string;
  previous?: number | null;
  change?: number | null;
  change_is_meaningful?: boolean;
  answered?: number;
  of?: number;
}

export interface CheckinReport {
  course_title: string | null;
  quiz: {
    correct: number;
    total: number;
    percent: number | null;
    unanswered: number;
    by_content: { name: string; correct: number; total: number }[];
    by_competency: { name: string; correct: number; total: number }[];
    review: ReviewRow[];
  };
  self_report: Record<string, ConstructScore>;
  self_report_disclaimer: string;
  observations: { text: string; basis: string[] }[];
  coaching_note: { status: "ok" | "unavailable" | "invalid" | "skipped"; note: string | null; model?: string | null; detail?: string | null; flags?: string[] };
  thresholds: Record<string, number>;
}

export interface Checkin {
  id: string;
  status: CheckinStatus;
  course: { id: string; title: string } | null;
  created_at: string;
  completed_at: string | null;
  error: { code: string; message: string } | null;
  quiz?: CheckinQuestion[];
  self_report?: { statements: Statement[]; scale: { min: number; max: number; labels: string[] }; disclaimer: string };
  report?: CheckinReport;
  provenance?: { quiz_model: string | null; items_model: string | null; prompt_version: string | null };
}

export interface CheckinSummary {
  id: string;
  status: CheckinStatus;
  created_at: string;
  course_title: string | null;
  quiz_percent: number | null;
  quiz_correct: number | null;
  quiz_total: number | null;
  self_report: Record<string, number>;
}

export const checkinsService = {
  start(fresh = true, courseId?: string) {
    return apiClient.post<Checkin>("/api/v1/checkins/start", { fresh, course_id: courseId ?? null });
  },
  get(id: string, signal?: AbortSignal) {
    return apiClient.get<Checkin>(`/api/v1/checkins/${id}`, { signal });
  },
  history(signal?: AbortSignal) {
    return apiClient.get<CheckinSummary[]>("/api/v1/checkins", { signal });
  },
  submit(id: string, quiz: Record<string, string>, selfReport: Record<string, number>) {
    return apiClient.post<Checkin>(`/api/v1/checkins/${id}/submit`, { quiz, self_report: selfReport, coaching_note: true }, { timeoutMs: 120_000 });
  },
  skip(id: string) {
    return apiClient.post<Checkin>(`/api/v1/checkins/${id}/skip`);
  },
};

/** Set by the login page: the next visit to the check-in page starts a new one, once. */
export const CHECKIN_PENDING_KEY = "checkin_pending";
export const CHECKIN_CURRENT_KEY = "checkin_current";
