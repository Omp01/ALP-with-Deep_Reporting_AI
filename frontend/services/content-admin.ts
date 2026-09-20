/**
 * Content administration API calls (services/api/app/api/v1/content_admin.py).
 * Thin typed wrappers; components own state and decisions.
 */

import { apiClient } from "@/lib/api-client";
import type {
  AnalysisUpdateInput,
  Capabilities,
  ContentDetail,
  ContentListFilters,
  ContentListResponse,
  IngestionJob,
  IngestResponse,
  PublishResponse,
  QuestionCandidate,
  QuestionInput,
} from "@/types/content-admin";

const BASE = "/api/v1/admin/content";

/** A file upload of up to 200 MB can take a while on a slow link. */
const UPLOAD_TIMEOUT_MS = 10 * 60_000;

export interface CourseSummary {
  id: string;
  title: string;
  code: string;
  status: string;
}

export interface ModuleSummary {
  id: string;
  course_id: string;
  title: string;
  sequence_order: number;
}

export interface CompetencySummary {
  id: string;
  code: string;
  name: string;
  domain: string | null;
}

export const contentAdminService = {
  capabilities(signal?: AbortSignal): Promise<Capabilities> {
    return apiClient.get<Capabilities>(`${BASE}/capabilities`, { signal });
  },

  list(filters: ContentListFilters, signal?: AbortSignal): Promise<ContentListResponse> {
    return apiClient.get<ContentListResponse>(BASE, { params: { ...filters }, signal });
  },

  get(id: string, signal?: AbortSignal): Promise<ContentDetail> {
    return apiClient.get<ContentDetail>(`${BASE}/${id}`, { signal });
  },

  job(id: string, signal?: AbortSignal): Promise<IngestionJob> {
    return apiClient.get<IngestionJob>(`${BASE}/jobs/${id}`, { signal });
  },

  uploadFile(
    file: File,
    moduleId: string,
    options: { title?: string; allowDuplicate?: boolean } = {}
  ): Promise<IngestResponse> {
    const form = new FormData();
    form.append("file", file);
    form.append("module_id", moduleId);
    if (options.title) form.append("title", options.title);
    if (options.allowDuplicate) form.append("allow_duplicate", "true");
    return apiClient.upload<IngestResponse>(`${BASE}/ingest/file`, form, {
      timeoutMs: UPLOAD_TIMEOUT_MS,
    });
  },

  addYouTube(
    url: string,
    moduleId: string,
    options: { title?: string; allowDuplicate?: boolean } = {}
  ): Promise<IngestResponse> {
    return apiClient.post<IngestResponse>(`${BASE}/ingest/youtube`, {
      url,
      module_id: moduleId,
      title: options.title || undefined,
      allow_duplicate: options.allowDuplicate ?? false,
    });
  },

  reprocess(id: string, force = false): Promise<IngestResponse> {
    return apiClient.post<IngestResponse>(`${BASE}/${id}/process`, { force });
  },

  update(
    id: string,
    changes: { title?: string; description?: string; module_id?: string }
  ): Promise<ContentDetail> {
    return apiClient.put<ContentDetail>(`${BASE}/${id}`, changes);
  },

  setTranscript(id: string, text: string, analyze = true): Promise<ContentDetail> {
    return apiClient.put<ContentDetail>(`${BASE}/${id}/transcript`, { text, analyze });
  },

  updateAnalysis(id: string, changes: AnalysisUpdateInput): Promise<ContentDetail> {
    return apiClient.put<ContentDetail>(`${BASE}/${id}/analysis`, changes);
  },

  addQuestion(id: string, question: QuestionInput): Promise<QuestionCandidate> {
    return apiClient.post<QuestionCandidate>(`${BASE}/${id}/candidates`, question);
  },

  editQuestion(candidateId: string, changes: Partial<QuestionInput>): Promise<QuestionCandidate> {
    return apiClient.put<QuestionCandidate>(`${BASE}/candidates/${candidateId}`, changes);
  },

  setQuestionStatus(
    candidateId: string,
    status: "pending" | "approved" | "rejected"
  ): Promise<QuestionCandidate> {
    return apiClient.post<QuestionCandidate>(`${BASE}/candidates/${candidateId}/status`, { status });
  },

  setQuestionsStatus(
    id: string,
    ids: string[],
    status: "pending" | "approved" | "rejected"
  ): Promise<QuestionCandidate[]> {
    return apiClient.post<QuestionCandidate[]>(`${BASE}/${id}/candidates/status`, { ids, status });
  },

  deleteQuestion(candidateId: string): Promise<void> {
    return apiClient.delete<void>(`${BASE}/candidates/${candidateId}`);
  },

  publish(id: string): Promise<PublishResponse> {
    return apiClient.post<PublishResponse>(`${BASE}/${id}/publish`);
  },

  unpublish(id: string): Promise<ContentDetail> {
    return apiClient.post<ContentDetail>(`${BASE}/${id}/unpublish`);
  },

  remove(id: string): Promise<void> {
    return apiClient.delete<void>(`${BASE}/${id}`);
  },

  // -- the course structure content is filed under (existing endpoints) -----------------------
  courses(signal?: AbortSignal): Promise<CourseSummary[]> {
    return apiClient.get<CourseSummary[]>("/api/v1/courses", { signal });
  },

  modules(courseId: string, signal?: AbortSignal): Promise<ModuleSummary[]> {
    return apiClient.get<ModuleSummary[]>(`/api/v1/courses/${courseId}/modules`, { signal });
  },

  createCourse(title: string, code: string): Promise<CourseSummary> {
    return apiClient.post<CourseSummary>("/api/v1/courses", { title, code, status: "draft" });
  },

  createModule(courseId: string, title: string, sequenceOrder: number): Promise<ModuleSummary> {
    return apiClient.post<ModuleSummary>(`/api/v1/courses/${courseId}/modules`, {
      title,
      sequence_order: sequenceOrder,
    });
  },

  competencies(signal?: AbortSignal): Promise<CompetencySummary[]> {
    return apiClient.get<CompetencySummary[]>("/api/v1/competencies", { signal });
  },
};
