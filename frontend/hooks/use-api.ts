"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError } from "@/lib/api-client";

export interface UseApiResult<T> {
  data: T | null;
  /** True during the first load only — drives skeletons. */
  loading: boolean;
  /** True during a background refetch — drives a subtle inline indicator. */
  refreshing: boolean;
  error: ApiError | Error | null;
  /** True when the request succeeded and returned nothing to show. */
  isEmpty: boolean;
  refetch: () => void;
  /** Replace the cached value locally, e.g. after a successful mutation. */
  setData: (value: T | null) => void;
}

export interface UseApiOptions<T> {
  /** Re-runs the fetch when any of these change. Same contract as a dep array. */
  deps?: unknown[];
  /** Skip fetching — for a request that depends on a value not yet available. */
  enabled?: boolean;
  /** Decides whether a successful response counts as empty. */
  isEmpty?: (data: T) => boolean;
}

function defaultIsEmpty(data: unknown): boolean {
  if (data == null) return true;
  if (Array.isArray(data)) return data.length === 0;
  return false;
}

/**
 * Loads data for a component, tracking the four states every data view needs:
 * loading, error, empty, and populated.
 *
 * The distinction between `loading` and `refreshing` is what stops a page from
 * flashing back to skeletons on every refetch — first load shows skeletons,
 * subsequent loads keep the current data on screen while the new data arrives.
 *
 * In-flight requests are aborted on unmount and superseded by newer ones, so a
 * slow response can never overwrite a fresher one.
 *
 *   const { data, loading, error, refetch } = useApi(
 *     (signal) => apiClient.get<Course[]>("/api/v1/courses", { signal }),
 *     { deps: [orgId] }
 *   );
 */
export function useApi<T>(
  fetcher: (signal: AbortSignal) => Promise<T>,
  options: UseApiOptions<T> = {}
): UseApiResult<T> {
  const { deps = [], enabled = true, isEmpty: isEmptyFn = defaultIsEmpty } = options;

  const [data, setData] = useState<T | null>(null);
  const [internalLoading, setInternalLoading] = useState(enabled);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<ApiError | Error | null>(null);

  // Held in refs so `run` stays referentially stable across renders.
  const fetcherRef = useRef(fetcher);
  useEffect(() => {
    fetcherRef.current = fetcher;
  });
  const hasLoaded = useRef(false);
  const controllerRef = useRef<AbortController | null>(null);

  const run = useCallback(async () => {
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;

    if (hasLoaded.current) setRefreshing(true);
    else setInternalLoading(true);
    setError(null);

    try {
      const result = await fetcherRef.current(controller.signal);
      if (controller.signal.aborted) return;
      setData(result);
      hasLoaded.current = true;
    } catch (err) {
      if (controller.signal.aborted) return;
      // An abort surfaces as a timeout ApiError only when the client timed out;
      // a unmount-driven abort is filtered above.
      setError(err instanceof Error ? err : new Error("Request failed"));
    } finally {
      if (!controller.signal.aborted) {
        setInternalLoading(false);
        setRefreshing(false);
      }
    }
  }, []);

  useEffect(() => {
    if (!enabled) {
      return;
    }
    void Promise.resolve().then(run);
    return () => controllerRef.current?.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- caller-supplied deps
  }, [enabled, run, ...deps]);

  const loading = enabled && internalLoading;

  return {
    data,
    loading,
    refreshing,
    error,
    isEmpty: !loading && !error && data !== null && isEmptyFn(data),
    refetch: run,
    setData,
  };
}

export interface UseMutationResult<TArgs extends unknown[], TResult> {
  mutate: (...args: TArgs) => Promise<TResult | undefined>;
  loading: boolean;
  error: ApiError | Error | null;
  reset: () => void;
}

/**
 * Runs a write request, tracking its in-flight and error state.
 *
 * Returns `undefined` rather than throwing when the request fails, so a click
 * handler does not need its own try/catch; inspect `error`, or pass `onError`.
 */
export function useMutation<TArgs extends unknown[], TResult>(
  mutator: (...args: TArgs) => Promise<TResult>,
  handlers: {
    onSuccess?: (result: TResult) => void;
    onError?: (error: ApiError | Error) => void;
  } = {}
): UseMutationResult<TArgs, TResult> {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ApiError | Error | null>(null);

  const handlersRef = useRef(handlers);
  const mutatorRef = useRef(mutator);
  useEffect(() => {
    handlersRef.current = handlers;
    mutatorRef.current = mutator;
  });

  const mutate = useCallback(async (...args: TArgs) => {
    setLoading(true);
    setError(null);
    try {
      const result = await mutatorRef.current(...args);
      handlersRef.current.onSuccess?.(result);
      return result;
    } catch (err) {
      const normalised = err instanceof Error ? err : new Error("Request failed");
      setError(normalised);
      handlersRef.current.onError?.(normalised);
      return undefined;
    } finally {
      setLoading(false);
    }
  }, []);

  const reset = useCallback(() => setError(null), []);

  return { mutate, loading, error, reset };
}
