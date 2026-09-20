"use client";

import * as React from "react";
import { FileText } from "lucide-react";

import { Alert, Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Field, Textarea } from "@/components/ui";
import { useToast } from "@/hooks/use-toast";
import { contentAdminService } from "@/services";
import type { ContentDetail } from "@/types/content-admin";

const MIN_CHARS = 50;

/**
 * Paste a transcript for a video or recording that has none. It is used exactly as entered and marked as
 * manually provided; nothing is ever invented in its place.
 */
export function TranscriptPanel({
  detail,
  onChanged,
}: {
  detail: ContentDetail;
  onChanged: (next: ContentDetail) => void;
}) {
  const { toastSuccess, toastError } = useToast();
  const [text, setText] = React.useState("");
  const [saving, setSaving] = React.useState(false);

  const submit = async () => {
    setSaving(true);
    try {
      const next = await contentAdminService.setTranscript(detail.id, text.trim(), true);
      toastSuccess("Transcript saved", "The content is being analysed.");
      setText("");
      onChanged(next);
    } catch (err) {
      toastError(err, "Could not save the transcript");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card data-testid="transcript-panel">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <FileText className="size-4" aria-hidden="true" />
          {detail.has_transcript ? "Replace the transcript" : "Add a transcript"}
        </CardTitle>
        <CardDescription>
          Analysis and question drafting work from text. Paste what is said in this {detail.content_type.toLowerCase()}.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-3">
        {detail.has_transcript && (
          <Alert variant="warning">
            A transcript already exists. Saving replaces it and analyses the content again; questions you have already
            reviewed are kept.
          </Alert>
        )}
        <Field label="Transcript" htmlFor="transcript-text" hint={`At least ${MIN_CHARS} characters.`}>
          {(props) => (
            <Textarea
              {...props}
              rows={8}
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Paste the transcript here"
            />
          )}
        </Field>
        <div>
          <Button onClick={submit} disabled={text.trim().length < MIN_CHARS} loading={saving}>
            Save and analyse
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
