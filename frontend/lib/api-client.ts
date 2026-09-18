/**
 * The single HTTP entry point to the Adaptive LMS backend.
 *
 * Every network call in the app goes through this client. It handles:
 *   - base URL from NEXT_PUBLIC_API_URL (never a hardcoded host)
 *   - JWT attachment from the session
 *   - request timeouts via AbortController
 *   - FastAPI error-shape normalisation into a typed ApiError
 *   - 401 handling: clear the session once, let the UI route to /login
 *
 * Do not call `fetch` directly from a component. A raw fetch skips the timeout,
 * the error normalisation, and the 401 path, and re-introduces the hardcoded
 * `http://localhost:8000` that made the previous build undeployable.
 */

import { clearSession, getToken } from "./auth";

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/+$/, "") || "http://localhost:8000";

/** Default per-request timeout. Report generation overrides this. */
const DEFAULT_TIMEOUT_MS = 20_000;

export type QueryParams = Record<
  string,
  string | number | boolean | null | undefined
>;

export interface RequestOptions {
  params?: QueryParams;
  timeoutMs?: number;
  signal?: AbortSignal;
  /** Skip the Authorization header (used by the login call itself). */
  anonymous?: boolean;
}

/**
 * A failed API call, carrying enough structure for the UI to decide between
 * "show an inline field error", "show an error state", and "send to login".
 */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details?: unknown;

  constructor(message: string, status: number, code: string, details?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }

  /** The caller is not signed in, or the token expired. */
  get isUnauthorized(): boolean {
    return this.status === 401;
  }

  /** Signed in, but this role or tenant may not see the resource. */
  get isForbidden(): boolean {
    return this.status === 403;
  }

  get isNotFound(): boolean {
    return this.status === 404;
  }

  /** Request never completed — offline, DNS failure, or timeout. */
  get isNetworkError(): boolean {
    return this.status === 0;
  }

  get isServerError(): boolean {
    return this.status >= 500;
  }

  /** Message safe to put in front of an end user (§51: never a raw stack trace). */
  get userMessage(): string {
    if (this.isNetworkError) {
      return "Cannot reach the server. Check your connection and try again.";
    }
    if (this.isUnauthorized) {
      return "Your session has expired. Please sign in again.";
    }
    if (this.isForbidden) {
      return "You do not have permission to view this.";
    }
    if (this.isServerError) {
      return "Something went wrong on our side. Please try again in a moment.";
    }
    return this.message;
  }
}

function buildUrl(path: string, params?: QueryParams): string {
  const url = new URL(
    path.startsWith("/") ? `${API_BASE_URL}${path}` : `${API_BASE_URL}/${path}`
  );
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      // Drop unset filters rather than sending `?search=undefined`.
      if (value === undefined || value === null || value === "") continue;
      url.searchParams.append(key, String(value));
    }
  }
  return url.toString();
}

/**
 * Normalise the several error shapes FastAPI can return.
 *
 * The API emits `{"error": {"code", "message"}}` from its own handlers, but
 * `{"detail": ...}` from HTTPException and from Pydantic validation (where
 * `detail` is an array of field errors). All three must become one ApiError.
 */
async function toApiError(response: Response): Promise<ApiError> {
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    return new ApiError(
      `Request failed with status ${response.status}`,
      response.status,
      "http_error"
    );
  }

  const record = body as Record<string, unknown> | null;

  const structured = record?.error as
    | { code?: string; message?: string; details?: unknown }
    | undefined;
  if (structured?.message) {
    return new ApiError(
      structured.message,
      response.status,
      structured.code ?? "api_error",
      structured.details
    );
  }

  const detail = record?.detail;
  if (typeof detail === "string") {
    return new ApiError(detail, response.status, "api_error");
  }
  if (Array.isArray(detail)) {
    const first = detail[0] as { msg?: string; loc?: unknown[] } | undefined;
    const field = Array.isArray(first?.loc) ? first.loc.slice(1).join(".") : "";
    const msg = first?.msg ?? "Validation failed";
    return new ApiError(
      field ? `${field}: ${msg}` : msg,
      response.status,
      "validation_error",
      detail
    );
  }

  return new ApiError(
    `Request failed with status ${response.status}`,
    response.status,
    "http_error",
    body
  );
}

class ApiClient {
  constructor(private readonly baseUrl: string) {}

  private headers(anonymous: boolean, json: boolean): HeadersInit {
    const headers: Record<string, string> = {};
    if (json) headers["Content-Type"] = "application/json";
    if (!anonymous) {
      const token = getToken();
      if (token) headers["Authorization"] = `Bearer ${token}`;
    }
    return headers;
  }

  private async request<T>(
    method: string,
    path: string,
    body: unknown,
    options: RequestOptions = {},
    isFormData = false
  ): Promise<T> {
    const { params, timeoutMs = DEFAULT_TIMEOUT_MS, anonymous = false } = options;

    // Own timeout controller, chained to any caller-supplied signal so that
    // component unmount and timeout both abort the same request.
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    if (options.signal) {
      if (options.signal.aborted) controller.abort();
      else options.signal.addEventListener("abort", () => controller.abort());
    }

    let response: Response;
    try {
      response = await fetch(buildUrl(path, params), {
        method,
        headers: this.headers(anonymous, !isFormData),
        body: isFormData
          ? (body as FormData)
          : body !== undefined
            ? JSON.stringify(body)
            : undefined,
        signal: controller.signal,
      });
    } catch (err) {
      if ((err as Error)?.name === "AbortError") {
        throw new ApiError(
          `Request timed out after ${Math.round(timeoutMs / 1000)}s`,
          0,
          "timeout"
        );
      }
      throw new ApiError("Network request failed", 0, "network_error");
    } finally {
      clearTimeout(timer);
    }

    if (!response.ok) {
      const error = await toApiError(response);
      // Drop a dead token immediately so the next render sees a logged-out
      // state. Routing is the UI's job — AuthGuard reacts to the change.
      if (error.isUnauthorized) clearSession();
      throw error;
    }

    if (response.status === 204) return undefined as T;

    const contentType = response.headers.get("content-type") ?? "";
    if (!contentType.includes("application/json")) {
      return (await response.text()) as T;
    }
    return (await response.json()) as T;
  }

  get<T>(path: string, options?: RequestOptions): Promise<T> {
    return this.request<T>("GET", path, undefined, options);
  }

  post<T>(path: string, body?: unknown, options?: RequestOptions): Promise<T> {
    return this.request<T>("POST", path, body, options);
  }

  put<T>(path: string, body?: unknown, options?: RequestOptions): Promise<T> {
    return this.request<T>("PUT", path, body, options);
  }

  patch<T>(path: string, body?: unknown, options?: RequestOptions): Promise<T> {
    return this.request<T>("PATCH", path, body, options);
  }

  delete<T>(path: string, options?: RequestOptions): Promise<T> {
    return this.request<T>("DELETE", path, undefined, options);
  }

  /** Multipart upload. Content-Type is left unset so the browser adds the boundary. */
  upload<T>(path: string, formData: FormData, options?: RequestOptions): Promise<T> {
    return this.request<T>("POST", path, formData, options, true);
  }
}

export const apiClient = new ApiClient(API_BASE_URL);
export default apiClient;
