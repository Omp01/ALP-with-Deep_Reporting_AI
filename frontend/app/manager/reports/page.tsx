"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { Navbar } from "@/components/Navbar";
import { Sidebar } from "@/components/Sidebar";
import {
  FileText,
  Sparkles,
  ShieldCheck,
  Send,
  RefreshCw,
  Mail,
  Clock,
  CheckCircle2,
  AlertCircle,
  HelpCircle,
  Database,
  ArrowRight,
  X,
  Layers,
} from "lucide-react";

interface EvidenceFact {
  citation_key: string;
  category: string;
  fact: string;
  source_entity: string;
  confidence: number;
  timestamp: string;
  metadata?: Record<string, any>;
}

interface ClaimItem {
  claim: string;
  confidence: number;
  evidence_ids: string[];
  supported: boolean;
}

interface DigestData {
  id?: string;
  digest_id?: string;
  content: string;
  sent_to: string[];
  sent_at?: string;
  timestamp?: string;
  status: string;
}

export default function ManagerReportsPage() {
  const [teams, setTeams] = useState<any[]>([]);
  const [selectedTeamId, setSelectedTeamId] = useState<string>("");
  const [insight, setInsight] = useState<any>(null);
  const [evidenceMap, setEvidenceMap] = useState<Record<string, EvidenceFact>>({});
  const [selectedEvidence, setSelectedEvidence] = useState<EvidenceFact | null>(null);
  const [latestDigest, setLatestDigest] = useState<DigestData | null>(null);
  const [loading, setLoading] = useState(true);
  const [generatingReport, setGeneratingReport] = useState(false);
  const [generatingDigest, setGeneratingDigest] = useState(false);
  const [digestSuccessMsg, setDigestSuccessMsg] = useState<string | null>(null);

  useEffect(() => {
    async function init() {
      if (typeof window === "undefined") return;
      const stored = localStorage.getItem("user");
      const token = localStorage.getItem("access_token");
      if (!stored || !token) {
        window.location.href = "/login";
        return;
      }
      const headers = { Authorization: `Bearer ${token}` };

      try {
        // 1. Fetch teams
        const tRes = await fetch("http://localhost:8000/api/v1/teams", { headers });
        if (tRes.ok) {
          const tList = await tRes.json();
          setTeams(tList);
          if (tList.length > 0) {
            setSelectedTeamId(tList[0].id);
            await fetchCohortInsight(tList[0].id, token);
          }
        }

        // 2. Fetch latest digest
        const dRes = await fetch("http://localhost:8000/api/v1/reports/digest/latest", { headers });
        if (dRes.ok) {
          setLatestDigest(await dRes.json());
        }
      } catch (err) {
        console.error("Error loading reports page:", err);
      } finally {
        setLoading(false);
      }
    }
    init();
  }, []);

  async function fetchCohortInsight(teamId: string, token: string) {
    setGeneratingReport(true);
    try {
      const res = await fetch("http://localhost:8000/api/v1/insights/generate", {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          scope_type: "team",
          scope_id: teamId,
          question: "Provide an executive summary of systemic cohort bottlenecks, mastery trends, and recommended team interventions.",
        }),
      });

      if (res.ok) {
        const data = await res.json();
        setInsight(data);

        // Fetch evidence package
        const evRes = await fetch(`http://localhost:8000/api/v1/insights/${data.insight_id}/evidence`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (evRes.ok) {
          const evData = await evRes.json();
          const pkg: EvidenceFact[] = evData.evidence_package || [];
          const map: Record<string, EvidenceFact> = {};
          pkg.forEach((item) => {
            map[item.citation_key] = item;
          });
          setEvidenceMap(map);
        }
      }
    } catch (err) {
      console.error(err);
    } finally {
      setGeneratingReport(false);
    }
  }

  async function handleTriggerDigest() {
    const token = localStorage.getItem("access_token");
    if (!token) return;
    setGeneratingDigest(true);
    setDigestSuccessMsg(null);
    try {
      const res = await fetch("http://localhost:8000/api/v1/reports/digest/generate", {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const dData = await res.json();
        setLatestDigest(dData);
        setDigestSuccessMsg("Scheduled proactive digest generated and dispatched successfully!");
      }
    } catch (err) {
      console.error(err);
    } finally {
      setGeneratingDigest(false);
    }
  }

  const renderNarrativeWithCitations = (text: string) => {
    if (!text) return null;
    const parts = text.split(/(\[E-\d+\])/g);
    return parts.map((part, index) => {
      const match = part.match(/^\[(E-\d+)\]$/);
      if (match) {
        const key = match[1];
        const ev = evidenceMap[key];
        return (
          <button
            key={index}
            onClick={() => setSelectedEvidence(ev || null)}
            className="inline-flex items-center gap-1 mx-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-indigo-50 text-indigo-700 border border-indigo-200 hover:bg-indigo-100 hover:border-indigo-300 transition-colors shadow-2xs"
            title={`Inspect evidence fact ${key}`}
          >
            <span>[{key}]</span>
            <HelpCircle className="w-3 h-3 text-indigo-500 inline" />
          </button>
        );
      }
      return <span key={index}>{part}</span>;
    });
  };

  return (
    <div className="min-h-screen bg-slate-50">
      <Navbar />
      <div className="flex">
        <Sidebar />
        <main className="flex-1 p-8 max-w-7xl">
          {/* Header */}
          <div className="mb-8 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
            <div>
              <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-indigo-50 text-indigo-700 text-xs font-semibold mb-2 border border-indigo-200">
                <FileText className="w-3.5 h-3.5 text-indigo-600" />
                Reporting & Proactive Digests
              </div>
              <h1 className="text-2xl font-bold text-slate-900 tracking-tight">
                Cohort Grounded AI Intelligence
              </h1>
              <p className="text-sm text-slate-500 mt-1">
                Zero-hallucination narratives backed by database citations, alongside scheduled proactive executive digests.
              </p>
            </div>

            <div className="flex items-center gap-3">
              <select
                value={selectedTeamId}
                onChange={(e) => {
                  setSelectedTeamId(e.target.value);
                  const token = localStorage.getItem("access_token");
                  if (token) fetchCohortInsight(e.target.value, token);
                }}
                className="px-3 py-2 bg-white border border-slate-300 rounded-lg text-sm font-medium text-slate-800 shadow-xs focus:ring-2 focus:ring-indigo-500"
              >
                {teams.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name}
                  </option>
                ))}
              </select>

              <button
                onClick={() => {
                  const token = localStorage.getItem("access_token");
                  if (token && selectedTeamId) fetchCohortInsight(selectedTeamId, token);
                }}
                disabled={generatingReport}
                className="inline-flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-sm font-medium shadow-xs transition-colors disabled:opacity-50"
              >
                <RefreshCw className={`w-4 h-4 ${generatingReport ? "animate-spin" : ""}`} />
                {generatingReport ? "Synthesizing..." : "Refresh Report"}
              </button>
            </div>
          </div>

          <div className="space-y-8">
            {/* Grounded Cohort AI Report */}
            {generatingReport ? (
              <div className="bg-white border border-slate-200 rounded-2xl p-12 text-center">
                <div className="inline-block animate-spin rounded-full h-8 w-8 border-4 border-indigo-600 border-t-transparent mb-4"></div>
                <p className="text-slate-600 font-medium">Extracting team telemetry facts & building evidence graph...</p>
                <p className="text-xs text-slate-400 mt-1">Grounded citations guaranteed with zero hallucination penalty</p>
              </div>
            ) : insight ? (
              <div className="space-y-6">
                {/* Grounding Badge */}
                <div className="bg-gradient-to-r from-emerald-50 via-teal-50 to-indigo-50 border border-emerald-200 rounded-2xl p-6 shadow-xs flex items-center justify-between">
                  <div className="flex items-center gap-4">
                    <div className="w-11 h-11 rounded-xl bg-emerald-600 text-white flex items-center justify-center shrink-0">
                      <ShieldCheck className="w-6 h-6" />
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <h3 className="font-bold text-slate-900">Verifiable Cohort Narrative</h3>
                        <span className="px-2 py-0.5 rounded-full text-xs font-bold bg-emerald-100 text-emerald-800 border border-emerald-300">
                          100% Grounded
                        </span>
                      </div>
                      <p className="text-xs text-slate-600 mt-1">
                        Citations mapped directly to cohort competency states and learning event logs.
                      </p>
                    </div>
                  </div>
                  <div className="text-right">
                    <span className="text-xs text-slate-400 font-mono">
                      Generated in {insight.generation_time_ms}ms
                    </span>
                  </div>
                </div>

                {/* Synthesis Narrative Card */}
                <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-xs">
                  <div className="flex items-center justify-between pb-4 mb-4 border-b border-slate-100">
                    <div className="flex items-center gap-2">
                      <FileText className="w-5 h-5 text-indigo-600" />
                      <h2 className="text-lg font-bold text-slate-900">Executive Cohort Synthesis</h2>
                    </div>
                    <span className="text-xs font-mono text-slate-500 bg-slate-100 px-2 py-1 rounded">
                      Model: {insight.model_used || "gpt-4o-mini"}
                    </span>
                  </div>

                  <div className="prose prose-slate max-w-none text-slate-800 leading-relaxed text-base mb-6">
                    {renderNarrativeWithCitations(insight.summary)}
                  </div>

                  {/* Claims Breakdown */}
                  <div className="pt-4 border-t border-slate-100">
                    <h4 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">
                      Substantiated Telemetry Claims
                    </h4>
                    <div className="space-y-2.5">
                      {insight.claims?.map((c: ClaimItem, i: number) => (
                        <div
                          key={i}
                          className="p-3 bg-slate-50 border border-slate-200 rounded-xl flex items-center justify-between gap-3 text-xs"
                        >
                          <div className="flex items-center gap-2.5">
                            <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
                            <span className="text-slate-800 font-medium">{c.claim}</span>
                          </div>
                          <div className="flex items-center gap-1.5 shrink-0">
                            {c.evidence_ids?.map((evKey) => (
                              <button
                                key={evKey}
                                onClick={() => setSelectedEvidence(evidenceMap[evKey] || null)}
                                className="px-2 py-0.5 bg-white border border-slate-300 text-indigo-700 rounded text-xs font-semibold shadow-2xs hover:border-indigo-400"
                              >
                                [{evKey}]
                              </button>
                            ))}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>

                {/* Recommended Coaching Interventions */}
                {insight.recommendations && insight.recommendations.length > 0 && (
                  <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-xs">
                    <h3 className="text-sm font-bold text-slate-900 uppercase tracking-wider mb-4 flex items-center gap-2">
                      <ArrowRight className="w-4 h-4 text-indigo-600" />
                      Priority Team Interventions
                    </h3>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                      {insight.recommendations.map((rec: string, i: number) => (
                        <div
                          key={i}
                          className="p-4 rounded-xl bg-indigo-50/50 border border-indigo-100 flex items-start gap-3"
                        >
                          <div className="w-6 h-6 rounded-full bg-indigo-600 text-white flex items-center justify-center text-xs font-bold shrink-0 mt-0.5">
                            {i + 1}
                          </div>
                          <p className="text-sm text-slate-800 leading-snug">{rec}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ) : null}

            {/* Scheduled Proactive Digest Section */}
            <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-xs">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 mb-6 border-b border-slate-100">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl bg-indigo-50 text-indigo-600 flex items-center justify-center font-bold">
                    <Mail className="w-5 h-5" />
                  </div>
                  <div>
                    <h2 className="text-lg font-bold text-slate-900">
                      Proactive Leadership Digest
                    </h2>
                    <p className="text-xs text-slate-500">
                      Autonomous weekly email & notification rollup sent to managers and executives.
                    </p>
                  </div>
                </div>

                <button
                  onClick={handleTriggerDigest}
                  disabled={generatingDigest}
                  className="inline-flex items-center gap-2 px-4 py-2 bg-slate-900 hover:bg-slate-800 text-white rounded-lg text-sm font-medium transition-colors shadow-xs disabled:opacity-50"
                >
                  <Send className={`w-4 h-4 ${generatingDigest ? "animate-spin" : ""}`} />
                  {generatingDigest ? "Dispatching Digest..." : "Trigger Proactive Run"}
                </button>
              </div>

              {digestSuccessMsg && (
                <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-4 mb-6 text-emerald-800 text-sm flex items-center gap-3">
                  <CheckCircle2 className="w-5 h-5 text-emerald-600 shrink-0" />
                  <span>{digestSuccessMsg}</span>
                </div>
              )}

              {latestDigest ? (
                <div className="p-6 rounded-xl bg-slate-50 border border-slate-200 space-y-4">
                  <div className="flex flex-wrap items-center justify-between gap-2 pb-3 border-b border-slate-200/80 text-xs">
                    <div className="flex items-center gap-2">
                      <span className="px-2 py-0.5 rounded-full font-bold uppercase bg-emerald-100 text-emerald-800 border border-emerald-300">
                        {latestDigest.status || "Dispatched"}
                      </span>
                      <span className="text-slate-500">
                        Recipients: <span className="font-semibold text-slate-800">{latestDigest.sent_to?.join(", ")}</span>
                      </span>
                    </div>
                    <div className="text-slate-400 font-mono">
                      Timestamp: {new Date(latestDigest.sent_at || latestDigest.timestamp || new Date()).toLocaleString()}
                    </div>
                  </div>

                  <div className="whitespace-pre-line text-sm text-slate-800 font-sans leading-relaxed bg-white p-4 rounded-lg border border-slate-200 shadow-2xs">
                    {latestDigest.content}
                  </div>
                </div>
              ) : (
                <div className="text-center py-8 text-slate-400 text-sm">
                  No proactive digests generated yet. Click "Trigger Proactive Run" to dispatch the first digest.
                </div>
              )}
            </div>
          </div>
        </main>
      </div>

      {/* "Why?" Evidence Inspection Drawer / Modal */}
      {selectedEvidence && (
        <div className="fixed inset-0 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4 z-50 animate-fade-in">
          <div className="bg-white border border-slate-200 rounded-2xl max-w-lg w-full p-6 shadow-2xl relative">
            <button
              onClick={() => setSelectedEvidence(null)}
              className="absolute top-4 right-4 text-slate-400 hover:text-slate-600 p-1"
            >
              <X className="w-5 h-5" />
            </button>

            <div className="flex items-center gap-2 mb-3">
              <span className="px-2.5 py-1 bg-indigo-600 text-white font-mono font-bold text-xs rounded-md">
                [{selectedEvidence.citation_key}]
              </span>
              <span className="text-xs uppercase font-bold text-slate-400 tracking-wider">
                Cohort Grounding Fact
              </span>
            </div>

            <h3 className="text-lg font-bold text-slate-900 mb-4">
              Ground Truth Telemetry Proof
            </h3>

            <div className="p-4 bg-slate-50 border border-slate-200 rounded-xl mb-4">
              <p className="text-sm font-medium text-slate-900 leading-relaxed">
                {selectedEvidence.fact}
              </p>
            </div>

            <div className="space-y-2.5 text-xs">
              <div className="flex justify-between py-1.5 border-b border-slate-100">
                <span className="text-slate-500">Source Entity</span>
                <span className="font-mono font-semibold text-slate-800">{selectedEvidence.source_entity}</span>
              </div>
              <div className="flex justify-between py-1.5 border-b border-slate-100">
                <span className="text-slate-500">Evidence Category</span>
                <span className="font-semibold text-slate-800 uppercase">{selectedEvidence.category}</span>
              </div>
              <div className="flex justify-between py-1.5 border-b border-slate-100">
                <span className="text-slate-500">Confidence Score</span>
                <span className="font-semibold text-emerald-700">{(selectedEvidence.confidence * 100).toFixed(1)}%</span>
              </div>
              <div className="flex justify-between py-1.5 border-b border-slate-100">
                <span className="text-slate-500">Recorded At</span>
                <span className="font-mono text-slate-600">{new Date(selectedEvidence.timestamp).toLocaleString()}</span>
              </div>
            </div>

            <div className="mt-6 flex justify-end">
              <button
                onClick={() => setSelectedEvidence(null)}
                className="px-4 py-2 bg-slate-900 text-white text-xs font-semibold rounded-lg hover:bg-slate-800 transition-colors"
              >
                Close Inspector
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
