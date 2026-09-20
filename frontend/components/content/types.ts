/**
 * Type definitions for the assessment runner. Lesson-item shapes live in types/learning.ts.
 */

export interface QuizOptionData {
  id: string;
  question_id: string;
  option_text: string;
  order_index: number;
  is_correct?: boolean | null;
  explanation?: string | null;
}

export interface QuizQuestionData {
  id: string;
  quiz_id: string;
  competency_id?: string | null;
  question_text: string;
  question_type: string;
  points: number;
  order_index: number;
  explanation?: string | null;
  /** Written questions: what the answer is judged on. The expected answer is never sent to learners. */
  rubric?: { criterion: string; weight?: number; description?: string }[] | null;
  options: QuizOptionData[];
}

export interface QuizMetaData {
  id: string;
  org_id?: string;
  course_id: string;
  module_id?: string | null;
  title: string;
  description?: string | null;
  time_limit_mins: number;
  passing_score: number;
  max_attempts: number;
  is_adaptive: boolean;
  questions_count: number;
  total_points: number;
  created_at?: string;
}

export interface GradedResponse {
  question_id: string;
  selected_option_id?: string | null;
  is_correct: boolean;
  points_awarded: number;
  correct_option_id?: string | null;
  explanation?: string | null;
  question_type?: string;
  grading_status?: "graded" | "needs_review";
  /** Share of the points earned, 0..1. Null while the answer waits for a person. */
  score_fraction?: number | null;
  graded_by?: "ai" | "human" | null;
  feedback?: string | null;
}

export interface QuizAttemptData {
  id: string;
  quiz_id: string;
  user_id: string;
  score: number;
  passed: boolean;
  attempt_number: number;
  started_at: string;
  completed_at?: string | null;
  /** needs_review: some written answers await a person; the score is provisional and the attempt is not passed yet. */
  grading_status?: "graded" | "needs_review";
  responses: GradedResponse[];
}
