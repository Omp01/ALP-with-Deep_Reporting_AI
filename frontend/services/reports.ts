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

export const reportsService = {
  generate(body: { audience: Audience; scope_id?: string; days?: number; use_ai?: boolean; force?: boolean }) {
    return apiClient.post<Report>("/api/v1/reports/generate", body, { timeoutMs: 180_000 });
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
};
