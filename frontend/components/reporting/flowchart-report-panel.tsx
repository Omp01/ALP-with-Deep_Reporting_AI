"use client";

import React, { useEffect, useState } from "react";
import {
  GitFork,
  Layers,
  ShieldAlert,
  Sparkles,
  FileText,
  Loader2,
  Info,
  CheckCircle2,
  AlertTriangle,
  ArrowRight,
} from "lucide-react";
import { Card, Badge, Button, Alert } from "@/components/ui";
import { reportsService, FlowchartResponse } from "@/services/reports";
import { FlowchartViewer } from "./flowchart-viewer";

interface FlowchartReportPanelProps {
  teamId?: string;
  courseId?: string;
  onOpenEvidence?: (evidenceId: string) => void;
}

export function FlowchartReportPanel({
  teamId,
  courseId,
  onOpenEvidence,
}: FlowchartReportPanelProps) {
  const [flowchartType, setFlowchartType] = useState<"competency_dependency" | "module_friction" | "risk_cascade">(
    "competency_dependency"
  );
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<FlowchartResponse | null>(null);

  const fetchFlowchart = async (typeToUse = flowchartType) => {
    setLoading(true);
    setError(null);
    try {
      const res = await reportsService.flowchart({
        flowchart_type: typeToUse,
        team_id: teamId,
        course_id: courseId,
        days: 30,
      });
      setData(res);
    } catch (err: any) {
      console.error("Failed to load flowchart report:", err);
      setError(err?.message || "Failed to generate visual flowchart report.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchFlowchart(flowchartType);
  }, [flowchartType, teamId, courseId]);

  return (
    <Card className="p-6 bg-white border border-slate-200 rounded-2xl shadow-xs space-y-6">
      {/* Panel Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-100 pb-4">
        <div className="flex items-center gap-3">
          <div className="p-2.5 rounded-xl bg-indigo-50 text-indigo-600 border border-indigo-100 font-bold">
            <GitFork className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-lg font-bold text-slate-900">Flowchart BI Reports</h2>
              <Badge variant="primary" className="text-xs">
                Interactive Visual Diagrams
              </Badge>
            </div>
            <p className="text-xs text-slate-500 mt-0.5">
              Visualize learner competency dependencies, bottleneck drop-off pathways, and automated risk cascades.
            </p>
          </div>
        </div>

        {/* Tab Switcher */}
        <div className="flex items-center bg-slate-100 p-1 rounded-xl gap-1 text-xs font-medium">
          <button
            onClick={() => setFlowchartType("competency_dependency")}
            className={`px-3 py-1.5 rounded-lg transition-all flex items-center gap-1.5 ${
              flowchartType === "competency_dependency"
                ? "bg-white text-indigo-600 font-bold shadow-xs"
                : "text-slate-600 hover:text-slate-900"
            }`}
          >
            <GitFork className="w-3.5 h-3.5" />
            Competency Tree
          </button>
          <button
            onClick={() => setFlowchartType("module_friction")}
            className={`px-3 py-1.5 rounded-lg transition-all flex items-center gap-1.5 ${
              flowchartType === "module_friction"
                ? "bg-white text-indigo-600 font-bold shadow-xs"
                : "text-slate-600 hover:text-slate-900"
            }`}
          >
            <Layers className="w-3.5 h-3.5" />
            Module Friction
          </button>
          <button
            onClick={() => setFlowchartType("risk_cascade")}
            className={`px-3 py-1.5 rounded-lg transition-all flex items-center gap-1.5 ${
              flowchartType === "risk_cascade"
                ? "bg-white text-indigo-600 font-bold shadow-xs"
                : "text-slate-600 hover:text-slate-900"
            }`}
          >
            <ShieldAlert className="w-3.5 h-3.5" />
            Risk Cascade
          </button>
        </div>
      </div>

      {/* Loading state */}
      {loading && (
        <div className="p-12 text-center space-y-3 bg-slate-50/50 rounded-xl border border-dashed border-slate-200">
          <Loader2 className="w-7 h-7 animate-spin text-indigo-600 mx-auto" />
          <p className="text-xs font-semibold text-slate-700">Synthesizing visual flowchart telemetry...</p>
        </div>
      )}

      {/* Error state */}
      {error && (
        <Alert variant="danger" className="text-xs">
          <AlertTriangle className="w-4 h-4 text-red-500" />
          <span>{error}</span>
        </Alert>
      )}

      {/* Content View */}
      {data && !loading && (
        <div className="space-y-6">
          {/* AI Narrative Summary Box */}
          <div className="p-4 rounded-xl bg-indigo-50/60 border border-indigo-100 flex items-start gap-3">
            <Sparkles className="w-5 h-5 text-indigo-600 shrink-0 mt-0.5" />
            <div className="space-y-1">
              <h3 className="text-xs font-bold text-indigo-950 uppercase tracking-wider">
                AI Intelligence Narrative: {data.title}
              </h3>
              <p className="text-xs text-indigo-900 leading-relaxed font-medium">{data.summary}</p>
            </div>
          </div>

          {/* Interactive Mermaid Flowchart Viewer */}
          <FlowchartViewer mermaidCode={data.mermaid_code} />

          {/* Citations & Evidence Explorer Linkage */}
          {data.evidence_ids && data.evidence_ids.length > 0 && (
            <div className="flex items-center justify-between pt-2 border-t border-slate-100 text-xs text-slate-500">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-semibold text-slate-700 flex items-center gap-1">
                  <FileText className="w-3.5 h-3.5 text-indigo-600" /> Grounded Evidence Citations:
                </span>
                {data.evidence_ids.map((eid) => (
                  <button
                    key={eid}
                    onClick={() => onOpenEvidence?.(eid)}
                    className="px-2 py-0.5 rounded bg-indigo-50 hover:bg-indigo-100 border border-indigo-200 text-indigo-700 font-mono text-[11px] font-semibold transition-colors"
                  >
                    [{eid}]
                  </button>
                ))}
              </div>
              <span className="text-[11px] text-slate-400">Click citation to inspect raw telemetry</span>
            </div>
          )}
        </div>
      )}
    </Card>
  );
}
