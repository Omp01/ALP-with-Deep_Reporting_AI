/**
 * Learner experience API calls: home, course overview, player, progress, enrolment.
 */

import { apiClient } from "@/lib/api-client";
import type {
  ContentProgressResult,
  CourseOverview,
  LearnerHome,
  PlayerPayload,
  ProgressReport,
} from "@/types/learning";

export const learningService = {
  home(signal?: AbortSignal): Promise<LearnerHome> {
    return apiClient.get<LearnerHome>("/api/v1/learning/home", { signal });
  },

  courseOverview(courseId: string, signal?: AbortSignal): Promise<CourseOverview> {
    return apiClient.get<CourseOverview>(`/api/v1/learning/courses/${courseId}`, { signal });
  },

  player(contentId: string, signal?: AbortSignal): Promise<PlayerPayload> {
    return apiClient.get<PlayerPayload>(`/api/v1/learning/content/${contentId}`, { signal });
  },

  /** Report progress on a lesson. Quizzes and assignments complete server-side, not through this. */
  reportProgress(contentId: string, report: ProgressReport): Promise<ContentProgressResult> {
    return apiClient.post<ContentProgressResult>(`/api/v1/progress/content/${contentId}`, report);
  },

  enroll(courseId: string): Promise<{ status: string; enrollment_id: string }> {
    return apiClient.post(`/api/v1/courses/${courseId}/enroll`);
  },
};
