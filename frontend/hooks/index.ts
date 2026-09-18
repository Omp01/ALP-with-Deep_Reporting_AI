/**
 * Shared React hooks.
 *
 * `useAuth` and `useApi` are the two that matter most: together they remove the
 * per-page `localStorage` parsing and the ad-hoc `fetch` + `useState` blocks
 * that the pages previously each reimplemented.
 */

export { useAuth, type UseAuthResult } from "./use-auth";
export {
  useApi,
  useMutation,
  type UseApiResult,
  type UseApiOptions,
  type UseMutationResult,
} from "./use-api";
export { useToast } from "./use-toast";
export { useMediaQuery, useIsDesktop } from "./use-media-query";
