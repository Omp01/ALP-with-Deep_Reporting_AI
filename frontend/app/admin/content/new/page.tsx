"use client";

import React, { useCallback, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { FileUp, Link2, Plus, Sparkles } from "lucide-react";

import { AppShell, PageHeader } from "@/components/shell";
import {
  Alert,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  ErrorState,
  Field,
  Input,
  Select,
  Skeleton,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  buttonVariants,
} from "@/components/ui";
import { useApi } from "@/hooks/use-api";
import { ApiError } from "@/lib/api-client";
import { cn } from "@/lib/utils";
import { contentAdminService } from "@/services";

const ROLES = ["org_admin", "instructor"] as const;
const NEW = "__new__";

function extensionOf(name: string): string {
  const dot = name.lastIndexOf(".");
  return dot < 0 ? "" : name.slice(dot + 1).toLowerCase();
}

function formatBytes(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** A course code from its title, e.g. "Intro to SQL" -> "INTRO-TO-SQL". The administrator can change it. */
function codeFromTitle(title: string): string {
  return title
    .toUpperCase()
    .replace(/[^A-Z0-9]+/g, "-")
    .replace(/^-|-$/g, "")
    .slice(0, 30);
}

export default function AddContentPage() {
  const router = useRouter();
  const fileInput = useRef<HTMLInputElement>(null);

  const capabilities = useApi((signal) => contentAdminService.capabilities(signal));
  const courses = useApi((signal) => contentAdminService.courses(signal));

  const [source, setSource] = useState<"file" | "youtube">("file");
  const [file, setFile] = useState<File | null>(null);
  const [url, setUrl] = useState("");
  const [title, setTitle] = useState("");

  const [courseId, setCourseId] = useState("");
  const [moduleId, setModuleId] = useState("");
  const [newCourseTitle, setNewCourseTitle] = useState("");
  const [newCourseCode, setNewCourseCode] = useState("");
  const [newModuleTitle, setNewModuleTitle] = useState("");

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [duplicate, setDuplicate] = useState<{ content_id: string; message: string } | null>(null);

  const modules = useApi((signal) => contentAdminService.modules(courseId, signal), {
    enabled: Boolean(courseId) && courseId !== NEW,
    deps: [courseId],
  });

  const creatingCourse = courseId === NEW;
  const creatingModule = moduleId === NEW || creatingCourse;

  const caps = capabilities.data;
  const acceptAttr = useMemo(() => (caps ? caps.file_types.map((e) => `.${e}`).join(",") : undefined), [caps]);

  const fileProblem = useMemo(() => {
    if (!file || !caps) return null;
    const ext = extensionOf(file.name);
    if (ext === "doc" || ext === "ppt")
      return "Older Office formats (.doc, .ppt) are not supported. Save the file as .docx or .pptx and add it again.";
    if (!caps.file_types.includes(ext))
      return `.${ext || "?"} files are not supported. Supported: ${caps.file_types.join(", ")}.`;
    if (file.size === 0) return "This file is empty.";
    if (file.size > caps.max_upload_mb * 1024 * 1024)
      return `This file is ${formatBytes(file.size)}. The limit is ${caps.max_upload_mb} MB.`;
    return null;
  }, [file, caps]);

  const isMedia = file ? ["mp4", "webm", "mov", "mp3", "wav", "m4a"].includes(extensionOf(file.name)) : false;

  const pickFile = useCallback((picked: File | null) => {
    setFile(picked);
    setError(null);
    setDuplicate(null);
    if (picked) setTitle((current) => current || picked.name.replace(/\.[^.]+$/, ""));
  }, []);

  const sourceReady = source === "file" ? Boolean(file) && !fileProblem : url.trim().length > 0;
  const placementReady = creatingCourse
    ? newCourseTitle.trim().length > 0 && newCourseCode.trim().length > 0 && newModuleTitle.trim().length > 0
    : Boolean(courseId) && (moduleId === NEW ? newModuleTitle.trim().length > 0 : Boolean(moduleId));

  const submit = async (allowDuplicate = false) => {
    setSubmitting(true);
    setError(null);
    setDuplicate(null);
    try {
      // 1. make sure the place it goes exists
      let targetModule = moduleId;
      if (creatingCourse || moduleId === NEW) {
        let targetCourse = courseId;
        if (creatingCourse) {
          const created = await contentAdminService.createCourse(newCourseTitle.trim(), newCourseCode.trim());
          targetCourse = created.id;
        }
        const created = await contentAdminService.createModule(
          targetCourse,
          newModuleTitle.trim(),
          (modules.data?.length ?? 0) + 1
        );
        targetModule = created.id;
      }

      // 2. hand the material to the pipeline
      const options = { title: title.trim() || undefined, allowDuplicate };
      const result =
        source === "file" && file
          ? await contentAdminService.uploadFile(file, targetModule, options)
          : await contentAdminService.addYouTube(url.trim(), targetModule, options);
      router.push(`/admin/content/${result.content_id}`);
    } catch (err) {
      if (err instanceof ApiError && err.code === "duplicate_content") {
        const detail = err.details as { content_id?: string } | undefined;
        if (detail?.content_id) setDuplicate({ content_id: detail.content_id, message: err.message });
        else setError(err.message);
      } else {
        setError(err instanceof ApiError ? err.userMessage : "Something went wrong. Please try again.");
      }
      setSubmitting(false);
    }
  };

  return (
    <AppShell roles={[...ROLES]}>
      <PageHeader
        title="Add Content"
        description="Bring in a document, a recording or a YouTube video. Nothing reaches learners until you have reviewed and published it."
        breadcrumbs={[{ label: "Content Library", href: "/admin/content" }, { label: "Add Content" }]}
      />

      {capabilities.error ? (
        <ErrorState error={capabilities.error} onRetry={capabilities.refetch} />
      ) : (
        <div className="grid max-w-3xl gap-6">
          {caps && !caps.ai_configured && (
            <Alert variant="warning" title="No AI provider is configured">
              {caps.ai_detail} You can still add content, but objectives, competencies and questions cannot be
              generated until a provider is set up. You can write questions by hand in the review step.
            </Alert>
          )}

          <Card>
            <CardHeader>
              <CardTitle>1. Choose the source</CardTitle>
              <CardDescription>Only material you provide is analysed. Web pages are not fetched.</CardDescription>
            </CardHeader>
            <CardContent>
              <Tabs value={source} onValueChange={(v) => setSource(v as "file" | "youtube")}>
                <TabsList aria-label="Content source">
                  <TabsTrigger value="file">
                    <FileUp className="mr-2 inline size-4" aria-hidden="true" />
                    Upload a file
                  </TabsTrigger>
                  <TabsTrigger value="youtube">
                    <Link2 className="mr-2 inline size-4" aria-hidden="true" />
                    YouTube link
                  </TabsTrigger>
                </TabsList>

                <TabsContent value="file">
                  <div
                    onDragOver={(e) => e.preventDefault()}
                    onDrop={(e) => {
                      e.preventDefault();
                      pickFile(e.dataTransfer.files?.[0] ?? null);
                    }}
                    className="flex flex-col items-center gap-2 rounded-lg border-2 border-dashed border-border-strong px-6 py-10 text-center"
                  >
                    <FileUp className="size-8 text-fg-subtle" aria-hidden="true" />
                    {file ? (
                      <p className="text-sm text-fg">
                        <span className="font-medium">{file.name}</span>{" "}
                        <span className="text-fg-muted">({formatBytes(file.size)})</span>
                      </p>
                    ) : (
                      <p className="text-sm text-fg-muted">Drag a file here, or choose one.</p>
                    )}
                    <input
                      ref={fileInput}
                      id="content-file"
                      data-testid="content-file"
                      type="file"
                      accept={acceptAttr}
                      className="sr-only"
                      onChange={(e) => pickFile(e.target.files?.[0] ?? null)}
                    />
                    <Button variant="secondary" size="sm" onClick={() => fileInput.current?.click()}>
                      {file ? "Choose a different file" : "Choose file"}
                    </Button>
                    {caps ? (
                      <p className="text-xs text-fg-subtle">
                        {caps.file_types.map((e) => e.toUpperCase()).join(", ")} · up to {caps.max_upload_mb} MB
                      </p>
                    ) : (
                      <Skeleton className="h-3 w-56" />
                    )}
                  </div>
                  {fileProblem && (
                    <Alert variant="danger" className="mt-3">
                      {fileProblem}
                    </Alert>
                  )}
                  {isMedia && caps && !caps.transcription_available && !fileProblem && (
                    <Alert variant="info" className="mt-3" title="This recording cannot be transcribed automatically">
                      No transcription engine is installed on the server. The file will be stored, and you will be
                      asked to paste a transcript so it can be analysed.
                    </Alert>
                  )}
                </TabsContent>

                <TabsContent value="youtube">
                  <Field
                    label="YouTube video link"
                    htmlFor="youtube-url"
                    hint="A youtube.com or youtu.be link to a single video. The video is embedded, not copied."
                  >
                    {(props) => (
                      <Input
                        {...props}
                        type="url"
                        inputMode="url"
                        placeholder="https://www.youtube.com/watch?v=…"
                        value={url}
                        onChange={(e) => {
                          setUrl(e.target.value);
                          setDuplicate(null);
                          setError(null);
                        }}
                      />
                    )}
                  </Field>
                  <p className="mt-3 text-xs text-fg-muted">
                    Captions are used as the transcript when the video has them. If it has none, you can paste a
                    transcript in the next step.
                  </p>
                </TabsContent>
              </Tabs>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>2. Where does it go?</CardTitle>
              <CardDescription>Content lives in a module of a course.</CardDescription>
            </CardHeader>
            <CardContent className="grid gap-4">
              {courses.loading ? (
                <Skeleton className="h-9 w-full" />
              ) : courses.error ? (
                <ErrorState error={courses.error} onRetry={courses.refetch} size="sm" />
              ) : (
                <>
                  <Field label="Course" htmlFor="course" required>
                    {(props) => (
                      <Select
                        {...props}
                        placeholder="Choose a course"
                        value={courseId}
                        onChange={(e) => {
                          setCourseId(e.target.value);
                          setModuleId("");
                        }}
                        options={[
                          ...(courses.data ?? []).map((c) => ({ value: c.id, label: c.title })),
                          { value: NEW, label: "+ New course…" },
                        ]}
                      />
                    )}
                  </Field>

                  {creatingCourse && (
                    <div className="grid gap-4 sm:grid-cols-2">
                      <Field label="New course title" htmlFor="new-course-title" required>
                        {(props) => (
                          <Input
                            {...props}
                            value={newCourseTitle}
                            onChange={(e) => {
                              setNewCourseTitle(e.target.value);
                              setNewCourseCode(codeFromTitle(e.target.value));
                            }}
                          />
                        )}
                      </Field>
                      <Field label="Course code" htmlFor="new-course-code" required hint="Unique in your organisation.">
                        {(props) => (
                          <Input {...props} value={newCourseCode} onChange={(e) => setNewCourseCode(e.target.value)} />
                        )}
                      </Field>
                    </div>
                  )}

                  {courseId && !creatingCourse && (
                    <Field label="Module" htmlFor="module" required>
                      {(props) => (
                        <Select
                          {...props}
                          placeholder={modules.loading ? "Loading modules…" : "Choose a module"}
                          value={moduleId}
                          onChange={(e) => setModuleId(e.target.value)}
                          options={[
                            ...(modules.data ?? []).map((m) => ({ value: m.id, label: m.title })),
                            { value: NEW, label: "+ New module…" },
                          ]}
                        />
                      )}
                    </Field>
                  )}

                  {creatingModule && courseId && (
                    <Field label="New module title" htmlFor="new-module-title" required>
                      {(props) => (
                        <Input {...props} value={newModuleTitle} onChange={(e) => setNewModuleTitle(e.target.value)} />
                      )}
                    </Field>
                  )}
                </>
              )}

              <Field label="Title" htmlFor="title" hint="Optional. Taken from the file name or the video when left empty.">
                {(props) => <Input {...props} value={title} onChange={(e) => setTitle(e.target.value)} maxLength={255} />}
              </Field>
            </CardContent>
          </Card>

          {duplicate && (
            <Alert
              variant="warning"
              title="This looks like something you already added"
              action={
                <div className="flex gap-2">
                  <Link
                    href={`/admin/content/${duplicate.content_id}`}
                    className={cn(buttonVariants({ variant: "secondary", size: "sm" }))}
                  >
                    Open existing
                  </Link>
                  <Button size="sm" variant="secondary" onClick={() => submit(true)} disabled={submitting}>
                    Add anyway
                  </Button>
                </div>
              }
            >
              {duplicate.message}
            </Alert>
          )}
          {error && <Alert variant="danger">{error}</Alert>}

          <div className="flex items-center justify-end gap-3">
            <Link href="/admin/content" className={cn(buttonVariants({ variant: "ghost" }))}>
              Cancel
            </Link>
            <Button onClick={() => submit(false)} disabled={!sourceReady || !placementReady || submitting} loading={submitting}>
              {creatingCourse || moduleId === NEW ? <Plus aria-hidden="true" /> : <Sparkles aria-hidden="true" />}
              Add and analyse
            </Button>
          </div>
        </div>
      )}
    </AppShell>
  );
}
