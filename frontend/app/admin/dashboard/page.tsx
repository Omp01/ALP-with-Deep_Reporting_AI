"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { Navbar } from "@/components/Navbar";
import { Sidebar } from "@/components/Sidebar";
import {
  Layers,
  UploadCloud,
  Download,
  FileSpreadsheet,
  Code2,
  CheckCircle2,
  Clock,
  AlertCircle,
  TrendingUp,
  Award,
  Users,
  ShieldAlert,
  Copy,
  ExternalLink,
  RefreshCw,
  FileText,
} from "lucide-react";

interface OrgAnalytics {
  org_id: string;
  total_users: number;
  active_enrollments: number;
  overall_completion_rate_pct: number;
  organization_mastery_index: number;
  critical_at_risk_learners: number;
}

interface IngestionJob {
  id: string;
  file_name: string;
  file_type: string;
  file_size: number;
  status: string;
  created_at: string;
  completed_at?: string;
  error_message?: string;
}

export default function AdminDashboardPage() {
  const [analytics, setAnalytics] = useState<OrgAnalytics | null>(null);
  const [jobs, setJobs] = useState<IngestionJob[]>([]);
  const [courses, setCourses] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [selectedModuleId, setSelectedModuleId] = useState<string>("");
  const [uploadMessage, setUploadMessage] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
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
        const aRes = await fetch("http://localhost:8000/api/v1/analytics/organization", { headers });
        if (aRes.ok) setAnalytics(await aRes.json());

        // 2. Ingestion Jobs
        const jRes = await fetch("http://localhost:8000/api/v1/ingestion/jobs", { headers });
        if (jRes.ok) setJobs(await jRes.json());

        // 3. Courses
        const cRes = await fetch("http://localhost:8000/api/v1/courses", { headers });
        if (cRes.ok) setCourses(await cRes.json());
      } catch (err) {
        console.error("Error loading admin data:", err);
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, []);

  async function handleFileUpload(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedFile) return;

    const token = localStorage.getItem("access_token");
    if (!token) return;

    setUploading(true);
    setUploadMessage(null);
    setUploadError(null);

    const formData = new FormData();
    formData.append("file", selectedFile);
    if (selectedModuleId) {
      formData.append("module_id", selectedModuleId);
    }

    try {
      // 1. Upload file
      const upRes = await fetch("http://localhost:8000/api/v1/ingestion/upload", {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      });

      if (!upRes.ok) {
        const err = await upRes.json();
        throw new Error(err.detail || "Upload failed");
      }

      const uploadData = await upRes.json();
      const jobId = uploadData.job_id;

      setUploadMessage(`File uploaded (${uploadData.file_name}). Commencing semantic chunking & extraction...`);

      // 2. Trigger automatic processing
      const procRes = await fetch(`http://localhost:8000/api/v1/ingestion/jobs/${jobId}/process`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });

      if (procRes.ok) {
        setUploadMessage(`Processing complete for ${uploadData.file_name}! Content chunks and knowledge nodes created.`);
      }

      // 3. Refresh job list
      const jRes = await fetch("http://localhost:8000/api/v1/ingestion/jobs", {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (jRes.ok) setJobs(await jRes.json());

      setSelectedFile(null);
    } catch (err: any) {
      setUploadError(err.message || "Failed to process content");
    } finally {
      setUploading(false);
    }
  }

  async function triggerExportDownload(endpoint: string, filename: string, format: string) {
    const token = localStorage.getItem("access_token");
    if (!token) return;

    setExporting(`${endpoint}-${format}`);
    try {
      const res = await fetch(`http://localhost:8000/api/v1/export/${endpoint}?format=${format}`, {
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

  const embedSnippet = `<iframe src="http://localhost:8000/api/v1/embed/report" width="100%" height="320" frameborder="0" style="border-radius: 12px; border: 1px solid #e2e8f0;"></iframe>`;

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
                Organization Intelligence & Ingestion Studio
              </h1>
              <p className="text-sm text-slate-500 mt-1">
                Oversee enterprise learning analytics, ingest syllabus content into knowledge graphs, and export BI data streams.
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
                    {analytics ? analytics.active_enrollments : 13}
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
                    {analytics ? `${analytics.overall_completion_rate_pct}%` : "68%"}
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
                    {analytics ? `${(analytics.organization_mastery_index * 100).toFixed(0)}%` : "76%"}
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
                    {analytics ? analytics.critical_at_risk_learners : 1}
                  </div>
                  <div className="text-xs text-red-700 font-medium mt-2">
                    Triggered early-warning alerts
                  </div>
                </div>
              </div>

              {/* Content Ingestion Studio */}
              <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-xs">
                <div className="pb-4 mb-6 border-b border-slate-100 flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-xl bg-indigo-50 text-indigo-600 flex items-center justify-center font-bold">
                      <UploadCloud className="w-5 h-5" />
                    </div>
                    <div>
                      <h2 className="text-lg font-bold text-slate-900">
                        Content Ingestion & Semantic Chunker
                      </h2>
                      <p className="text-xs text-slate-500">
                        Upload course materials (PDF, DOCX, TXT, MD). Automatically chunks text and maps to competencies.
                      </p>
                    </div>
                  </div>
                </div>

                <form onSubmit={handleFileUpload} className="space-y-4 mb-6">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1.5">
                        Select Document / Syllabus File
                      </label>
                      <input
                        type="file"
                        accept=".pdf,.docx,.pptx,.txt,.md"
                        onChange={(e) => setSelectedFile(e.target.files?.[0] || null)}
                        className="block w-full text-sm text-slate-500 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-xs file:font-semibold file:bg-indigo-50 file:text-indigo-700 hover:file:bg-indigo-100 cursor-pointer border border-slate-300 rounded-lg p-1"
                      />
                    </div>

                    <div>
                      <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1.5">
                        Associate to Course (Optional)
                      </label>
                      <select
                        value={selectedModuleId}
                        onChange={(e) => setSelectedModuleId(e.target.value)}
                        className="w-full px-3 py-2 bg-white border border-slate-300 rounded-lg text-sm text-slate-800"
                      >
                        <option value="">Auto-detect course & module</option>
                        {courses.map((c) => (
                          <option key={c.id} value={c.id}>
                            {c.title}
                          </option>
                        ))}
                      </select>
                    </div>
                  </div>

                  <div className="flex justify-end">
                    <button
                      type="submit"
                      disabled={!selectedFile || uploading}
                      className="inline-flex items-center gap-2 px-5 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-sm font-medium transition-colors shadow-xs disabled:opacity-50"
                    >
                      <UploadCloud className={`w-4 h-4 ${uploading ? "animate-spin" : ""}`} />
                      {uploading ? "Extracting & Chunking..." : "Upload & Parse Syllabus"}
                    </button>
                  </div>
                </form>

                {uploadMessage && (
                  <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-4 mb-4 text-emerald-800 text-sm flex items-center gap-3">
                    <CheckCircle2 className="w-5 h-5 text-emerald-600 shrink-0" />
                    <span>{uploadMessage}</span>
                  </div>
                )}

                {uploadError && (
                  <div className="bg-red-50 border border-red-200 rounded-xl p-4 mb-4 text-red-700 text-sm flex items-center gap-3">
                    <AlertCircle className="w-5 h-5 text-red-500 shrink-0" />
                    <span>{uploadError}</span>
                  </div>
                )}

                {/* Ingestion Jobs Ledger */}
                <div className="mt-6">
                  <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">
                    Recent Ingestion Jobs & Knowledge Extractions
                  </h3>
                  <div className="overflow-x-auto">
                    <table className="w-full text-left text-xs">
                      <thead className="bg-slate-50 text-slate-500 uppercase font-semibold border-b border-slate-200">
                        <tr>
                          <th className="px-4 py-2.5">File Name</th>
                          <th className="px-4 py-2.5">Type</th>
                          <th className="px-4 py-2.5">File Size</th>
                          <th className="px-4 py-2.5">Status</th>
                          <th className="px-4 py-2.5">Uploaded</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100">
                        {jobs.map((j) => (
                          <tr key={j.id} className="hover:bg-slate-50/50">
                            <td className="px-4 py-2.5 font-medium text-slate-900">{j.file_name}</td>
                            <td className="px-4 py-2.5 uppercase text-slate-500 font-mono">{j.file_type}</td>
                            <td className="px-4 py-2.5 text-slate-600 font-mono">
                              {(j.file_size / 1024).toFixed(1)} KB
                            </td>
                            <td className="px-4 py-2.5">
                              <span
                                className={`px-2 py-0.5 rounded-full font-semibold uppercase text-[10px] ${
                                  j.status === "completed"
                                    ? "bg-emerald-100 text-emerald-800"
                                    : j.status === "processing"
                                    ? "bg-indigo-100 text-indigo-800"
                                    : "bg-slate-100 text-slate-800"
                                }`}
                              >
                                {j.status}
                              </span>
                            </td>
                            <td className="px-4 py-2.5 text-slate-400">
                              {new Date(j.created_at).toLocaleString()}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
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
                        src="http://localhost:8000/api/v1/embed/report"
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
