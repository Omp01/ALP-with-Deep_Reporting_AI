"use client";

import * as React from "react";
import { CheckCircle2, Rocket } from "lucide-react";

import {
  Alert,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  ConfirmDialog,
} from "@/components/ui";
import { useToast } from "@/hooks/use-toast";
import { pluralize } from "@/lib/utils";
import { contentAdminService } from "@/services";
import type { ContentDetail } from "@/types/content-admin";

/** What publishing will do, stated before it is done, and the way back once it is. */
export function PublishPanel({
  detail,
  onChanged,
}: {
  detail: ContentDetail;
  onChanged: () => void;
}) {
  const { toastSuccess, toastError } = useToast();
  const [confirming, setConfirming] = React.useState(false);
  const [working, setWorking] = React.useState(false);

  const published = detail.status === "published";
  const approved = detail.candidates.filter((c) => c.status === "approved").length;
  const alreadyLive = detail.candidates.filter((c) => c.status === "published").length;
  const pending = detail.candidates.filter((c) => c.status === "pending").length;
  const decisions = detail.analysis?.competencies ?? [];
  const toCreate = decisions.filter((c) => c.action === "create" && !("created_at_publish" in c)).length;
  const toLink = decisions.filter((c) => c.action === "link").length;
  const { can_publish: canPublish, blockers, warnings } = detail.readiness;

  const publish = async () => {
    setWorking(true);
    try {
      const result = await contentAdminService.publish(detail.id);
      const parts = [
        result.questions_published > 0 ? pluralize(result.questions_published, "question") + " published" : null,
        result.competencies_created > 0 ? pluralize(result.competencies_created, "competency", "competencies") + " created" : null,
      ].filter(Boolean);
      toastSuccess(published ? "Changes published" : "Published to learners", parts.join(" · ") || undefined);
      setConfirming(false);
      onChanged();
    } catch (err) {
      toastError(err, "Could not publish");
    } finally {
      setWorking(false);
    }
  };

  const unpublish = async () => {
    setWorking(true);
    try {
      await contentAdminService.unpublish(detail.id);
      toastSuccess("Removed from learners", "Learner progress is kept. You can publish it again at any time.");
      onChanged();
    } catch (err) {
      toastError(err, "Could not unpublish");
    } finally {
      setWorking(false);
    }
  };

  return (
    <Card data-testid="publish-panel">
      <CardHeader>
        <CardTitle>{published ? "Live for learners" : "Publish"}</CardTitle>
        <CardDescription>
          {published
            ? "Learners can open this content."
            : "Learners see nothing until you publish. Only approved questions are included."}
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4">
        {published && (
          <Alert variant="success" icon={CheckCircle2}>
            Published{alreadyLive > 0 ? ` with ${pluralize(alreadyLive, "question")}` : ""}.
          </Alert>
        )}

        {blockers.length > 0 && (
          <Alert variant="danger" title="Cannot publish yet">
            <ul className="list-disc pl-4">
              {blockers.map((b) => (
                <li key={b}>{b}</li>
              ))}
            </ul>
          </Alert>
        )}

        {warnings.length > 0 && (
          <Alert variant="warning" title="Worth a look">
            <ul className="list-disc pl-4">
              {warnings.map((w) => (
                <li key={w}>{w}</li>
              ))}
            </ul>
          </Alert>
        )}

        <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
          <dt className="text-fg-muted">Questions to publish</dt>
          <dd className="text-right font-medium text-fg">{approved}</dd>
          <dt className="text-fg-muted">Still to review</dt>
          <dd className="text-right font-medium text-fg">{pending}</dd>
          <dt className="text-fg-muted">Competencies to create</dt>
          <dd className="text-right font-medium text-fg">{toCreate}</dd>
          <dt className="text-fg-muted">Competencies to link</dt>
          <dd className="text-right font-medium text-fg">{toLink}</dd>
        </dl>

        <div className="flex flex-wrap gap-2">
          <Button
            onClick={() => setConfirming(true)}
            disabled={!canPublish || working || (published && approved === 0)}
            loading={working && confirming}
            title={published && approved === 0 ? "Approve more questions to publish additional ones" : undefined}
          >
            <Rocket aria-hidden="true" />
            {published ? "Publish new approvals" : "Publish"}
          </Button>
          {published && (
            <Button variant="secondary" onClick={unpublish} loading={working && !confirming}>
              Unpublish
            </Button>
          )}
        </div>
      </CardContent>

      <ConfirmDialog
        open={confirming}
        onClose={() => setConfirming(false)}
        onConfirm={publish}
        loading={working}
        title={published ? "Publish the new approvals?" : "Publish to learners?"}
        confirmLabel="Publish"
        description={
          <div className="grid gap-2 text-sm">
            <p>This will:</p>
            <ul className="list-disc pl-5">
              <li>make the content visible to learners enrolled in the course;</li>
              <li>
                create {pluralize(approved, "quiz question")} from your approved questions
                {pending > 0 ? ` (${pending} unreviewed will not be included)` : ""};
              </li>
              {toCreate > 0 && <li>create {pluralize(toCreate, "new competency", "new competencies")} in your skill graph;</li>}
              {toLink > 0 && <li>attach {pluralize(toLink, "existing competency", "existing competencies")} to this content.</li>}
            </ul>
          </div>
        }
      />
    </Card>
  );
}
