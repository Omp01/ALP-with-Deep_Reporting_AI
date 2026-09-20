/**
 * Skill graph API calls. Thin, typed wrappers over the shared api-client:
 * no state, no caching, no business logic — components decide what to do
 * with the result.
 */

import { apiClient } from "@/lib/api-client";
import type { Prerequisite, SkillGraph } from "@/types";

export interface AddPrerequisiteInput {
  prerequisite_id: string;
  min_mastery: number;
  rationale?: string;
}

export const skillGraphService = {
  /** The tenant's whole graph: competencies with their depth, plus prerequisite edges. */
  getGraph(signal?: AbortSignal): Promise<SkillGraph> {
    return apiClient.get<SkillGraph>("/api/v1/competencies/graph", { signal });
  },

  /** Declare that `competencyId` requires `input.prerequisite_id`. Rejects loops with a 409. */
  addPrerequisite(competencyId: string, input: AddPrerequisiteInput): Promise<Prerequisite> {
    return apiClient.post<Prerequisite>(
      `/api/v1/competencies/${competencyId}/prerequisites`,
      input
    );
  },

  removePrerequisite(competencyId: string, prerequisiteId: string): Promise<void> {
    return apiClient.delete<void>(
      `/api/v1/competencies/${competencyId}/prerequisites/${prerequisiteId}`
    );
  },
};
