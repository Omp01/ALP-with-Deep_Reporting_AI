"use client";

import React, { useState } from "react";
import { CalendarClock, Code2, Mail } from "lucide-react";

import { AppShell, PageHeader } from "@/components/shell";
import { Alert, Badge, Button, EmptyState, ErrorState, SkeletonText, useToast } from "@/components/ui";
import { useApi } from "@/hooks/use-api";
import { formatDateTime } from "@/lib/utils";
import { reportsService, type Audience } from "@/services/reports";

const ROLES = ["manager", "instructor", "org_admin", "system_admin"] as const;

/**
 * Scheduled reporting: digests generated from real data on a cadence, stored, and shown here. Delivery is in the app only:
 * no email is sent (no mail server is configured), and the page says so.
 */
export default function ReportsAndDigestsPage() {
  const { toast } = useToast();
  const digests = useApi((signal) => reportsService.digests(signal));
  const schedules = useApi((signal) => reportsService.schedules(signal));
  const [busy, setBusy] = useState(false);
  const [snippet, setSnippet] = useState<string | null>(null);

  const run = async () => {
    setBusy(true);
    try {
      const result = await reportsService.generateDigest();
      toast({ title: result.status === "success" ? "Digest generated" : "The digest could not be generated", variant: result.status === "success" ? "success" : "error" });
      digests.refetch();
    } catch (err) {
      toast({ title: "The digest could not be generated", description: err instanceof Error ? err.message : undefined, variant: "error" });
    } finally {
      setBusy(false);
    }
  };

  const schedule = async (audience: Audience, cadence: "weekly" | "monthly", title: string) => {
    try {
      await reportsService.createSchedule({ title, audience, cadence });
      toast({ title: "Scheduled", description: `${title} will be generated ${cadence}.`, variant: "success" });
      schedules.refetch();
    } catch (err) {
      toast({ title: "Could not schedule", description: err instanceof Error ? err.message : undefined, variant: "error" });
    }
  };

  const embed = async () => {
    try {
      setSnippet((await reportsService.embedToken({ report: "skill-gaps", scope: "team" })).snippet);
    } catch (err) {
      toast({ title: "Could not create an embed token", description: err instanceof Error ? err.message : undefined, variant: "error" });
    }
  };

  return (
    <AppShell roles={[...ROLES]}>
      <PageHeader
        title="Reports and digests"
        description="Digests are built from the same evidence as the insight pages: every number in them comes from stored data, and each finding cites its evidence."
        actions={
          <Button onClick={run} disabled={busy} data-testid="generate-digest">
            {busy ? "Generating…" : "Generate weekly digest now"}
          </Button>
        }
      />
      <Alert variant="info" className="mb-5">
        <Mail className="mr-1 inline size-4" aria-hidden="true" /> Digests are stored and shown here. No email is sent: no mail server is configured.
      </Alert>

      <section aria-labelledby="digests-title" className="mb-8">
        <h2 id="digests-title" className="mb-3 text-base font-semibold text-fg">
          Latest digests
        </h2>
        {digests.loading ? (
          <SkeletonText lines={4} />
        ) : digests.error ? (
          <ErrorState error={digests.error} onRetry={digests.refetch} />
        ) : (digests.data?.items ?? []).length === 0 ? (
          <EmptyState title="No digests yet" description="Generate one now, or schedule a weekly digest below." />
        ) : (
          <ul className="space-y-3">
            {(digests.data?.items ?? []).map((d) => (
              <li key={d.id} className="rounded-lg border border-border p-4" data-digest-id={d.id}>
                <div className="flex flex-wrap items-center gap-2 text-xs text-fg-muted">
                  <Badge variant={d.status === "success" ? "success" : "danger"} size="sm">
                    {d.status}
                  </Badge>
                  <span>{formatDateTime(d.generated_at)}</span>
                  <span>· {d.audience}</span>
                </div>
                <pre className="mt-2 whitespace-pre-wrap font-sans text-sm text-fg">{d.content}</pre>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section aria-labelledby="schedules-title" className="mb-8">
        <h2 id="schedules-title" className="mb-3 flex items-center gap-2 text-base font-semibold text-fg">
          <CalendarClock className="size-4" aria-hidden="true" /> Schedules
        </h2>
        <div className="mb-3 flex flex-wrap gap-2">
          <Button variant="secondary" size="sm" onClick={() => schedule("team", "weekly", "Weekly team digest")}>
            Schedule weekly team digest
          </Button>
          <Button variant="secondary" size="sm" onClick={() => schedule("ld", "weekly", "Weekly L&D digest")}>
            Schedule weekly L&amp;D digest
          </Button>
          <Button variant="secondary" size="sm" onClick={() => schedule("organization", "monthly", "Monthly organization capability report")}>
            Schedule monthly organization report
          </Button>
        </div>
        {(schedules.data?.items ?? []).length > 0 && (
          <ul className="space-y-1 text-sm text-fg-muted">
            {(schedules.data?.items ?? []).map((s) => (
              <li key={s.id}>
                {s.title} ({s.cadence}) · next {s.next_run_at ? formatDateTime(s.next_run_at) : "—"}
              </li>
            ))}
          </ul>
        )}
        <p className="mt-2 text-xs text-fg-muted">You can only schedule reports you are allowed to ask for; the roles that may do so are the same as for the insight pages.</p>
      </section>

      <section aria-labelledby="embed-title">
        <h2 id="embed-title" className="mb-3 flex items-center gap-2 text-base font-semibold text-fg">
          <Code2 className="size-4" aria-hidden="true" /> Embed skill gaps in another page
        </h2>
        <Button variant="secondary" size="sm" onClick={embed}>
          Create an embed snippet
        </Button>
        {snippet && (
          <pre className="mt-3 overflow-x-auto rounded-lg bg-surface-raised p-3 text-xs" data-testid="embed-snippet">
            {snippet}
          </pre>
        )}
        <p className="mt-2 text-xs text-fg-muted">The token is scoped to your team&apos;s skill gaps, expires, and works only for this widget.</p>
      </section>
    </AppShell>
  );
}
