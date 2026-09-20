"use client";

import React, { useMemo, useState } from "react";
import { GitBranch, Plus, Search, X } from "lucide-react";

import { AppShell, PageHeader } from "@/components/shell";
import {
  Badge,
  Button,
  Card,
  CardContent,
  ConfirmDialog,
  Dialog,
  EmptyState,
  ErrorState,
  Field,
  Input,
  Select,
  SkeletonCard,
  Textarea,
} from "@/components/ui";
import { ApiError } from "@/lib/api-client";
import { useApi } from "@/hooks/use-api";
import { useToast } from "@/hooks/use-toast";
import { skillGraphService } from "@/services";
import type {
  PrerequisiteCycleDetail,
  SkillGraph,
  SkillGraphNode,
} from "@/types";

const DEFAULT_MIN_MASTERY_PCT = 60;

function percent(value: number): string {
  return `${Math.round(value * 100)}%`;
}

/** "SQL Joins → Filtering → SQL Basics → SQL Joins" for a cycle returned by the API. */
function describeCycle(cycle: string[], nodesById: Map<string, SkillGraphNode>): string {
  return cycle.map((id) => nodesById.get(id)?.name ?? "Unknown competency").join(" → ");
}

export default function SkillGraphPage() {
  const { toastSuccess, toastError } = useToast();

  const { data: graph, loading, error, refetch } = useApi<SkillGraph>(
    (signal) => skillGraphService.getGraph(signal),
    { isEmpty: (g) => g.nodes.length === 0 }
  );

  const [search, setSearch] = useState("");
  const [domain, setDomain] = useState("all");

  // "Add prerequisite" dialog state
  const [target, setTarget] = useState<SkillGraphNode | null>(null);
  const [prerequisiteId, setPrerequisiteId] = useState("");
  const [minMasteryPct, setMinMasteryPct] = useState(String(DEFAULT_MIN_MASTERY_PCT));
  const [rationale, setRationale] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  // "Remove prerequisite" confirmation
  const [removal, setRemoval] = useState<{ node: SkillGraphNode; prerequisite: SkillGraphNode } | null>(null);
  const [removing, setRemoving] = useState(false);

  const nodesById = useMemo(
    () => new Map((graph?.nodes ?? []).map((n) => [n.id, n])),
    [graph]
  );
  const edgeByPair = useMemo(
    () => new Map((graph?.edges ?? []).map((e) => [`${e.competency_id}:${e.prerequisite_id}`, e])),
    [graph]
  );

  const visibleNodes = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return (graph?.nodes ?? []).filter(
      (n) =>
        (domain === "all" || n.domain === domain) &&
        (needle === "" ||
          n.name.toLowerCase().includes(needle) ||
          n.code.toLowerCase().includes(needle))
    );
  }, [graph, search, domain]);

  const levels = useMemo(() => {
    const byLevel = new Map<number, SkillGraphNode[]>();
    for (const node of visibleNodes) {
      byLevel.set(node.level, [...(byLevel.get(node.level) ?? []), node]);
    }
    return [...byLevel.entries()].sort(([a], [b]) => a - b);
  }, [visibleNodes]);

  const openAddDialog = (node: SkillGraphNode) => {
    setTarget(node);
    setPrerequisiteId("");
    setMinMasteryPct(String(DEFAULT_MIN_MASTERY_PCT));
    setRationale("");
    setFormError(null);
  };

  const candidatePrerequisites = useMemo(() => {
    if (!target || !graph) return [];
    return graph.nodes
      .filter((n) => n.id !== target.id && !target.prerequisite_ids.includes(n.id))
      .sort((a, b) => a.name.localeCompare(b.name))
      .map((n) => ({ value: n.id, label: `${n.name} (${n.code})` }));
  }, [target, graph]);

  const submitPrerequisite = async () => {
    if (!target) return;
    const pct = Number(minMasteryPct);
    if (!prerequisiteId) {
      setFormError("Choose the competency that must come first.");
      return;
    }
    if (!Number.isFinite(pct) || pct < 0 || pct > 100) {
      setFormError("Required mastery must be between 0 and 100.");
      return;
    }

    setSaving(true);
    setFormError(null);
    try {
      await skillGraphService.addPrerequisite(target.id, {
        prerequisite_id: prerequisiteId,
        min_mastery: pct / 100,
        rationale: rationale.trim() || undefined,
      });
      toastSuccess(
        "Prerequisite added",
        `${target.name} now requires ${nodesById.get(prerequisiteId)?.name ?? "the selected competency"}.`
      );
      setTarget(null);
      refetch();
    } catch (err) {
      if (err instanceof ApiError && err.code === "prerequisite_cycle") {
        const detail = err.details as PrerequisiteCycleDetail | undefined;
        setFormError(
          detail?.cycle
            ? `That would create a circular dependency: ${describeCycle(detail.cycle, nodesById)}.`
            : err.message
        );
      } else if (err instanceof ApiError && err.status >= 400 && err.status < 500) {
        setFormError(err.message);
      } else {
        toastError(err, "Could not add prerequisite");
      }
    } finally {
      setSaving(false);
    }
  };

  const confirmRemoval = async () => {
    if (!removal) return;
    setRemoving(true);
    try {
      await skillGraphService.removePrerequisite(removal.node.id, removal.prerequisite.id);
      toastSuccess("Prerequisite removed");
      setRemoval(null);
      refetch();
    } catch (err) {
      toastError(err, "Could not remove prerequisite");
    } finally {
      setRemoving(false);
    }
  };

  return (
    <AppShell roles={["instructor", "org_admin", "system_admin"]}>
      <PageHeader
        title="Skill graph"
        description="Which competencies must be learned before others. The adaptive engine uses these links to decide when a learner needs a prerequisite before moving on."
        breadcrumbs={[{ label: "Admin", href: "/admin/dashboard" }, { label: "Skill graph" }]}
      />

      {loading && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
        </div>
      )}

      {!loading && error && <ErrorState error={error} onRetry={refetch} />}

      {!loading && !error && graph && graph.nodes.length === 0 && (
        <EmptyState
          icon={GitBranch}
          title="No competencies yet"
          description="Competencies are created when content is analysed, or added directly. Once they exist you can link them here."
        />
      )}

      {!loading && !error && graph && graph.nodes.length > 0 && (
        <>
          <p className="mb-4 text-sm text-fg-muted" aria-live="polite">
            {graph.nodes.length} competencies · {graph.edges.length} prerequisite links ·{" "}
            {graph.max_level + 1} {graph.max_level === 0 ? "level" : "levels"} deep
          </p>

          <div className="mb-6 flex flex-wrap items-center gap-3">
            <div className="w-full sm:w-72">
              <Input
                aria-label="Search competencies"
                placeholder="Search competencies…"
                leadingIcon={<Search className="size-4" aria-hidden="true" />}
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
            <div className="w-full sm:w-48">
              <Select
                aria-label="Filter by domain"
                value={domain}
                onChange={(e) => setDomain(e.target.value)}
                options={[
                  { value: "all", label: "All domains" },
                  ...graph.domains.map((d) => ({ value: d, label: d })),
                ]}
              />
            </div>
          </div>

          {levels.length === 0 ? (
            <EmptyState
              icon={Search}
              size="sm"
              title="No competencies match"
              description="Try a different search or domain."
            />
          ) : (
            <div className="space-y-8">
              {levels.map(([level, nodes]) => (
                <section key={level} aria-labelledby={`level-${level}`}>
                  <h2 id={`level-${level}`} className="mb-3 text-sm font-semibold text-fg">
                    {level === 0 ? "Foundations" : `Level ${level}`}
                    <span className="ml-2 font-normal text-fg-muted">
                      {level === 0 ? "no prerequisites" : `builds on level ${level - 1} and below`}
                    </span>
                  </h2>

                  <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
                    {nodes.map((node) => (
                      <Card key={node.id}>
                        <CardContent className="space-y-3 pt-5">
                          <div>
                            <h3 className="font-medium text-fg">{node.name}</h3>
                            <p className="mt-0.5 font-mono text-xs text-fg-muted">{node.code}</p>
                          </div>

                          <div className="flex flex-wrap gap-1.5">
                            {node.domain && <Badge variant="primary">{node.domain}</Badge>}
                            <Badge>{node.taxonomy_level}</Badge>
                            <Badge>difficulty {percent(node.difficulty)}</Badge>
                          </div>

                          <div>
                            <p className="mb-1.5 text-xs font-medium text-fg-muted">Requires</p>
                            {node.prerequisite_ids.length === 0 ? (
                              <p className="text-xs text-fg-subtle">Nothing — a starting point.</p>
                            ) : (
                              <ul className="space-y-1">
                                {node.prerequisite_ids.map((id) => {
                                  const prerequisite = nodesById.get(id);
                                  const edge = edgeByPair.get(`${node.id}:${id}`);
                                  if (!prerequisite) return null;
                                  return (
                                    <li
                                      key={id}
                                      className="flex items-center justify-between gap-2 rounded-md bg-surface px-2.5 py-1.5 text-sm"
                                    >
                                      <span className="min-w-0 truncate" title={edge?.rationale ?? undefined}>
                                        {prerequisite.name}
                                        {edge && (
                                          <span className="ml-1.5 text-xs text-fg-muted">
                                            ≥ {percent(edge.min_mastery)}
                                          </span>
                                        )}
                                      </span>
                                      <button
                                        type="button"
                                        onClick={() => setRemoval({ node, prerequisite })}
                                        aria-label={`Remove ${prerequisite.name} as a prerequisite of ${node.name}`}
                                        className="shrink-0 rounded p-1 text-fg-subtle hover:bg-surface-elevated hover:text-danger focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary"
                                      >
                                        <X className="size-3.5" aria-hidden="true" />
                                      </button>
                                    </li>
                                  );
                                })}
                              </ul>
                            )}
                          </div>

                          <div className="flex items-center justify-between pt-1">
                            <span className="text-xs text-fg-muted">
                              {node.dependent_ids.length === 0
                                ? "Nothing depends on this"
                                : `Unlocks ${node.dependent_ids.length}`}
                            </span>
                            <Button variant="ghost" size="sm" onClick={() => openAddDialog(node)}>
                              <Plus aria-hidden="true" />
                              Add prerequisite
                            </Button>
                          </div>
                        </CardContent>
                      </Card>
                    ))}
                  </div>
                </section>
              ))}
            </div>
          )}
        </>
      )}

      <Dialog
        open={target !== null}
        onClose={() => (saving ? undefined : setTarget(null))}
        title={target ? `Add prerequisite to ${target.name}` : "Add prerequisite"}
        description="Learners should reach the required mastery here before this competency is treated as unblocked."
        footer={
          <>
            <Button variant="secondary" onClick={() => setTarget(null)} disabled={saving}>
              Cancel
            </Button>
            <Button onClick={submitPrerequisite} disabled={saving}>
              {saving ? "Adding…" : "Add prerequisite"}
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <Field label="Must be learned first" htmlFor="prereq-select" required>
            {(props) => (
              <Select
                {...props}
                value={prerequisiteId}
                onChange={(e) => setPrerequisiteId(e.target.value)}
                placeholder="Choose a competency…"
                options={candidatePrerequisites}
              />
            )}
          </Field>

          <Field
            label="Required mastery (%)"
            htmlFor="prereq-mastery"
            hint="Mastery of the prerequisite at which this competency counts as unblocked."
          >
            {(props) => (
              <Input
                {...props}
                type="number"
                min={0}
                max={100}
                step={5}
                value={minMasteryPct}
                onChange={(e) => setMinMasteryPct(e.target.value)}
              />
            )}
          </Field>

          <Field label="Why? (optional)" htmlFor="prereq-rationale">
            {(props) => (
              <Textarea
                {...props}
                rows={2}
                maxLength={1000}
                value={rationale}
                onChange={(e) => setRationale(e.target.value)}
              />
            )}
          </Field>

          {formError && (
            <p role="alert" className="rounded-md bg-danger-light px-3 py-2 text-sm text-danger">
              {formError}
            </p>
          )}
        </div>
      </Dialog>

      <ConfirmDialog
        open={removal !== null}
        onClose={() => (removing ? undefined : setRemoval(null))}
        onConfirm={confirmRemoval}
        title="Remove prerequisite?"
        description={
          removal
            ? `${removal.node.name} will no longer require ${removal.prerequisite.name}.`
            : ""
        }
        confirmLabel="Remove"
        destructive
        loading={removing}
      />
    </AppShell>
  );
}
