"use client";

import * as React from "react";
import { Plus, Trash2 } from "lucide-react";

import {
  Alert,
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Field,
  Input,
  Select,
  Textarea,
} from "@/components/ui";
import { useApi } from "@/hooks/use-api";
import { useToast } from "@/hooks/use-toast";
import { contentAdminService } from "@/services";
import type { AnalysisUpdateInput, CompetencyDecision, ContentDetail } from "@/types/content-admin";

const LEVELS = [
  { value: "beginner", label: "Beginner" },
  { value: "intermediate", label: "Intermediate" },
  { value: "advanced", label: "Advanced" },
];

const BLOOM = ["remember", "understand", "apply", "analyze", "evaluate", "create"].map((v) => ({
  value: v,
  label: v[0].toUpperCase() + v.slice(1),
}));

const ACTIONS = [
  { value: "link", label: "Use an existing competency" },
  { value: "create", label: "Create a new competency" },
  { value: "skip", label: "Do not attach" },
];

const CODE_PATTERN = /[^a-z0-9.-]+/g;

function slug(text: string): string {
  return text.toLowerCase().replace(CODE_PATTERN, "-").replace(/^-+|-+$/g, "");
}

interface Draft {
  summary: string;
  level: string;
  objectives: string[];
  competencies: CompetencyDecision[];
}

function draftFrom(detail: ContentDetail): Draft {
  const a = detail.analysis;
  return {
    summary: a?.summary ?? "",
    level: a?.level ?? "beginner",
    objectives: a?.objectives?.length ? [...a.objectives] : [],
    competencies: (a?.competencies ?? []).map((c) => ({ ...c })),
  };
}

/**
 * What the AI understood the content to teach — and the decisions that are the administrator's to make:
 * the objectives learners will see, and which competencies this content provides evidence for.
 */
export function AnalysisPanel(props: {
  detail: ContentDetail;
  locked: boolean;
  onChanged: (next: ContentDetail) => void;
}) {
  // A new analysis (retry / re-analyse / save) remounts the form so its draft restarts from it;
  // edits in progress are never overwritten by anything else.
  const { detail } = props;
  const key = `${detail.job?.id}:${detail.job?.attempts}:${detail.analysis?.provenance?.attempts ?? ""}:${detail.analysis?.edited ?? false}`;
  return <AnalysisForm key={key} {...props} />;
}

function AnalysisForm({
  detail,
  locked,
  onChanged,
}: {
  detail: ContentDetail;
  locked: boolean;
  onChanged: (next: ContentDetail) => void;
}) {
  const { toastSuccess, toastError } = useToast();
  const [draft, setDraft] = React.useState<Draft>(() => draftFrom(detail));
  const [baseline] = React.useState(() => JSON.stringify(draftFrom(detail)));
  const [saving, setSaving] = React.useState(false);

  const competencies = useApi((signal) => contentAdminService.competencies(signal));

  const dirty = JSON.stringify(draft) !== baseline;
  const analysis = detail.analysis;

  const invalid = React.useMemo(() => {
    for (const c of draft.competencies) {
      if (c.name.trim().length < 3) return "Every competency needs a name of at least 3 characters.";
      if (c.action === "link" && !c.competency_id) return `Choose which existing competency “${c.name}” refers to.`;
    }
    return null;
  }, [draft.competencies]);

  const setCompetency = (index: number, changes: Partial<CompetencyDecision>) =>
    setDraft((d) => ({
      ...d,
      competencies: d.competencies.map((c, i) => (i === index ? { ...c, ...changes } : c)),
    }));

  const save = async () => {
    setSaving(true);
    try {
      const body: AnalysisUpdateInput = {
        summary: draft.summary.trim() || undefined,
        level: draft.level as AnalysisUpdateInput["level"],
        objectives: draft.objectives.map((o) => o.trim()).filter(Boolean),
        competencies: draft.competencies.map((c) => ({
          name: c.name.trim(),
          description: c.description ?? "",
          domain: c.domain ?? null,
          bloom_level: c.bloom_level ?? "understand",
          difficulty: c.difficulty ?? 0.5,
          action: c.action,
          competency_id: c.action === "link" ? c.competency_id : null,
          code: c.action === "create" ? c.code || slug(c.name) : null,
        })),
      };
      const next = await contentAdminService.updateAnalysis(detail.id, body);
      toastSuccess("Analysis saved");
      onChanged(next);
    } catch (err) {
      toastError(err, "Could not save the analysis");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="grid gap-6">
      {!analysis && (
        <Alert variant="neutral" title="There is no analysis yet">
          Nothing has been generated for this content. You can write the learning objectives and choose the
          competencies yourself below.
        </Alert>
      )}
      {analysis?.provenance?.provider && (
        <p className="text-xs text-fg-muted">
          Drafted by {analysis.provenance.provider}
          {analysis.prompt_version ? ` (${analysis.prompt_version})` : ""}
          {analysis.edited ? " · edited by you" : ""}. Check it before publishing — it is a proposal, not a fact.
        </p>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Summary and level</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4">
          <Field label="Summary" htmlFor="analysis-summary">
            {(props) => (
              <Textarea
                {...props}
                rows={3}
                value={draft.summary}
                disabled={locked}
                onChange={(e) => setDraft({ ...draft, summary: e.target.value })}
              />
            )}
          </Field>
          <Field label="Level" htmlFor="analysis-level" className="max-w-xs">
            {(props) => (
              <Select
                {...props}
                options={LEVELS}
                value={draft.level}
                disabled={locked}
                onChange={(e) => setDraft({ ...draft, level: e.target.value })}
              />
            )}
          </Field>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Learning objectives</CardTitle>
          <CardDescription>Shown to learners on the course page. Reword, remove or add your own.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3">
          {draft.objectives.length === 0 && <p className="text-sm text-fg-muted">No objectives yet.</p>}
          {draft.objectives.map((objective, i) => (
            <div key={i} className="flex items-start gap-2">
              <Input
                aria-label={`Objective ${i + 1}`}
                value={objective}
                disabled={locked}
                maxLength={300}
                onChange={(e) =>
                  setDraft({ ...draft, objectives: draft.objectives.map((o, j) => (j === i ? e.target.value : o)) })
                }
              />
              {!locked && (
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label={`Remove objective ${i + 1}`}
                  onClick={() => setDraft({ ...draft, objectives: draft.objectives.filter((_, j) => j !== i) })}
                >
                  <Trash2 />
                </Button>
              )}
            </div>
          ))}
          {!locked && draft.objectives.length < 15 && (
            <div>
              <Button variant="secondary" size="sm" onClick={() => setDraft({ ...draft, objectives: [...draft.objectives, ""] })}>
                <Plus aria-hidden="true" /> Add objective
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Competencies</CardTitle>
          <CardDescription>
            The skills this content gives evidence for. Reusing an existing competency keeps your skill graph
            tidy; a new one is only created when you publish.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4">
          {draft.competencies.length === 0 && (
            <p className="text-sm text-fg-muted">No competencies are attached to this content.</p>
          )}
          {draft.competencies.map((c, i) => (
            <div key={i} className="grid gap-3 rounded-lg border border-border p-4" data-competency={c.name}>
              <div className="flex flex-wrap items-center gap-2">
                <Input
                  aria-label={`Competency ${i + 1} name`}
                  className="min-w-56 flex-1"
                  value={c.name}
                  disabled={locked}
                  maxLength={100}
                  onChange={(e) => setCompetency(i, { name: e.target.value })}
                />
                {c.match_score != null && c.action === "link" && (
                  <Badge variant="info" size="sm">
                    Matched an existing competency ({Math.round(c.match_score * 100)}%)
                  </Badge>
                )}
                {!locked && (
                  <Button
                    variant="ghost"
                    size="icon"
                    aria-label={`Remove competency ${i + 1}`}
                    onClick={() => setDraft({ ...draft, competencies: draft.competencies.filter((_, j) => j !== i) })}
                  >
                    <Trash2 />
                  </Button>
                )}
              </div>

              <div className="grid gap-3 sm:grid-cols-2">
                <Select
                  aria-label={`Competency ${i + 1} action`}
                  options={ACTIONS}
                  value={c.action}
                  disabled={locked}
                  onChange={(e) => {
                    const action = e.target.value as CompetencyDecision["action"];
                    setCompetency(i, {
                      action,
                      competency_id: action === "link" ? c.competency_id : null,
                      code: action === "create" ? c.code || slug(c.name) : c.code,
                    });
                  }}
                />
                {c.action === "link" && (
                  <Select
                    aria-label={`Competency ${i + 1} existing competency`}
                    placeholder="Choose a competency"
                    value={c.competency_id ?? ""}
                    disabled={locked || competencies.loading}
                    onChange={(e) => setCompetency(i, { competency_id: e.target.value })}
                    options={(competencies.data ?? []).map((x) => ({ value: x.id, label: `${x.name} (${x.code})` }))}
                  />
                )}
                {c.action === "create" && (
                  <Input
                    aria-label={`Competency ${i + 1} code`}
                    placeholder="code, e.g. sql.joins"
                    value={c.code ?? ""}
                    disabled={locked}
                    onChange={(e) => setCompetency(i, { code: e.target.value })}
                  />
                )}
              </div>

              {c.action === "create" && (
                <div className="grid gap-3 sm:grid-cols-2">
                  <Select
                    aria-label={`Competency ${i + 1} cognitive level`}
                    options={BLOOM}
                    value={c.bloom_level ?? "understand"}
                    disabled={locked}
                    onChange={(e) => setCompetency(i, { bloom_level: e.target.value })}
                  />
                  <Input
                    aria-label={`Competency ${i + 1} description`}
                    placeholder="Short description"
                    value={c.description ?? ""}
                    disabled={locked}
                    maxLength={500}
                    onChange={(e) => setCompetency(i, { description: e.target.value })}
                  />
                </div>
              )}
            </div>
          ))}
          {!locked && draft.competencies.length < 10 && (
            <div>
              <Button
                variant="secondary"
                size="sm"
                onClick={() =>
                  setDraft({
                    ...draft,
                    competencies: [...draft.competencies, { name: "", action: "link", competency_id: null, bloom_level: "understand", difficulty: 0.5 }],
                  })
                }
              >
                <Plus aria-hidden="true" /> Add competency
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      {!locked && (
        <div className="flex flex-wrap items-center justify-end gap-3">
          {invalid && dirty && <span className="text-sm text-danger">{invalid}</span>}
          <Button
            variant="secondary"
            disabled={!dirty || saving}
            onClick={() => setDraft(JSON.parse(baseline) as Draft)}
          >
            Discard changes
          </Button>
          <Button onClick={save} disabled={!dirty || Boolean(invalid)} loading={saving}>
            Save analysis
          </Button>
        </div>
      )}
    </div>
  );
}
