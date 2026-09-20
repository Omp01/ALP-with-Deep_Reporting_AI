"use client";

import React, { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { ExternalLink, RefreshCw, Trash2 } from "lucide-react";

import { AppShell, PageHeader } from "@/components/shell";
import {
  Alert,
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  ConfirmDialog,
  ErrorState,
  Field,
  Input,
  Skeleton,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  Textarea,
} from "@/components/ui";
import { AnalysisPanel } from "@/components/admin-content/analysis-panel";
import { PublishPanel } from "@/components/admin-content/publish-panel";
import { QuestionsPanel } from "@/components/admin-content/questions-panel";
import {
  ContentStateBadge,
  StageTracker,
  sourceLabel,
  typeLabel,
} from "@/components/admin-content/status";
import { TranscriptPanel } from "@/components/admin-content/transcript-panel";
import { useApi } from "@/hooks/use-api";
import { useToast } from "@/hooks/use-toast";
import { ApiError } from "@/lib/api-client";
import { formatDateTime, formatDuration, pluralize } from "@/lib/utils";
import { contentAdminService } from "@/services";
import type { ContentDetail, QuestionCandidate } from "@/types/content-admin";

const ROLES = ["org_admin", "instructor"] as const;
const POLL_MS = 2000;
/** Failures whose fix is "supply a transcript" rather than "try again". */
const TRANSCRIPT_CODES = new Set(["no_transcript", "transcription_unavailable"]);

function isRunning(detail: ContentDetail | null): boolean {
  if (!detail) return false;
  const job = detail.job?.status;
  return detail.status === "processing" || job === "pending" || job === "processing";
}

export default function ContentReviewPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { toastSuccess, toastError } = useToast();

  const { data: detail, loading, error, refetch, setData } = useApi<ContentDetail>(
    (signal) => contentAdminService.get(id, signal),
    { deps: [id] }
  );

  const [tab, setTab] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [confirmReanalyse, setConfirmReanalyse] = useState(false);
  const [busy, setBusy] = useState<"retry" | "reanalyse" | "delete" | null>(null);

  // Follow a running job until it finishes.
  const running = isRunning(detail);
  useEffect(() => {
    if (!running) return;
    const timer = setInterval(refetch, POLL_MS);
    return () => clearInterval(timer);
  }, [running, refetch]);

  // Land on the tab that needs attention first, once, when the content becomes reviewable.
  const initialTab = detail
    ? detail.candidates.some((c) => c.status === "pending")
      ? "questions"
      : detail.analysis
        ? "analysis"
        : "overview"
    : "overview";
  const activeTab = tab ?? initialTab;

  const replaceCandidate = (candidate: QuestionCandidate) =>
    detail &&
    setData({
      ...detail,
      candidates: detail.candidates.map((c) => (c.id === candidate.id ? candidate : c)),
    });

  const rerun = async (force: boolean) => {
    setBusy(force ? "reanalyse" : "retry");
    try {
      await contentAdminService.reprocess(id, force);
      setConfirmReanalyse(false);
      refetch();
    } catch (err) {
      toastError(err, force ? "Could not start the analysis" : "Could not retry");
    } finally {
      setBusy(null);
    }
  };

  const remove = async () => {
    setBusy("delete");
    try {
      await contentAdminService.remove(id);
      toastSuccess("Content deleted");
      router.push("/admin/content");
    } catch (err) {
      toastError(err, "Could not delete");
      setConfirmDelete(false);
      setBusy(null);
    }
  };

  if (loading) {
    return (
      <AppShell roles={[...ROLES]}>
        <Skeleton className="mb-6 h-8 w-72" />
        <Skeleton className="h-64 w-full" />
      </AppShell>
    );
  }

  if (error || !detail) {
    const notFound = error instanceof ApiError && error.isNotFound;
    return (
      <AppShell roles={[...ROLES]}>
        <ErrorState
          error={error}
          title={notFound ? "This content does not exist" : undefined}
          onRetry={notFound ? undefined : refetch}
        />
      </AppShell>
    );
  }

  const job = detail.job;
  const isMedia = detail.content_type === "VIDEO" || detail.content_type === "AUDIO";
  const needsTranscript = isMedia && !detail.has_transcript && !running;
  const showRetry = job && (job.status === "needs_attention" || job.status === "failed");
  const pendingCount = detail.candidates.filter((c) => c.status === "pending").length;

  return (
    <AppShell roles={[...ROLES]}>
      <PageHeader
        title={detail.title}
        breadcrumbs={[{ label: "Content Library", href: "/admin/content" }, { label: detail.title }]}
        description={
          <span className="flex flex-wrap items-center gap-2">
            <ContentStateBadge status={detail.status} job={job?.status ?? null} />
            <Badge variant="neutral">{typeLabel(detail.content_type)}</Badge>
            <span className="text-fg-muted">
              {sourceLabel(detail.source_type)}
              {detail.course_title ? ` · ${detail.course_title}` : ""}
              {detail.module_title ? ` › ${detail.module_title}` : ""}
            </span>
          </span>
        }
        actions={
          <>
            <Button
              variant="secondary"
              disabled={running}
              onClick={() => setConfirmReanalyse(true)}
            >
              <RefreshCw aria-hidden="true" /> Analyse again
            </Button>
            <Button
              variant="ghost"
              disabled={detail.status === "published" || running}
              title={detail.status === "published" ? "Unpublish before deleting" : undefined}
              onClick={() => setConfirmDelete(true)}
              aria-label="Delete content"
            >
              <Trash2 aria-hidden="true" />
            </Button>
          </>
        }
      />

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="grid min-w-0 content-start gap-6">
          {job && (running || job.status !== "completed") && (
            <Card data-testid="processing-card" data-job-status={job.status}>
              <CardHeader>
                <CardTitle>{running ? "Processing…" : "Processing steps"}</CardTitle>
              </CardHeader>
              <CardContent className="grid gap-4">
                <StageTracker stages={job.stages} />
                {job.attempts > 1 && (
                  <p className="text-xs text-fg-muted">Attempt {job.attempts}.</p>
                )}
                {!running && job.error_message && (
                  <Alert
                    variant={job.status === "failed" ? "danger" : "warning"}
                    title={job.status === "failed" ? "This content could not be processed" : "Processing did not finish"}
                    action={
                      showRetry && !TRANSCRIPT_CODES.has(job.error_code ?? "") ? (
                        <Button size="sm" variant="secondary" onClick={() => rerun(false)} loading={busy === "retry"}>
                          Retry
                        </Button>
                      ) : undefined
                    }
                  >
                    {job.error_message}
                  </Alert>
                )}
                {(detail.metadata.warnings ?? []).map((w) => (
                  <Alert key={w} variant="info">
                    {w}
                  </Alert>
                ))}
              </CardContent>
            </Card>
          )}

          {needsTranscript && <TranscriptPanel detail={detail} onChanged={setData} />}

          {running && !detail.analysis ? null : (
            <Tabs value={activeTab} onValueChange={setTab}>
              <TabsList aria-label="Review sections">
                <TabsTrigger value="questions">
                  Questions
                  {pendingCount > 0 && (
                    <Badge variant="warning" size="sm" className="ml-2">
                      {pendingCount}
                    </Badge>
                  )}
                </TabsTrigger>
                <TabsTrigger value="analysis">Analysis</TabsTrigger>
                <TabsTrigger value="overview">Details</TabsTrigger>
              </TabsList>

              <TabsContent value="questions">
                <QuestionsPanel detail={detail} onChanged={replaceCandidate} refresh={refetch} />
              </TabsContent>

              <TabsContent value="analysis">
                <AnalysisPanel detail={detail} locked={running} onChanged={setData} />
              </TabsContent>

              <TabsContent value="overview">
                <DetailsPanel detail={detail} onChanged={setData} showTranscript={isMedia && !needsTranscript} />
              </TabsContent>
            </Tabs>
          )}
        </div>

        <div className="grid content-start gap-6">
          <PublishPanel detail={detail} onChanged={refetch} />
        </div>
      </div>

      <ConfirmDialog
        open={confirmReanalyse}
        onClose={() => setConfirmReanalyse(false)}
        onConfirm={() => rerun(true)}
        loading={busy === "reanalyse"}
        title="Analyse this content again?"
        confirmLabel="Analyse again"
        description="The AI will read the material again and draft new objectives and questions. Questions you have approved or rejected are kept; questions you have not reviewed yet are replaced."
      />
      <ConfirmDialog
        open={confirmDelete}
        onClose={() => setConfirmDelete(false)}
        onConfirm={remove}
        loading={busy === "delete"}
        destructive
        title="Delete this content?"
        confirmLabel="Delete"
        description={`“${detail.title}”, its stored file and its ${pluralize(detail.candidates.length, "question candidate")} will be permanently removed.`}
      />
    </AppShell>
  );
}

/* -------------------------------------------------------------------------- */
/* Details                                                                    */
/* -------------------------------------------------------------------------- */

function DetailsPanel({
  detail,
  onChanged,
  showTranscript,
}: {
  detail: ContentDetail;
  onChanged: (next: ContentDetail) => void;
  showTranscript: boolean;
}) {
  const { toastSuccess, toastError } = useToast();
  const [title, setTitle] = useState(detail.title);
  const [description, setDescription] = useState(detail.description ?? "");
  const [saving, setSaving] = useState(false);

  const dirty = title.trim() !== detail.title || description.trim() !== (detail.description ?? "");

  const save = async () => {
    setSaving(true);
    try {
      const next = await contentAdminService.update(detail.id, { title: title.trim(), description: description.trim() });
      toastSuccess("Details saved");
      onChanged(next);
    } catch (err) {
      toastError(err, "Could not save");
    } finally {
      setSaving(false);
    }
  };

  const meta = detail.metadata as Record<string, unknown>;
  const facts: [string, React.ReactNode][] = [
    ["Source", sourceLabel(detail.source_type)],
    ["Original file", detail.original_filename ?? "—"],
    ["Length", detail.duration_seconds > 0 ? formatDuration(detail.duration_seconds) : "Unknown"],
    ["Text extracted", detail.text_length > 0 ? `${detail.text_length.toLocaleString()} characters` : "None"],
    ["Transcript", meta.transcript_source ? String(meta.transcript_source).replaceAll("_", " ") : detail.has_transcript ? "Yes" : "—"],
    ["Added", formatDateTime(detail.created_at)],
  ];

  return (
    <div className="grid gap-6">
      <Card>
        <CardHeader>
          <CardTitle>Title and description</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4">
          <Field label="Title" htmlFor="content-title" required>
            {(props) => <Input {...props} value={title} maxLength={255} onChange={(e) => setTitle(e.target.value)} />}
          </Field>
          <Field label="Description" htmlFor="content-description">
            {(props) => (
              <Textarea {...props} rows={3} maxLength={2000} value={description} onChange={(e) => setDescription(e.target.value)} />
            )}
          </Field>
          <div>
            <Button onClick={save} disabled={!dirty || title.trim().length === 0} loading={saving}>
              Save details
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>About this content</CardTitle>
        </CardHeader>
        <CardContent>
          <dl className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-[10rem_1fr]">
            {facts.map(([k, v]) => (
              <React.Fragment key={k}>
                <dt className="text-fg-muted">{k}</dt>
                <dd className="min-w-0 break-words text-fg">{v}</dd>
              </React.Fragment>
            ))}
            {detail.source_url && (
              <>
                <dt className="text-fg-muted">Link</dt>
                <dd>
                  <a
                    href={detail.source_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-primary hover:underline"
                  >
                    Open on YouTube <ExternalLink className="size-3.5" aria-hidden="true" />
                  </a>
                </dd>
              </>
            )}
          </dl>
        </CardContent>
      </Card>

      {detail.text_preview && (
        <Card>
          <CardHeader>
            <CardTitle>Extracted text</CardTitle>
          </CardHeader>
          <CardContent>
            <pre className="max-h-80 overflow-auto whitespace-pre-wrap rounded-md bg-surface p-3 text-xs leading-relaxed text-fg-muted">
              {detail.text_preview}
              {detail.text_length > detail.text_preview.length ? "\n…" : ""}
            </pre>
          </CardContent>
        </Card>
      )}

      {showTranscript && <TranscriptPanel detail={detail} onChanged={onChanged} />}
    </div>
  );
}
