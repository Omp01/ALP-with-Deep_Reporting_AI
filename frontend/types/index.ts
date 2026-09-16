/**
 * Shared TypeScript types for the Adaptive LMS frontend.
 * These mirror the backend Pydantic schemas.
 */

// =============================================================================
// Enums
// =============================================================================

export type UserRole = "learner" | "manager" | "admin";
export type Difficulty = "beginner" | "intermediate" | "advanced";
export type ContentType = "text" | "video" | "audio" | "document" | "interactive";
export type ContentStatus = "processing" | "ready" | "error";
export type CourseStatus = "draft" | "published" | "archived";
export type CompetencyTrend = "improving" | "stable" | "declining";
export type RiskLevel = "low" | "medium" | "high" | "critical";
export type AdaptiveDecision = "remediate" | "continue" | "advance" | "skip" | "change_modality" | "revisit";
export type InsightScope = "learner" | "team" | "cohort" | "course" | "module" | "organization" | "program";
export type InsightStatus = "generated" | "validated" | "rejected";

// =============================================================================
// Auth
// =============================================================================

export interface LoginRequest {
  email: string;
  password: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
}

export interface User {
  id: string;
  tenant_id: string;
  email: string;
  first_name: string;
  last_name: string;
  role: UserRole;
  is_active: boolean;
  last_login?: string;
  created_at: string;
}

// =============================================================================
// Organization
// =============================================================================

export interface Organization {
  id: string;
  name: string;
  slug: string;
  settings?: Record<string, unknown>;
  created_at: string;
}

// =============================================================================
// Course & Content
// =============================================================================

export interface Course {
  id: string;
  tenant_id: string;
  title: string;
  description: string;
  status: CourseStatus;
  created_by: string;
  metadata?: Record<string, unknown>;
  created_at: string;
}

export interface Module {
  id: string;
  tenant_id: string;
  course_id: string;
  title: string;
  description: string;
  sort_order: number;
  difficulty: Difficulty;
  created_at: string;
}

export interface ContentItem {
  id: string;
  tenant_id: string;
  module_id: string;
  title: string;
  content_type: ContentType;
  status: ContentStatus;
  difficulty: Difficulty;
  sort_order: number;
  estimated_duration_sec?: number;
  created_at: string;
}

// =============================================================================
// Competency
// =============================================================================

export interface Competency {
  id: string;
  tenant_id: string;
  name: string;
  description: string;
  domain: string;
  difficulty: Difficulty;
  parent_id?: string;
  created_at: string;
}

export interface LearnerCompetency {
  competency_id: string;
  learner_id: string;
  competency_name?: string;
  mastery: number;
  confidence: number;
  evidence_count: number;
  recent_accuracy?: number;
  avg_response_time_ms?: number;
  retry_rate?: number;
  error_distribution?: Record<string, number>;
  trend: CompetencyTrend;
  last_updated: string;
}

// =============================================================================
// Assessment
// =============================================================================

export interface Question {
  id: string;
  assessment_id: string;
  competency_id: string;
  question_text: string;
  question_type: "multiple_choice" | "true_false" | "short_answer";
  difficulty: Difficulty;
  explanation: string;
  options: QuestionOption[];
}

export interface QuestionOption {
  id: string;
  option_text: string;
  is_correct: boolean;
  error_type?: string;
}

// =============================================================================
// Learning Event
// =============================================================================

export interface LearningEvent {
  event_id: string;
  tenant_id: string;
  learner_id: string;
  session_id: string;
  event_type: string;
  course_id?: string;
  module_id?: string;
  content_id?: string;
  competency_id?: string;
  question_id?: string;
  timestamp: string;
  duration_ms?: number;
  attempt_number?: number;
  correct?: boolean;
  error_type?: string;
  difficulty?: string;
  metadata?: Record<string, unknown>;
}

// =============================================================================
// Adaptive
// =============================================================================

export interface AdaptiveNextResponse {
  decision: AdaptiveDecision;
  reason: string;
  competency_id?: string;
  competency_name?: string;
  mastery?: number;
  confidence?: number;
  recommended_content_id?: string;
  recommended_content_title?: string;
  recommended_difficulty?: Difficulty;
  adaptation_type: string;
}

// =============================================================================
// Risk
// =============================================================================

export interface RiskScore {
  learner_id: string;
  learner_name?: string;
  risk_level: RiskLevel;
  risk_score: number;
  risk_reasons: string[];
  detected_at: string;
}

// =============================================================================
// Insight & Report
// =============================================================================

export interface InsightClaim {
  claim: string;
  confidence: number;
  evidence_ids: string[];
  supported: boolean;
}

export interface Insight {
  insight_id: string;
  scope_type: InsightScope;
  scope_id: string;
  question: string;
  claims: InsightClaim[];
  summary: string;
  recommendations: string[];
  status: InsightStatus;
  prompt_version: string;
  model_used: string;
  generation_time_ms: number;
  created_at: string;
}

export interface EvidenceDetail {
  event_id: string;
  learner_id?: string;
  question_id?: string;
  competency_id?: string;
  timestamp: string;
  event_type: string;
  correct?: boolean;
  metadata?: Record<string, unknown>;
}

export interface Report {
  id: string;
  report_type: string;
  title: string;
  content: Record<string, unknown>;
  status: string;
  created_at: string;
}

// =============================================================================
// Analytics
// =============================================================================

export interface AnalyticsData {
  mastery_trend: { date: string; mastery: number }[];
  accuracy_trend: { date: string; accuracy: number }[];
  competency_distribution: { name: string; mastery: number; confidence: number }[];
  risk_summary: { level: RiskLevel; count: number }[];
  recent_events_count: number;
  active_learners: number;
  avg_mastery: number;
  at_risk_count: number;
}

// =============================================================================
// Common
// =============================================================================

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface ApiError {
  error: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
  };
}
