/**
 * Grounded reports (services/api/app/api/v1/reports.py): four audiences, cited claims, the evidence drawer, digests.
 */

import { apiClient } from "@/lib/api-client";

export type Audience = "learner" | "team" | "ld" | "organization";
export type ClaimType = "OBSERVATION" | "CORRELATION" | "PLAUSIBLE_EXPLANATION" | "CAUSAL_CLAIM";

export interface Claim {
  claim: string;
  claim_type: ClaimType;
  evidence_ids: string[];
  metric_ids: string[];
  confidence: number;
  source: "deterministic" | "ai";
  kind?: string;
  scope?: string;
  timestamp?: string;
  status?: "accepted" | "rejected";
  flags?: string[];
}

export interface Report {
  id: string;
  audience: Audience;
  scope: { scope_label: string; period_start: string; period_end: string; scope_type: string };
  generated_by: "ai" | "deterministic";
  ai_status: "ok" | "unavailable" | "invalid" | "skipped";
  ai_note: string | null;
  model: string | null;
  summary: string | null;
  claims: Claim[];
  rejected_claims: Claim[];
  notes: string[];
  metrics: { id: string; name: string; value: number | string; unit: string; definition: string }[];
  created_at: string;
  cached: boolean;
  counts: { records: number; metrics: number; findings: number; accepted: number; rejected: number };
}

export interface EvidenceRecord {
  id: string;
  type: string;
  label: string;
  occurred_at: string | null;
  data: Record<string, unknown>;
  cited_by: string[];
  source_link: string | null;
}

export interface Digest {
  id: string;
  title: string;
  audience: string;
  generated_at: string;
  status: string;
  content: string;
  report_id: string | null;
}

export interface InvestigationResponse {
  id: string;
  question: string;
  scope: { scope_label: string; period_start: string; period_end: string; scope_type: string };
  generated_by: string;
  ai_status: "ok" | "unavailable" | "invalid" | "skipped";
  ai_note: string | null;
  model: string | null;
  summary: string | null;
  claims: Claim[];
  rejected_claims: Claim[];
  limits: string[];
  metrics: { id: string; name: string; value: number | string; unit: string; definition: string }[];
  patterns: { id: string; kind: string; statement: string; claim_type: string; evidence_ids: string[]; priority: number }[];
  created_at: string;
  counts: { records: number; metrics: number; findings: number; accepted: number; rejected: number };
}

export interface FlowchartResponse {
  title: string;
  flowchart_type: "competency_dependency" | "module_friction" | "risk_cascade";
  mermaid_code: string;
  summary: string;
  nodes: Record<string, unknown>[];
  evidence_ids: string[];
}

export const reportsService = {
  generate(body: { audience: Audience; scope_id?: string; days?: number; use_ai?: boolean; force?: boolean }) {
    return apiClient.post<Report>("/api/v1/reports/generate", body, { timeoutMs: 180_000 });
  },
  investigate(body: { question: string; team_id?: string; course_id?: string; days?: number }) {
    return apiClient.post<InvestigationResponse>("/api/v1/reports/investigate", body, { timeoutMs: 180_000 });
  },
  flowchart(body: { flowchart_type: string; team_id?: string; course_id?: string; days?: number }) {
    const payload: Record<string, unknown> = {
      flowchart_type: body.flowchart_type,
      days: body.days ?? 30,
    };
    if (body.team_id && body.team_id.trim() !== "") payload.team_id = body.team_id;
    if (body.course_id && body.course_id.trim() !== "") payload.course_id = body.course_id;
    return apiClient.post<FlowchartResponse>("/api/v1/reports/flowchart", payload);
  },

  evidence(reportId: string, evidenceId: string, signal?: AbortSignal) {
    return apiClient.get<EvidenceRecord>(`/api/v1/reports/${reportId}/evidence/${evidenceId}`, { signal });
  },
  digests(signal?: AbortSignal) {
    return apiClient.get<{ items: Digest[] }>("/api/v1/reports/digests", { signal });
  },
  generateDigest() {
    return apiClient.post<{ status: string; report_id: string | null }>("/api/v1/reports/digest/generate", {}, { timeoutMs: 180_000 });
  },
  createSchedule(body: { title: string; audience: Audience; cadence: "weekly" | "monthly"; scope_id?: string }) {
    return apiClient.post<{ id: string }>("/api/v1/reports/schedules", body);
  },
  schedules(signal?: AbortSignal) {
    return apiClient.get<{ items: { id: string; title: string; audience: string; cadence: string; next_run_at: string | null; last_run_at: string | null }[] }>("/api/v1/reports/schedules", { signal });
  },
  embedToken(body: { report: "skill-gaps" | "risks" | "summary"; scope: "team" | "organization" | "learner"; scope_id?: string }) {
    return apiClient.post<{ token: string; snippet: string }>("/api/v1/embed/tokens", body);
  },
  getLearnerPerformance(params?: { user_id?: string; course_id?: string }, signal?: AbortSignal) {
    const query = new URLSearchParams();
    if (params?.user_id) query.set("user_id", params.user_id);
    if (params?.course_id) query.set("course_id", params.course_id);
    const qs = query.toString();
    return apiClient.get<import("@/types/learning").LearnerPerformanceReport>(
      `/api/v1/reports/learner/performance${qs ? `?${qs}` : ""}`,
      { signal }
    );
  },
  getManagerPerformance(params?: { team_id?: string; course_id?: string }, signal?: AbortSignal) {
    const query = new URLSearchParams();
    if (params?.team_id) query.set("team_id", params.team_id);
    if (params?.course_id) query.set("course_id", params.course_id);
    const qs = query.toString();
    return apiClient.get<import("@/types/learning").ManagerCohortPerformanceReport>(
      `/api/v1/reports/manager/performance${qs ? `?${qs}` : ""}`,
      { signal }
    );
  },
  getPsychometricPrompt(
    stage: string,
    params?: { course_id?: string; module_id?: string; content_item_id?: string; topic?: string },
    signal?: AbortSignal
  ) {
    const query = new URLSearchParams();
    query.set("stage", stage);
    if (params?.course_id) query.set("course_id", params.course_id);
    if (params?.module_id) query.set("module_id", params.module_id);
    if (params?.content_item_id) query.set("content_item_id", params.content_item_id);
    if (params?.topic) query.set("topic", params.topic);
    return apiClient.get<{ prompt: import("@/types/learning").PsychometricQuestion | null; message?: string }>(
      `/api/v1/psychometrics/prompt?${query.toString()}`,
      { signal }
    );
  },
  submitPsychometricResponse(body: import("@/types/learning").PsychometricResponseSubmit) {
    return apiClient.post<import("@/types/learning").PsychometricResponseReceipt>(
      "/api/v1/psychometrics/response",
      body
    );
  },
  getLearnerCalibration(params?: { user_id?: string; course_id?: string }, signal?: AbortSignal) {
    const query = new URLSearchParams();
    if (params?.user_id) query.set("user_id", params.user_id);
    if (params?.course_id) query.set("course_id", params.course_id);
    const qs = query.toString();
    return apiClient.get<import("@/types/learning").LearnerCalibrationReport>(
      `/api/v1/psychometrics/learner/calibration${qs ? `?${qs}` : ""}`,
      { signal }
    );
  },
  getManagerEffectiveness(params?: { course_id?: string }, signal?: AbortSignal) {
    const query = new URLSearchParams();
    if (params?.course_id) query.set("course_id", params.course_id);
    const qs = query.toString();
    return apiClient.get<import("@/types/learning").ManagerPsychometricsEffectivenessReport>(
      `/api/v1/psychometrics/manager/effectiveness${qs ? `?${qs}` : ""}`,
      { signal }
    );
  },
};


