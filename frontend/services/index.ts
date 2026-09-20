/**
 * Typed API service wrappers. Each wraps `lib/api-client.ts` with
 * domain-specific methods; pages call these instead of building URLs inline.
 */
export { skillGraphService, type AddPrerequisiteInput } from "./skill-graph";
export { learningService } from "./learning";
export { eventsService } from "./events";
export { masteryService, riskService, gradingService } from "./mastery";
export {
  contentAdminService,
  type CourseSummary,
  type ModuleSummary,
  type CompetencySummary,
} from "./content-admin";
