/**
 * Competency state, its explanation, skill gaps, risk, and written-answer review
 * (services/api/app/api/v1/mastery.py, grading.py, risks.py).
 *
 * Every number here is computed by the server from stored evidence. Nothing is estimated in the browser.
 */

import { apiClient } from "@/lib/api-client";

export type Trend = "improving" | "declining" | "stable" | "insufficient_data";

export interface CompetencyState {
  competency_id: string;
  code: string;
  name: string;
  domain: string | null;
  mastery: number;
  confidence: number;
  status: string;
  evidence_count: number;
  correct: number;
  incorrect: number;
  retries: number;
  recent_accuracy: number | null;
  time_on_task_seconds: number;
  error_distribution: Record<string, number>;
  trend: Trend;
  trend_delta: number | null;
  target_mastery: number | null;
  last_updated: string | null;
  last_evidence_id: string | null;
}

export interface EvidenceSource {
  kind: string;
  question?: string;
  quiz?: string;
  question_type?: string;
  title?: string;
}

export interface ChainStep {
  sequence: number;
  update_id: string;
  evidence_id: string;
  source: EvidenceSource;
  source_type: string;
  signal: number;
  confidence: number;
  weight: number;
  error_type: string | null;
  evidence_quote: string | null;
  difficulty: number | null;
  attempt_number: number | null;
  previous_mastery: number | null;
  new_mastery: number;
  new_confidence: number;
  occurred_at: string;
  note: string | null;
  summary: string;
}

export interface Explanation {
  state: CompetencyState;
  chain: ChainStep[];
  method: string;
  parameters: Record<string, number> | null;
  verified: boolean;
}

export interface GapSignal {
  code: string;
  description: string;
  points: number;
  value: number | null;
  threshold: number | null;
}

export interface SkillGap {
  competency_id: string;
  code: string;
  name: string;
  is_gap: boolean;
  severity: "low" | "medium" | "high" | "critical" | null;
  points: number;
  mastery: number;
  target_mastery: number;
  gap_size: number;
  signals: GapSignal[];
  reasons: string[];
  evidence_ids: string[];
  note: string | null;
}

export interface LearnerGaps {
  user_id: string;
  gaps: SkillGap[];
  not_enough_evidence: SkillGap[];
}

export interface CohortGap {
  competency_id: string;
  name: string;
  code: string | null;
  target_mastery: number;
  assessed_learners: number;
  learners_below_target: number;
  share_below_target: number;
  learners_declining: number;
  evidence_count: number;
  lowest_mastery: number;
  median_mastery: number;
}

export interface CohortGaps {
  learners_with_evidence: number;
  competencies: CohortGap[];
}

export interface RiskFactor {
  code: string;
  description: string;
  points: number;
  value: number | null;
  evidence_ids: string[];
}

export interface RiskRecord {
  id: string;
  user_id: string;
  learner_name: string;
  learner_email: string;
  course_id: string;
  course_title: string;
  risk_level: "low" | "medium" | "high" | "critical";
  risk_score: number;
  risk_factors: string[];
  risk_details: RiskFactor[];
  recommended_actions: string[];
  is_resolved: boolean;
  detected_at: string;
  updated_at: string;
}

export interface ReviewItem {
  response_id: string;
  attempt_id: string;
  attempt_number: number;
  quiz: string;
  course_id: string;
  learner: { id: string; name: string };
  question: string;
  question_type: string;
  points: number;
  expected_answer: string | null;
  rubric: { criterion: string; weight?: number; description?: string }[];
  competency: { id: string; name: string } | null;
  answer: string | null;
  grading_status: string;
  score_fraction: number | null;
  ai_suggestion: {
    source: string;
    status: string;
    signal: number | null;
    confidence: number | null;
    error_type: string | null;
    evidence_quote: string | null;
    quote_verified: boolean;
    feedback: string | null;
    why_review: string | null;
    provider: string | null;
    model: string | null;
  } | null;
  submitted_at: string | null;
}

export const ERROR_TYPES = [
  "conceptual_misunderstanding",
  "procedural_error",
  "calculation_error",
  "misreading",
  "careless_error",
  "knowledge_gap",
  "unknown",
] as const;

export const masteryService = {
  mine(signal?: AbortSignal) {
    return apiClient.get<{ user_id: string; competencies: CompetencyState[] }>("/api/v1/mastery/me", { signal });
  },
  myGaps(signal?: AbortSignal) {
    return apiClient.get<LearnerGaps>("/api/v1/mastery/me/gaps", { signal });
  },
  learner(userId: string, signal?: AbortSignal) {
    return apiClient.get<{ user_id: string; competencies: CompetencyState[] }>(`/api/v1/mastery/learners/${userId}`, { signal });
  },
  explain(userId: string, competencyId: string, signal?: AbortSignal) {
    return apiClient.get<Explanation>(`/api/v1/mastery/learners/${userId}/competencies/${competencyId}/explain`, { signal });
  },
  cohortGaps(query: { team_id?: string; course_id?: string } = {}, signal?: AbortSignal) {
    return apiClient.get<CohortGaps>("/api/v1/mastery/cohort-gaps", { params: { ...query }, signal });
  },
  parameters(signal?: AbortSignal) {
    return apiClient.get<{ method: string; description: string; confidence: string; not_evidence: string; parameters: Record<string, number> }>(
      "/api/v1/mastery/parameters",
      { signal }
    );
  },
};

export const riskService = {
  /** Active alerts for the learners the caller is responsible for. Managers see their team; admins the organisation. */
  active(signal?: AbortSignal) {
    return apiClient.get<RiskRecord[]>("/api/v1/risks", { params: { resolved: false, limit: 100 }, signal });
  },
  scan() {
    return apiClient.post<{ message?: string }>("/api/v1/risks/scan", {});
  },
  resolve(riskId: string) {
    return apiClient.put(`/api/v1/risks/${riskId}/resolve`, {});
  },
};

export const gradingService = {
  queue(query: { course_id?: string } = {}, signal?: AbortSignal) {
    return apiClient.get<{ items: ReviewItem[] }>("/api/v1/grading/queue", { params: { ...query }, signal });
  },
  review(responseId: string, body: { signal: number; error_type?: string | null; feedback?: string | null }) {
    return apiClient.post<{ response_id: string; attempt_id: string; attempt_grading_status: string; attempt_score: number; attempt_passed: boolean }>(
      `/api/v1/grading/responses/${responseId}/review`,
      body
    );
  },
};
