"use client";

import React, { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { FileStack, Plus, Search } from "lucide-react";

import { AppShell, PageHeader } from "@/components/shell";
import {
  Badge,
  Button,
  EmptyState,
  ErrorState,
  Input,
  Select,
  SkeletonTable,
  TableContainer,
  Table,
  TBody,
  TD,
  TH,
  THead,
  TR,
  buttonVariants,
} from "@/components/ui";
import { ContentStateBadge, sourceLabel, typeLabel } from "@/components/admin-content/status";
import { useApi } from "@/hooks/use-api";
import { cn, formatDuration, formatRelativeTime, pluralize } from "@/lib/utils";
import { contentAdminService } from "@/services";

const PAGE_SIZE = 20;
const ADMIN_ROLES = ["org_admin", "instructor"] as const;

const TYPE_OPTIONS = [
  { value: "", label: "All types" },
  { value: "video", label: "Video" },
  { value: "audio", label: "Audio" },
  { value: "document", label: "Document" },
  { value: "article", label: "Article" },
  { value: "quiz", label: "Quiz" },
];

const STATUS_OPTIONS = [
  { value: "", label: "All statuses" },
  { value: "processing", label: "Processing" },
  { value: "review", label: "In review" },
  { value: "published", label: "Published" },
  { value: "failed", label: "Failed" },
];

const SOURCE_OPTIONS = [
  { value: "", label: "All sources" },
  { value: "upload", label: "Uploads" },
  { value: "youtube", label: "YouTube" },
];

function useDebounced<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(id);
  }, [value, delayMs]);
  return debounced;
}

export default function ContentLibraryPage() {
  const router = useRouter();
  const [search, setSearch] = useState("");
  const [type, setType] = useState("");
  const [status, setStatus] = useState("");
  const [source, setSource] = useState("");
  const [courseId, setCourseId] = useState("");
  const [moduleId, setModuleId] = useState("");
  const [page, setPage] = useState(0);
  const query = useDebounced(search.trim(), 250);

  const courses = useApi((signal) => contentAdminService.courses(signal));
  const modules = useApi((signal) => contentAdminService.modules(courseId, signal), {
    enabled: Boolean(courseId),
    deps: [courseId],
  });

  const { data, loading, refreshing, error, refetch } = useApi(
    (signal) =>
      contentAdminService.list(
        {
          q: query,
          type,
          status,
          source,
          course_id: courseId,
          module_id: moduleId,
          limit: PAGE_SIZE,
          offset: page * PAGE_SIZE,
        },
        signal
      ),
    { deps: [query, type, status, source, courseId, moduleId, page] }
  );

  // While anything is processing the list refreshes itself, so statuses are never stale.
  const anyProcessing = useMemo(
    () => data?.items.some((i) => i.status === "processing") ?? false,
    [data]
  );
  useEffect(() => {
    if (!anyProcessing) return;
    const id = setInterval(refetch, 3000);
    return () => clearInterval(id);
  }, [anyProcessing, refetch]);

  const filtered = Boolean(query || type || status || source || courseId || moduleId);
  const reset = () => {
    setSearch("");
    setType("");
    setStatus("");
    setSource("");
    setCourseId("");
    setModuleId("");
    setPage(0);
  };
  const changing = (setter: (v: string) => void) => (value: string) => {
    setter(value);
    setPage(0);
  };

  const total = data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <AppShell roles={[...ADMIN_ROLES]}>
      <PageHeader
        title="Content Library"
        description="Everything learners can be taught from. Add material, check what the AI extracted from it, then publish."
        actions={
          <Link href="/admin/content/new" className={cn(buttonVariants({ variant: "primary" }))}>
            <Plus aria-hidden="true" /> Add Content
          </Link>
        }
      />

      <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-6">
        <div className="relative sm:col-span-2">
          <Search
            className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-fg-subtle"
            aria-hidden="true"
          />
          <Input
            aria-label="Search content"
            placeholder="Search by title"
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(0);
            }}
            className="pl-9"
          />
        </div>
        <Select aria-label="Type" options={TYPE_OPTIONS} value={type} onChange={(e) => changing(setType)(e.target.value)} />
        <Select aria-label="Status" options={STATUS_OPTIONS} value={status} onChange={(e) => changing(setStatus)(e.target.value)} />
        <Select aria-label="Source" options={SOURCE_OPTIONS} value={source} onChange={(e) => changing(setSource)(e.target.value)} />
        <Select
          aria-label="Course"
          value={courseId}
          onChange={(e) => {
            setCourseId(e.target.value);
            setModuleId("");
            setPage(0);
          }}
          options={[
            { value: "", label: "All courses" },
            ...(courses.data ?? []).map((c) => ({ value: c.id, label: c.title })),
          ]}
        />
        {courseId && (
          <Select
            aria-label="Module"
            value={moduleId}
            onChange={(e) => changing(setModuleId)(e.target.value)}
            options={[
              { value: "", label: "All modules" },
              ...(modules.data ?? []).map((m) => ({ value: m.id, label: m.title })),
            ]}
          />
        )}
      </div>

      {loading ? (
        <SkeletonTable rows={6} />
      ) : error ? (
        <ErrorState error={error} onRetry={refetch} />
      ) : !data || data.items.length === 0 ? (
        filtered ? (
          <EmptyState
            icon={Search}
            title="No content matches these filters"
            description="Try a different search, or clear the filters."
            action={<Button variant="secondary" onClick={reset}>Clear filters</Button>}
          />
        ) : (
          <EmptyState
            icon={FileStack}
            title="No content yet"
            description="Upload a document or recording, or add a YouTube video. The platform reads it, proposes objectives, competencies and questions, and waits for your review."
            action={
              <Link href="/admin/content/new" className={cn(buttonVariants({ variant: "primary" }))}>
                <Plus aria-hidden="true" /> Add Content
              </Link>
            }
          />
        )
      ) : (
        <>
          <TableContainer className={refreshing ? "opacity-80 transition-opacity" : undefined}>
            <Table caption="Content library">
              <THead>
                <TR>
                  <TH>Title</TH>
                  <TH>Type</TH>
                  <TH>Course / module</TH>
                  <TH>Status</TH>
                  <TH>Questions</TH>
                  <TH>Updated</TH>
                </TR>
              </THead>
              <TBody>
                {data.items.map((item) => (
                  <TR key={item.id} onClick={() => router.push(`/admin/content/${item.id}`)}>
                    <TD>
                      <Link
                        href={`/admin/content/${item.id}`}
                        className="font-medium text-fg hover:text-primary"
                        onClick={(e) => e.stopPropagation()}
                      >
                        {item.title}
                      </Link>
                      <div className="mt-0.5 text-xs text-fg-muted">
                        {sourceLabel(item.source_type)}
                        {item.duration_seconds > 0 && ` · ${formatDuration(item.duration_seconds)}`}
                      </div>
                    </TD>
                    <TD>
                      <Badge variant="neutral" size="sm">{typeLabel(item.content_type)}</Badge>
                    </TD>
                    <TD>
                      <div className="text-fg">{item.course_title ?? "—"}</div>
                      <div className="text-xs text-fg-muted">{item.module_title ?? ""}</div>
                    </TD>
                    <TD>
                      <ContentStateBadge status={item.status} job={item.job_status} />
                    </TD>
                    <TD className="text-fg-muted">
                      {item.approved_questions + item.pending_questions === 0 ? (
                        "—"
                      ) : (
                        <>
                          {item.approved_questions} approved
                          {item.pending_questions > 0 && (
                            <span className="text-warning">
                              {" · "}
                              {pluralize(item.pending_questions, "question")} to review
                            </span>
                          )}
                        </>
                      )}
                    </TD>
                    <TD className="whitespace-nowrap text-fg-muted">{formatRelativeTime(item.updated_at)}</TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          </TableContainer>

          <div className="mt-4 flex items-center justify-between text-sm text-fg-muted">
            <span>
              {total} {total === 1 ? "item" : "items"}
            </span>
            {pages > 1 && (
              <div className="flex items-center gap-2">
                <Button variant="secondary" size="sm" disabled={page === 0} onClick={() => setPage(page - 1)}>
                  Previous
                </Button>
                <span>
                  Page {page + 1} of {pages}
                </span>
                <Button variant="secondary" size="sm" disabled={page + 1 >= pages} onClick={() => setPage(page + 1)}>
                  Next
                </Button>
              </div>
            )}
          </div>
        </>
      )}
    </AppShell>
  );
}
