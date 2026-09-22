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

export interface VideoCheckpoint {
  id: string;
  content_item_id: string;
  timestamp_seconds: number;
  transcript_segment?: string | null;
  question: string;
  options: CheckpointOption[];
  order_index: number;
  status: CheckpointStatus;
  selected_option_id?: string | null;
  attempt_count: number;
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
  explanation?: string | null;
  all_checkpoints_completed: boolean;
}

export interface VideoSeekValidationResponse {
  allowed: boolean;
  reason?: string | null;
  first_missed_checkpoint?: VideoCheckpoint | null;
  missed_checkpoints: VideoCheckpoint[];
}

