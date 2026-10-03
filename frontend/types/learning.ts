/**
 * Types for the learner experience API (services/api/app/schemas/learning.py).
 * A value that cannot be known is `null` or an empty list — never a placeholder.
 */

export type ItemKind = "lesson" | "assessment" | "assignment";
export type ProgressStatus = "not_started" | "in_progress" | "completed";

export interface ItemSummary {
  id: string;
  module_id: string;
  title: string;
  content_type: string;
  kind: ItemKind;
  source_type: string;
  /** 0 when the length is unknown (e.g. a YouTube video). */
  duration_seconds: number;
  order_index: number;
  publication_status: string;
  progress_status: ProgressStatus;
  progress_percent: number;
  quiz_id: string | null;
  assignment_id: string | null;
}

export interface ModuleOverview {
  id: string;
  title: string;
  description: string | null;
  sequence_order: number;
  lessons: number;
  assessments: number;
  total_items: number;
  completed_items: number;
  known_duration_seconds: number;
  items: ItemSummary[];
}

export interface CompetencyDeveloped {
  id: string;
  code: string;
  name: string;
  description: string | null;
  domain: string | null;
  difficulty: number;
  target_mastery: number;
  /** null when the learner has no evidence yet. */
  mastery: number | null;
  confidence: number | null;
}

export interface PrerequisiteRequirement {
  competency_id: string;
  code: string;
  name: string;
  required_for: string[];
  min_mastery: number;
  mastery: number | null;
  /** null when the learner has no evidence for it. */
  met: boolean | null;
}

export interface ProgressOverview {
  total_items: number;
  completed_items: number;
  percent: number;
  time_spent_seconds: number;
  resume_item_id: string | null;
  resume_item_title: string | null;
}

export interface CourseHeader {
  id: string;
  title: string;
  code: string;
  description: string | null;
  status: string;
  category: string;
  difficulty: string;
  thumbnail_url: string | null;
  instructor_name: string | null;
  rating: number | null;
  duration_minutes: number | null;
  enrollment_count: number;
  module_count: number;
  item_count: number;
}

export interface CourseOverview {
  course: CourseHeader;
  is_enrolled: boolean;
  enrollment_status: string | null;
  is_preview: boolean;
  objectives: string[];
  objectives_source: "content_analysis" | "competency_descriptions" | "none";
  competencies: CompetencyDeveloped[];
  prerequisites: PrerequisiteRequirement[];
  modules: ModuleOverview[];
  progress: ProgressOverview;
}

// --- player ---------------------------------------------------------------------------------

export interface MediaInfo {
  provider: "youtube" | "html5_video" | "html5_audio" | "file";
  video_id: string | null;
  url: string | null;
  mime_type: string | null;
}

export interface AssignmentInfo {
  id: string;
  instructions: string;
  difficulty: string;
  max_score: number;
  rubric: Record<string, unknown>;
  submission_status: string | null;
  submission_text: string | null;
  submission_url: string | null;
  submitted_at: string | null;
  score: number | null;
  feedback: string | null;
}

export interface PlayerItem {
  id: string;
  course_id: string;
  module_id: string;
  title: string;
  description: string | null;
  content_type: string;
  kind: ItemKind;
  source_type: string;
  duration_seconds: number;
  text_content: string | null;
  transcript: string | null;
  media: MediaInfo | null;
  quiz_id: string | null;
  assignment: AssignmentInfo | null;
  competency_names: string[];
}

export interface PlayerProgress {
  status: ProgressStatus;
  progress_percent: number;
  position_seconds: number;
  time_spent_seconds: number;
}

export interface PlayerPayload {
  item: PlayerItem;
  progress: PlayerProgress;
  course_title: string;
  module_title: string;
  position: number;
  total: number;
  previous_id: string | null;
  next_id: string | null;
}

// --- home -----------------------------------------------------------------------------------

export interface ContinueLearning {
  course_id: string;
  course_title: string;
  module_title: string | null;
  item_id: string | null;
  item_title: string | null;
  item_type: string | null;
  progress_percent: number;
  last_activity_at: string | null;
}

export interface InProgressCourse {
  course_id: string;
  title: string;
  category: string;
  difficulty: string;
  thumbnail_url: string | null;
  progress_percent: number;
  completed_items: number;
  total_items: number;
}

export interface Recommendation {
  kind: "content" | "course";
  reason_type: "weak_competency" | "popular_in_org" | "available";
  reason: string;
  course_id: string;
  course_title: string;
  content_id: string | null;
  content_title: string | null;
  content_type: string | null;
  competency_id: string | null;
  competency_name: string | null;
  mastery: number | null;
}

export interface HomeCompetency {
  id: string;
  name: string;
  domain: string | null;
  mastery: number;
  confidence: number;
  evidence_count: number;
  updated_at: string;
}

export interface ActivityItem {
  event_type: string;
  label: string;
  course_title: string | null;
  timestamp: string;
}

export interface HomeInsight {
  id: string;
  narrative: string;
  created_at: string;
  model_used: string;
}

export interface LearnerHome {
  continue_learning: ContinueLearning | null;
  in_progress: InProgressCourse[];
  recommendations: Recommendation[];
  competencies: HomeCompetency[];
  recent_activity: ActivityItem[];
  insight: HomeInsight | null;
  stats: {
    enrolled_courses: number;
    completed_courses: number;
    completed_items: number;
    time_spent_seconds: number;
  };
}

export interface ProgressReport {
  status: ProgressStatus;
  progress_percent: number;
  /** Seconds of active learning since the previous report. */
  time_spent_seconds: number;
  position_seconds?: number;
}

export interface ContentProgressResult {
  id: string;
  status: ProgressStatus;
  progress_percent: number;
  time_spent_seconds: number;
  position_seconds: number;
}

// --- interactive video learning -------------------------------------------------------------

export interface CheckpointOption {
  id: string;
  text: string;
}

export type CheckpointStatus = "pending" | "displayed" | "answered" | "correct" | "incorrect";

export interface CheckpointRemediation {
  topic: string;
  video_title: string;
  content_item_id: string;
  timestamp_start_seconds: number;
  timestamp_end_seconds: number;
  section_label: string;
  explanation?: string | null;
  action_url?: string | null;
}

export interface VideoCheckpoint {
  id: string;
  content_item_id: string;
  timestamp_seconds: number;
  timestamp_start_seconds?: number | null;
  timestamp_end_seconds?: number | null;
  topic?: string | null;
  transcript_segment?: string | null;
  question: string;
  options: CheckpointOption[];
  order_index: number;
  max_score?: number;
  status: CheckpointStatus;
  selected_option_id?: string | null;
  attempt_count: number;
  score?: number;
  formula_id?: string | null;
  calculation_details?: Record<string, unknown> | null;
  correct_option_id?: string | null;
  explanation?: string | null;
}

export interface VideoCheckpointsPayload {
  content_item_id: string;
  total_checkpoints: number;
  completed_checkpoints: number;
  checkpoints: VideoCheckpoint[];
}

export interface VideoCheckpointAnswerResponse {
  checkpoint_id: string;
  is_correct: boolean;
  status: "correct" | "incorrect";
  selected_option_id: string;
  correct_option_id: string;
  score?: number;
  max_score?: number;
  attempt_number?: number;
  formula_id?: string;
  formula_version?: string;
  calculation_details?: Record<string, any> | null;
  reason?: string | null;
  remediation?: CheckpointRemediation | null;
  explanation?: string | null;
  all_checkpoints_completed: boolean;
}

export interface VideoSeekValidationResponse {
  allowed: boolean;
  reason?: string | null;
  first_missed_checkpoint?: VideoCheckpoint | null;
  missed_checkpoints: VideoCheckpoint[];
}

// --- performance reports & score transparency ---------------------------------

export interface QuestionAttemptDetail {
  id: string;
  title: string;
  assessment_type: "flashcard" | "quiz" | "assignment";
  topic?: string | null;
  attempts: number;
  first_attempt_correct: boolean;
  score: number;
  max_score: number;
  status: string;
  answered_at?: string | null;
  calculation_details?: Record<string, any> | null;
  remediation?: CheckpointRemediation | null;
}

export interface TopicMasteryItem {
  topic: string;
  mastery_percent: number;
  total_questions: number;
  correct_count: number;
  average_attempts: number;
  status: "strong" | "developing" | "weak";
}

export interface LearningEvidenceIndexDetail {
  lei_score: number;
  formula_version: string;
  weights: Record<string, number>;
  components: Record<string, { raw_value: number; normalized_weight: number; contribution: number }>;
}

export interface LearnerPerformanceReport {
  user_id: string;
  user_name: string;
  user_email?: string | null;
  course_id?: string | null;
  course_title?: string | null;
  overall_score: number;
  quiz_score?: number | null;
  assignment_score?: number | null;
  flashcard_score?: number | null;
  weights_used: Record<string, number>;
  first_attempt_accuracy: number;
  average_attempts: number;
  total_items_attempted: number;
  questions_requiring_retries: number;
  topic_mastery: TopicMasteryItem[];
  strong_topics: string[];
  weak_topics: string[];
  improvement_trend: "improving" | "stable" | "declining";
  attempt_history: QuestionAttemptDetail[];
  lei_score?: number | null;
  lei_detail?: LearningEvidenceIndexDetail | null;
  confidence_score?: number | null;
  confidence_gap?: number | null;
  calibration_quadrant?: "calibrated_mastery" | "blind_spot" | "underestimated_competence" | "accurate_struggle" | null;
  neutral_recommendation?: string | null;
}

export interface ManagerCohortLearnerSummary {
  user_id: string;
  user_name: string;
  user_email?: string | null;
  overall_score: number;
  first_attempt_accuracy: number;
  average_attempts: number;
  items_completed: number;
  status: "on_track" | "at_risk" | "needs_review";
}

export interface CohortWeakTopic {
  topic: string;
  struggling_learner_count: number;
  avg_attempts: number;
  avg_accuracy: number;
}

export interface ManagerCohortPerformanceReport {
  cohort_size: number;
  avg_overall_score: number;
  avg_first_attempt_accuracy: number;
  avg_attempts_per_item: number;
  learners_requiring_attention: ManagerCohortLearnerSummary[];
  cohort_weak_topics: CohortWeakTopic[];
  learner_roster: ManagerCohortLearnerSummary[];
  cohort_calibration_distribution?: Record<string, number> | null;
  flagged_topics_count?: number;
}

// Psychometric Framework Types
export type LearningStage =
  | "before_course"
  | "during_course"
  | "after_topic"
  | "after_video"
  | "after_assessment"
  | "end_of_module"
  | "end_of_course";

export type PsychometricConstruct =
  | "confidence"
  | "perceived_understanding"
  | "cognitive_effort"
  | "learning_difficulty"
  | "application_readiness"
  | "retention_confidence"
  | "engagement"
  | "self_assessed_mastery"
  | "reflection"
  | "motivation";

export interface PsychometricQuestion {
  id: string;
  stage: LearningStage;
  construct: PsychometricConstruct;
  question_text: string;
  scale_type: string;
  scale_min: number;
  scale_max: number;
  scale_labels?: Record<string, string> | null;
  course_id?: string | null;
  module_id?: string | null;
  content_item_id?: string | null;
  topic?: string | null;
  cooldown_seconds: number;
}

export interface PsychometricResponseSubmit {
  question_id: string;
  raw_response: { value: number | string | boolean };
  course_id?: string | null;
  module_id?: string | null;
  content_item_id?: string | null;
  topic?: string | null;
}

export interface PsychometricResponseReceipt {
  response_id: string;
  question_id: string;
  stage: string;
  construct: string;
  raw_response: Record<string, any>;
  normalized_score: number;
  recorded_at: string;
  acknowledgment_message: string;
}

export interface LearnerTopicProgressionItem {
  stage: string;
  status: string;
  confidence_score?: number | null;
  perceived_understanding?: number | null;
  objective_score?: number | null;
  updated_at: string;
}

export interface LearnerCalibrationReport {
  user_id: string;
  course_id?: string | null;
  average_confidence?: number | null;
  objective_performance?: number | null;
  confidence_gap?: number | null;
  calibration_quadrant?: "calibrated_mastery" | "blind_spot" | "underestimated_competence" | "accurate_struggle" | null;
  neutral_recommendation?: string | null;
  lei_score?: number | null;
  lei_detail?: LearningEvidenceIndexDetail | null;
  total_prompts_answered: number;
  stage_progression: LearnerTopicProgressionItem[];
}

export interface ContentFrictionItem {
  course_id?: string | null;
  module_id?: string | null;
  topic?: string | null;
  content_friction_index: number;
  is_flagged: boolean;
  total_learner_signals: number;
  breakdown: Record<string, number>;
}

export interface ManagerPsychometricsEffectivenessReport {
  cohort_size: number;
  cohort_calibration_distribution: Record<string, number>;
  flagged_friction_topics: ContentFrictionItem[];
  avg_cohort_lei: number;
  avg_cohort_confidence: number;
}

