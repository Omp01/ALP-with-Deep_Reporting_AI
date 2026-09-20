/**
 * Content administration types. They mirror services/api/app/schemas/content_admin.py.
 */

export type ContentStatus = "draft" | "processing" | "review" | "published" | "failed" | "archived";

export type JobStatus =
  | "pending"
  | "processing"
  | "ready_for_review"
  | "needs_attention"
  | "failed"
  | "completed";

export type StageStatus = "pending" | "running" | "done" | "skipped" | "failed";

export type CandidateStatus = "pending" | "approved" | "rejected" | "published";

export interface IngestionStage {
  name: string;
  status: StageStatus;
  started_at?: string | null;
  finished_at?: string | null;
  detail?: string | null;
  error?: { code: string; message: string } | null;
}

export interface IngestionJob {
  id: string;
  content_item_id: string | null;
  source_type: string;
  file_name: string;
  status: JobStatus;
  stage: string | null;
  stages: IngestionStage[];
  error_code: string | null;
  error_message: string | null;
  attempts: number;
  created_at: string;
  updated_at: string;
}

export interface QuestionOption {
  id: string;
  text: string;
  is_correct: boolean;
}

export type QuestionKind = "multiple_choice" | "short_answer" | "open_ended";

export interface RubricCriterion {
  criterion: string;
  weight?: number;
  description?: string | null;
}

export interface QuestionCandidate {
  id: string;
  question_text: string;
  question_type: QuestionKind;
  options: QuestionOption[];
  explanation: string | null;
  /** Written questions only. Never shown to learners. */
  expected_answer: string | null;
  rubric: RubricCriterion[] | null;
  difficulty: number;
  competency_id: string | null;
  competency_name: string | null;
  source_quote: string | null;
  origin: "generated" | "manual";
  status: CandidateStatus;
  edited: boolean;
  created_at: string;
}

export type CompetencyAction = "link" | "create" | "skip";

export interface CompetencyDecision {
  name: string;
  description?: string;
  domain?: string | null;
  bloom_level?: string;
  difficulty?: number;
  action: CompetencyAction;
  competency_id?: string | null;
  code?: string | null;
  /** Set by the analysis when it matched an existing competency. */
  match_score?: number | null;
  matched_name?: string | null;
}

export interface ContentAnalysis {
  summary?: string;
  level?: string;
  objectives?: string[];
  concepts?: { name: string; explanation: string }[];
  competencies?: CompetencyDecision[];
  edited?: boolean;
  prompt_version?: string;
  provenance?: { provider?: string; model?: string; attempts?: number };
  question_rejections?: { question: string; reason: string }[];
}

export interface Readiness {
  can_publish: boolean;
  blockers: string[];
  warnings: string[];
}

export interface ContentListItem {
  id: string;
  title: string;
  content_type: string;
  source_type: string;
  status: ContentStatus;
  course_id: string | null;
  course_title: string | null;
  module_id: string;
  module_title: string | null;
  duration_seconds: number;
  job_status: JobStatus | null;
  pending_questions: number;
  approved_questions: number;
  created_at: string;
  updated_at: string;
}

export interface ContentListResponse {
  items: ContentListItem[];
  total: number;
}

export interface ContentDetail {
  id: string;
  title: string;
  description: string | null;
  content_type: string;
  source_type: string;
  source_url: string | null;
  original_filename: string | null;
  status: ContentStatus;
  course_id: string | null;
  course_title: string | null;
  module_id: string;
  module_title: string | null;
  duration_seconds: number;
  metadata: Record<string, unknown> & { warnings?: string[] };
  text_preview: string | null;
  text_length: number;
  has_transcript: boolean;
  analysis: ContentAnalysis | null;
  job: IngestionJob | null;
  candidates: QuestionCandidate[];
  readiness: Readiness;
  created_at: string;
  updated_at: string;
}

export interface Capabilities {
  file_types: string[];
  max_upload_mb: number;
  youtube: boolean;
  ai_configured: boolean;
  ai_provider: string;
  ai_model: string;
  ai_detail: string;
  transcription_available: boolean;
  embeddings_enabled: boolean;
}

export interface IngestResponse {
  content_id: string;
  job_id: string;
  status: string;
}

export interface PublishResponse {
  content_id: string;
  status: string;
  competencies_created: number;
  competencies_linked: number;
  questions_published: number;
  quiz_content_id: string | null;
}

export interface ContentListFilters {
  q?: string;
  status?: string;
  type?: string;
  source?: string;
  course_id?: string;
  module_id?: string;
  limit?: number;
  offset?: number;
}

export interface QuestionInput {
  question_text: string;
  question_type?: QuestionKind;
  options?: { text: string; is_correct: boolean }[];
  expected_answer?: string | null;
  rubric?: RubricCriterion[] | null;
  explanation?: string | null;
  difficulty?: number;
  competency_id?: string | null;
  competency_name?: string | null;
  source_quote?: string | null;
}

export interface AnalysisUpdateInput {
  summary?: string;
  level?: "beginner" | "intermediate" | "advanced";
  objectives?: string[];
  competencies?: {
    name: string;
    description?: string;
    domain?: string | null;
    bloom_level?: string;
    difficulty?: number;
    action: "link" | "create" | "skip";
    competency_id?: string | null;
    code?: string | null;
  }[];
}
