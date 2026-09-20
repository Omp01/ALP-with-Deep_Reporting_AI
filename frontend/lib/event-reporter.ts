/**
 * Reports learner interaction events to the server, reliably and without ever getting in
 * the learner's way.
 *
 * What it does:
 *   - queues events and sends them in small batches (POST /api/v1/events/batch);
 *   - gives every event an idempotency key, so a retry after a timeout cannot double-count;
 *   - keeps events that failed to send and retries with backoff, instead of dropping them;
 *   - attaches the current learning session when it sends (not when the event happened), so
 *     if the session had to be restarted meanwhile the events still land in a live one;
 *   - flushes with `keepalive` when the page is being hidden or closed.
 *
 * What it does not do: report facts. Graded answers, completions and grades are recorded by
 * the server; the server refuses them from a browser.
 *
 * Framework-free on purpose (no React), so it can be reasoned about and tested on its own.
 */

import { ApiError } from "./api-client";

export type LearnerEventType =
  | "lesson_opened"
  | "video_started"
  | "video_paused"
  | "video_resumed"
  | "video_progress"
  | "article_opened"
  | "question_shown"
  | "hint_requested"
  | "assignment_opened";

export interface EventDraft {
  event_type: LearnerEventType;
  content_id?: string;
  question_id?: string;
  payload?: Record<string, unknown>;
  /** When it happened (ISO). Set by the caller if the event was noted before it could be queued. */
  occurred_at?: string;
}

interface QueuedEvent extends EventDraft {
  idempotency_key: string;
  timestamp: string;
}

export interface EventTransport {
  /** Send a batch. Rejects with an ApiError (or any Error) on failure. */
  send(events: Array<QueuedEvent & { session_id?: string }>, options: { keepalive: boolean }): Promise<void>;
}

export interface EventReporterOptions {
  transport: EventTransport;
  /** The session events should join right now, if one is known. */
  getSessionId: () => string | null;
  /** Called when the server says the session has ended; should start a new one. */
  onSessionInvalid?: () => Promise<void>;
  /** Milliseconds between automatic flushes. */
  flushIntervalMs?: number;
  /** Most events held while the server is unreachable; the oldest are dropped beyond this. */
  maxQueue?: number;
}

const BATCH_SIZE = 50;
const MAX_BACKOFF_MS = 30_000;

function newKey(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") return crypto.randomUUID();
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
}

/** Errors that will never succeed on retry: the event itself is wrong, not the network. */
function isRejection(error: unknown): boolean {
  return error instanceof ApiError && error.status >= 400 && error.status < 500 && error.status !== 408 && error.status !== 429;
}

export class EventReporter {
  private queue: QueuedEvent[] = [];
  private timer: ReturnType<typeof setInterval> | null = null;
  private inFlight = false;
  private failures = 0;
  private nextAttemptAt = 0;
  private disposed = false;
  /** Events discarded because the queue was full or the server rejected them. Exposed for diagnostics. */
  dropped = 0;

  constructor(private readonly options: EventReporterOptions) {
    const interval = options.flushIntervalMs ?? 2_000;
    if (interval > 0) this.timer = setInterval(() => void this.flush(), interval);
  }

  get pending(): number {
    return this.queue.length;
  }

  report(event: EventDraft): void {
    if (this.disposed) return;
    const { occurred_at, ...rest } = event;
    this.queue.push({ ...rest, idempotency_key: newKey(), timestamp: occurred_at ?? new Date().toISOString() });
    const cap = this.options.maxQueue ?? 200;
    if (this.queue.length > cap) {
      const overflow = this.queue.length - cap;
      this.queue.splice(0, overflow);
      this.dropped += overflow;
    }
  }

  /** Send what is queued. `keepalive` lets the request outlive the page (use when it is closing). */
  async flush(options: { keepalive?: boolean } = {}): Promise<void> {
    if (this.inFlight || this.queue.length === 0) return;
    if (!options.keepalive && Date.now() < this.nextAttemptAt) return;

    this.inFlight = true;
    const batch = this.queue.splice(0, BATCH_SIZE);
    try {
      const sessionId = this.options.getSessionId();
      await this.options.transport.send(
        batch.map((e) => (sessionId ? { ...e, session_id: sessionId } : e)),
        { keepalive: options.keepalive ?? false }
      );
      this.failures = 0;
      this.nextAttemptAt = 0;
    } catch (error) {
      if (error instanceof ApiError && ["session_ended", "session_not_found"].includes(error.code) && this.options.onSessionInvalid) {
        // The session went stale while the tab sat open. Start a new one and send the same events again.
        this.queue.unshift(...batch);
        try {
          await this.options.onSessionInvalid();
        } catch {
          this.backoff();
        }
      } else if (isRejection(error)) {
        // The server will not accept these however often they are sent (a bad reference, a payload
        // that fails validation). Retrying would block every event behind them.
        this.dropped += batch.length;
        if (typeof console !== "undefined") console.warn("Learning events were rejected and discarded:", error);
      } else {
        this.queue.unshift(...batch); // the network or the server is down: keep them and try again later
        this.backoff();
      }
    } finally {
      this.inFlight = false;
    }
    if (this.queue.length > 0 && this.failures === 0 && !options.keepalive) void this.flush();
  }

  private backoff(): void {
    this.failures += 1;
    this.nextAttemptAt = Date.now() + Math.min(1000 * 2 ** this.failures, MAX_BACKOFF_MS);
  }

  /** Stop the timer and make one last attempt to deliver what is left. */
  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    if (this.timer) clearInterval(this.timer);
    void this.flush({ keepalive: true });
  }
}
