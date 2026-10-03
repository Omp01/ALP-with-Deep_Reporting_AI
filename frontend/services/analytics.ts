/**
 * Deterministic Analytics Service.
 * Consumes the Phase 2 reporting analytics APIs:
 * - What Changed? (GET /api/v1/analytics/what-changed)
 * - Silent Strugglers (GET /api/v1/analytics/silent-strugglers)
 * - Learning Bottlenecks (GET /api/v1/analytics/bottlenecks)
 * - Assessment Intelligence (GET /api/v1/analytics/assessment-intelligence)
 */

import { apiClient, RequestOptions } from "@/lib/api-client";

export interface WhatChangedResponse {
  days_window: number;
  current_period: { start: string; end: string };
  previous_period: { start: string; end: string };
  competency: {
    current_avg_mastery: number | null;
    previous_avg_mastery: number | null;
    mastery_delta: number | null;
    mastery_pct_change: number | null;
    updates_count_current: number;
    updates_count_previous: number;
  };
  assessment: {
    current_accuracy_rate: number | null;
    previous_accuracy_rate: number | null;
    accuracy_delta: number | null;
    current_attempt_volume: number;
    previous_attempt_volume: number;
    current_total_responses: number;
    previous_total_responses: number;
  };
  activity: {
    current_event_count: number;
    previous_event_count: number;
    event_count_delta: number;
  };
}

export interface SilentStrugglerItem {
  user_id: string;
  learner_name: string;
  completion_percent: number;
  mastery_score: number;
  confidence_score: number;
  risk_level: string;
  competencies: { competency: string; mastery: number; trend: string }[];
  reasons: string[];
  evidence_ids: string[];
}

export interface SilentStrugglersResponse {
  thresholds: { min_completion_pct: number; max_mastery_score: number };
  total_strugglers_found: number;
  silent_strugglers: SilentStrugglerItem[];
}

export interface BottleneckModule {
  module_id: string;
  module_title: string;
  course_id: string;
  course_title: string;
  affected_learners: number;
  completion_rate: number;
  correctness_rate: number;
  retry_rate: number;
  mastery_delta: number;
  signals: string[];
  evidence_ids: string[];
  is_bottleneck: boolean;
}

export interface BottlenecksResponse {
  course_id: string | null;
  total_modules_analyzed: number;
  bottlenecks_detected: number;
  modules: BottleneckModule[];
}

export interface QuestionIntelligenceItem {
  question_id: string;
  quiz_id: string;
  quiz_title: string;
  question_text: string;
  competency_id: string | null;
  difficulty_rating: number | null;
  total_responses: number;
  correct_responses: number;
  incorrect_responses: number;
  correctness_rate: number;
  average_time_seconds: number;
  min_time_seconds: number;
  max_time_seconds: number;
  average_attempt_number: number;
}

export interface AssessmentIntelligenceResponse {
  quiz_id: string | null;
  course_id: string | null;
  total_questions_analyzed: number;
  questions: QuestionIntelligenceItem[];
}

export const analyticsService = {
  getWhatChanged(
    params?: { days?: number; course_id?: string; competency_id?: string; team_id?: string },
    options?: RequestOptions
  ) {
    return apiClient.get<WhatChangedResponse>("/api/v1/analytics/what-changed", {
      params,
      ...options,
    });
  },

  getSilentStrugglers(
    params?: { team_id?: string; min_completion_pct?: number; max_mastery_score?: number },
    options?: RequestOptions
  ) {
    return apiClient.get<SilentStrugglersResponse>("/api/v1/analytics/silent-strugglers", {
      params,
      ...options,
    });
  },

  getBottlenecks(
    params?: { course_id?: string; team_id?: string },
    options?: RequestOptions
  ) {
    return apiClient.get<BottlenecksResponse>("/api/v1/analytics/bottlenecks", {
      params,
      ...options,
    });
  },

  getAssessmentIntelligence(
    params?: { quiz_id?: string; course_id?: string; team_id?: string },
    options?: RequestOptions
  ) {
    return apiClient.get<AssessmentIntelligenceResponse>("/api/v1/analytics/assessment-intelligence", {
      params,
      ...options,
    });
  },
};
