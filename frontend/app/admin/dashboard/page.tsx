"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Navbar } from "@/components/Navbar";
import { Sidebar } from "@/components/Sidebar";
import { API_BASE_URL } from "@/lib/api-client";
import {
  Layers,
  UploadCloud,
  Download,
  FileSpreadsheet,
  Code2,
  TrendingUp,
  Award,
  Users,
  ShieldAlert,
  Copy,
} from "lucide-react";

interface OrgAnalytics {
  org_id: string;
  total_users: number;
  active_enrollments: number;
  overall_completion_rate_pct: number;
  organization_mastery_index: number;
  critical_at_risk_learners: number;
}

export default function AdminDashboardPage() {
  const [analytics, setAnalytics] = useState<OrgAnalytics | null>(null);
  const [courses, setCourses] = useState<unknown[]>([]);
  const [loading, setLoading] = useState(true);
  const [copySuccess, setCopySuccess] = useState(false);
  const [exporting, setExporting] = useState<string | null>(null);

  useEffect(() => {
    async function loadData() {
      if (typeof window === "undefined") return;
      const stored = localStorage.getItem("user");
      const token = localStorage.getItem("access_token");
      if (!stored || !token) {
        window.location.href = "/login";
        return;
      }
      const headers = { Authorization: `Bearer ${token}` };

      try {
        // 1. Organization Analytics
        const aRes = await fetch(`${API_BASE_URL}/api/v1/analytics/organization`, { headers });
        if (aRes.ok) setAnalytics(await aRes.json());

        // 2. Courses
        const cRes = await fetch(`${API_BASE_URL}/api/v1/courses`, { headers });
        if (cRes.ok) setCourses(await cRes.json());
      } catch (err) {
        console.error("Error loading admin data:", err);
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, []);

  async function triggerExportDownload(endpoint: string, filename: string, format: string) {
    const token = localStorage.getItem("access_token");
    if (!token) return;

    setExporting(`${endpoint}-${format}`);
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/export/${endpoint}?format=${format}`, {
        headers: { Authorization: `Bearer ${token}` },
      });

      if (!res.ok) throw new Error("Export request failed");

      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${filename}.${format}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      console.error(err);
    } finally {
      setExporting(null);
    }
  }

  const embedSnippet = `<iframe src="${API_BASE_URL}/api/v1/embed/report" width="100%" height="320" frameborder="0" style="border-radius: 12px; border: 1px solid #e2e8f0;"></iframe>`;

  const copyEmbedCode = () => {
    navigator.clipboard.writeText(embedSnippet);
    setCopySuccess(true);
    setTimeout(() => setCopySuccess(false), 2000);
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
                <Layers className="w-3.5 h-3.5 text-indigo-600" />
                Executive Administration
              </div>
              <h1 className="text-2xl font-bold text-slate-900 tracking-tight">
                Organization Overview
              </h1>
              <p className="text-sm text-slate-500 mt-1">
                Oversee learning analytics and export BI data streams. Content is managed in the Content Library.
              </p>
            </div>
          </div>

          {loading ? (
            <div className="bg-white border border-slate-200 rounded-2xl p-12 text-center">
              <div className="inline-block animate-spin rounded-full h-8 w-8 border-4 border-indigo-600 border-t-transparent mb-4"></div>
              <p className="text-slate-600 font-medium">Loading organization analytics and services...</p>
            </div>
          ) : (
            <div className="space-y-8">
              {/* Executive Analytics KPIs */}
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
                <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-xs">
                  <div className="flex items-center justify-between text-slate-400 mb-3">
                    <span className="text-xs font-semibold uppercase tracking-wider">Active Enrollments</span>
                    <Users className="w-5 h-5 text-indigo-500" />
                  </div>
                  <div className="text-3xl font-bold text-slate-900">
                    {analytics ? analytics.active_enrollments : "—"}
                  </div>
                  <div className="text-xs text-slate-500 mt-2">
                    Across {courses.length} active courses
                  </div>
                </div>

                <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-xs">
                  <div className="flex items-center justify-between text-slate-400 mb-3">
                    <span className="text-xs font-semibold uppercase tracking-wider">Completion Rate</span>
                    <TrendingUp className="w-5 h-5 text-emerald-500" />
                  </div>
                  <div className="text-3xl font-bold text-slate-900">
                    {analytics && analytics.overall_completion_rate_pct != null ? `${analytics.overall_completion_rate_pct}%` : "—"}
                  </div>
                  <div className="text-xs text-slate-500 mt-2">
                    Curriculum milestone completion
                  </div>
                </div>

                <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-xs">
                  <div className="flex items-center justify-between text-slate-400 mb-3">
                    <span className="text-xs font-semibold uppercase tracking-wider">Mastery Index</span>
                    <Award className="w-5 h-5 text-indigo-500" />
                  </div>
                  <div className="text-3xl font-bold text-slate-900">
                    {analytics && analytics.organization_mastery_index != null ? `${(analytics.organization_mastery_index * 100).toFixed(0)}%` : "—"}
                  </div>
                  <div className="text-xs text-slate-500 mt-2">
                    Bayesian verified competency
                  </div>
                </div>

                <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-xs">
                  <div className="flex items-center justify-between text-slate-400 mb-3">
                    <span className="text-xs font-semibold uppercase tracking-wider">Critical At-Risk</span>
                    <ShieldAlert className="w-5 h-5 text-red-500" />
                  </div>
                  <div className="text-3xl font-bold text-red-600">
                    {analytics ? analytics.critical_at_risk_learners : "—"}
                  </div>
                  <div className="text-xs text-red-700 font-medium mt-2">
                    Triggered early-warning alerts
                  </div>
                </div>
              </div>

              {/* Content lives in the Content Library */}
              <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-xs flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl bg-indigo-50 text-indigo-600 flex items-center justify-center">
                    <UploadCloud className="w-5 h-5" />
                  </div>
                  <div>
                    <h2 className="text-lg font-bold text-slate-900">Content Library</h2>
                    <p className="text-xs text-slate-500">
                      Add documents, recordings and YouTube videos, review what the AI extracted, and publish to learners.
                    </p>
                  </div>
                </div>
                <Link
                  href="/admin/content"
                  className="inline-flex items-center gap-2 px-5 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-sm font-medium transition-colors shadow-xs"
                >
                  Open Content Library
                </Link>
              </div>

              {/* BI Export & Data Warehouse Streaming Hub */}
              <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-xs">
                <div className="pb-4 mb-6 border-b border-slate-100 flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-xl bg-indigo-50 text-indigo-600 flex items-center justify-center font-bold">
                      <FileSpreadsheet className="w-5 h-5" />
                    </div>
                    <div>
                      <h2 className="text-lg font-bold text-slate-900">
                        BI & Data Warehouse Export Hub
                      </h2>
                      <p className="text-xs text-slate-500">
                        High-throughput streaming endpoints for external analytics (Snowflake, BigQuery, Tableau, PowerBI).
                      </p>
                    </div>
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
                  {/* Learning Events */}
                  <div className="p-5 rounded-xl border border-slate-200 bg-slate-50/50 space-y-3">
                    <div className="font-bold text-slate-900 text-sm">Learning Telemetry Stream</div>
                    <p className="text-xs text-slate-500 leading-relaxed">
                      Raw telemetry events containing micro-timings, question responses, and error distributions.
                    </p>
                    <div className="flex gap-2 pt-2">
                      <button
                        onClick={() => triggerExportDownload("events", "learning_events", "csv")}
                        disabled={exporting === "events-csv"}
                        className="flex-1 inline-flex items-center justify-center gap-1.5 px-3 py-1.5 bg-white border border-slate-300 hover:border-indigo-400 text-slate-800 rounded-lg text-xs font-semibold shadow-2xs transition-colors"
                      >
                        <Download className="w-3.5 h-3.5" /> CSV
                      </button>
                      <button
                        onClick={() => triggerExportDownload("events", "learning_events", "json")}
                        disabled={exporting === "events-json"}
                        className="flex-1 inline-flex items-center justify-center gap-1.5 px-3 py-1.5 bg-white border border-slate-300 hover:border-indigo-400 text-slate-800 rounded-lg text-xs font-semibold shadow-2xs transition-colors"
                      >
                        <Download className="w-3.5 h-3.5" /> JSON
                      </button>
                    </div>
                  </div>

                  {/* Competency Mastery */}
                  <div className="p-5 rounded-xl border border-slate-200 bg-slate-50/50 space-y-3">
                    <div className="font-bold text-slate-900 text-sm">Competency Mastery Ledger</div>
                    <p className="text-xs text-slate-500 leading-relaxed">
                      Calibrated Bayesian mastery scores, statistical confidence ratings, and trend vectors.
                    </p>
                    <div className="flex gap-2 pt-2">
                      <button
                        onClick={() => triggerExportDownload("competencies", "competency_mastery", "csv")}
                        disabled={exporting === "competencies-csv"}
                        className="flex-1 inline-flex items-center justify-center gap-1.5 px-3 py-1.5 bg-white border border-slate-300 hover:border-indigo-400 text-slate-800 rounded-lg text-xs font-semibold shadow-2xs transition-colors"
                      >
                        <Download className="w-3.5 h-3.5" /> CSV
                      </button>
                      <button
                        onClick={() => triggerExportDownload("competencies", "competency_mastery", "json")}
                        disabled={exporting === "competencies-json"}
                        className="flex-1 inline-flex items-center justify-center gap-1.5 px-3 py-1.5 bg-white border border-slate-300 hover:border-indigo-400 text-slate-800 rounded-lg text-xs font-semibold shadow-2xs transition-colors"
                      >
                        <Download className="w-3.5 h-3.5" /> JSON
                      </button>
                    </div>
                  </div>

                  {/* Risk Signals */}
                  <div className="p-5 rounded-xl border border-slate-200 bg-slate-50/50 space-y-3">
                    <div className="font-bold text-slate-900 text-sm">Risk Signals & Anomalies</div>
                    <p className="text-xs text-slate-500 leading-relaxed">
                      Multi-signal early warnings, dropout probabilities, and intervention resolution histories.
                    </p>
                    <div className="flex gap-2 pt-2">
                      <button
                        onClick={() => triggerExportDownload("risks", "risk_signals", "csv")}
                        disabled={exporting === "risks-csv"}
                        className="flex-1 inline-flex items-center justify-center gap-1.5 px-3 py-1.5 bg-white border border-slate-300 hover:border-indigo-400 text-slate-800 rounded-lg text-xs font-semibold shadow-2xs transition-colors"
                      >
                        <Download className="w-3.5 h-3.5" /> CSV
                      </button>
                      <button
                        onClick={() => triggerExportDownload("risks", "risk_signals", "json")}
                        disabled={exporting === "risks-json"}
                        className="flex-1 inline-flex items-center justify-center gap-1.5 px-3 py-1.5 bg-white border border-slate-300 hover:border-indigo-400 text-slate-800 rounded-lg text-xs font-semibold shadow-2xs transition-colors"
                      >
                        <Download className="w-3.5 h-3.5" /> JSON
                      </button>
                    </div>
                  </div>
                </div>
              </div>

              {/* Embeddable Reporting Widget Sandbox */}
              <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-xs">
                <div className="pb-4 mb-6 border-b border-slate-100 flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-xl bg-indigo-50 text-indigo-600 flex items-center justify-center font-bold">
                      <Code2 className="w-5 h-5" />
                    </div>
                    <div>
                      <h2 className="text-lg font-bold text-slate-900">
                        Embeddable Reporting Widget Sandbox
                      </h2>
                      <p className="text-xs text-slate-500">
                        Zero-friction embeddable iframe for internal portals, Notion, Slack canvas, or enterprise intranet.
                      </p>
                    </div>
                  </div>

                  <button
                    onClick={copyEmbedCode}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-slate-900 hover:bg-slate-800 text-white rounded-lg text-xs font-semibold transition-colors"
                  >
                    <Copy className="w-3.5 h-3.5" />
                    {copySuccess ? "Copied!" : "Copy Embed Code"}
                  </button>
                </div>

                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-start">
                  <div>
                    <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">
                      HTML Embed Snippet
                    </label>
                    <pre className="bg-slate-900 text-slate-100 p-4 rounded-xl text-xs font-mono overflow-x-auto leading-relaxed">
                      {embedSnippet}
                    </pre>
                    <p className="text-xs text-slate-400 mt-2">
                      Endpoint: <code className="text-indigo-600 font-mono">GET /api/v1/embed/report</code> (supports HTML Card & JSON summary).
                    </p>
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">
                      Live Widget Sandbox Preview
                    </label>
                    <div className="border border-slate-200 rounded-xl overflow-hidden shadow-xs bg-white">
                      <iframe
                        src={`${API_BASE_URL}/api/v1/embed/report`}
                        className="w-full h-72 border-0"
                        title="Embeddable Learning Report Widget"
                      />
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
