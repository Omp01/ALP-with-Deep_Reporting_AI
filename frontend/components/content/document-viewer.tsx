"use client";

import React, { useEffect } from "react";
import { CheckCircle2, Download, FileText } from "lucide-react";

import { Badge, Button, Spinner } from "@/components/ui";
import { useAuthedObjectUrl } from "@/hooks/use-object-url";
import type { ProgressReporter } from "@/hooks/use-progress-reporter";
import type { PlayerItem } from "@/types/learning";
import { Markdown } from "./markdown";

/**
 * Shows an uploaded document. PDFs render inline; other formats offer a download,
 * alongside any text that was extracted from them.
 */
export function DocumentViewer({
  item,
  completed,
  reporter,
}: {
  item: PlayerItem;
  completed: boolean;
  reporter: ProgressReporter;
}) {
  const media = item.media;
  const file = useAuthedObjectUrl(media?.provider === "file" ? media.url : null);
  const isPdf = media?.mime_type === "application/pdf";

  useEffect(() => {
    if (completed) return;
    reporter.setActive(true);
    return () => reporter.setActive(false);
  }, [reporter, completed]);

  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <header className="border-b border-border pb-5">
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <Badge variant="info">Document</Badge>
          {completed && (
            <Badge variant="success">
              <CheckCircle2 className="mr-1 size-3" aria-hidden="true" />
              Completed
            </Badge>
          )}
        </div>
        <h2 className="text-2xl font-semibold tracking-tight text-fg">{item.title}</h2>
        {item.description && <p className="mt-2 text-sm text-fg-muted">{item.description}</p>}
      </header>

      {file.loading && (
        <div className="flex h-64 items-center justify-center rounded-xl border border-border bg-surface">
          <Spinner size="lg" />
        </div>
      )}

      {file.error && (
        <p role="alert" className="rounded-lg border border-warning-border bg-warning-light px-4 py-3 text-sm text-fg">
          The document could not be loaded. Try again shortly.
        </p>
      )}

      {file.url && isPdf && (
        <iframe title={item.title} src={file.url} className="h-[75vh] w-full rounded-xl border border-border bg-surface" />
      )}

      {file.url && !isPdf && (
        <div className="flex flex-wrap items-center gap-3 rounded-xl border border-border bg-surface p-4">
          <FileText className="size-5 text-fg-muted" aria-hidden="true" />
          <p className="min-w-0 flex-1 text-sm text-fg-muted">
            This format cannot be previewed in the browser.
          </p>
          <a
            href={file.url}
            download={item.title}
            className="inline-flex h-8 items-center gap-1.5 rounded-md border border-border bg-surface-elevated px-3 text-xs font-medium text-fg hover:border-border-strong"
          >
            <Download className="size-3.5" aria-hidden="true" /> Download
          </a>
        </div>
      )}

      {item.text_content && (
        <details className="rounded-xl border border-border bg-surface-elevated p-4" open={!file.url && !file.loading}>
          <summary className="cursor-pointer text-sm font-medium text-fg">Text extracted from this document</summary>
          <Markdown source={item.text_content} className="mt-3" />
        </details>
      )}

      {!completed && (
        <div className="flex justify-end">
          <Button variant="secondary" size="sm" onClick={() => void reporter.complete()}>
            <CheckCircle2 aria-hidden="true" /> Mark as complete
          </Button>
        </div>
      )}
    </div>
  );
}
