"use client";

import { useEffect, useState } from "react";

import { ApiError, apiClient } from "@/lib/api-client";

export interface ObjectUrlState {
  url: string | null;
  loading: boolean;
  error: ApiError | Error | null;
}

interface Settled {
  path: string;
  url: string | null;
  error: ApiError | Error | null;
}

/**
 * Fetches an authenticated binary resource and exposes it as an object URL that an
 * <iframe>, <video> or <audio> element can load. The URL is revoked on unmount or
 * when the path changes.
 *
 * `loading` is derived (a path with no settled result yet), so no state is set
 * synchronously inside the effect.
 */
export function useAuthedObjectUrl(path: string | null): ObjectUrlState {
  const [settled, setSettled] = useState<Settled | null>(null);

  useEffect(() => {
    if (!path) return;
    const controller = new AbortController();
    let objectUrl: string | null = null;

    apiClient
      .getBlob(path, { signal: controller.signal })
      .then((blob) => {
        objectUrl = URL.createObjectURL(blob);
        setSettled({ path, url: objectUrl, error: null });
      })
      .catch((error: ApiError | Error) => {
        if (!controller.signal.aborted) setSettled({ path, url: null, error });
      });

    return () => {
      controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [path]);

  const current = settled && settled.path === path ? settled : null;
  return {
    url: current?.url ?? null,
    error: current?.error ?? null,
    loading: path !== null && current === null,
  };
}
