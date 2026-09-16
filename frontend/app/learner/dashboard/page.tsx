"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { Navbar } from "@/components/Navbar";
import { Sidebar } from "@/components/Sidebar";
import {
  Compass,
  Award,
  TrendingUp,
  Clock,
  Sparkles,
  ArrowRight,
  CheckCircle2,
  AlertCircle,
  HelpCircle,
  BookOpen,
} from "lucide-react";

export default function LearnerDashboard() {
  const [user, setUser] = useState<any>(null);
  const [analytics, setAnalytics] = useState<any>(null);
  const [competencies, setCompetencies] = useState<any[]>([]);
  const [adaptiveRec, setAdaptiveRec] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function loadData() {
      if (typeof window === "undefined") return;
      const stored = localStorage.getItem("user");
      const token = localStorage.getItem("access_token");
      if (!stored || !token) {
        window.location.href = "/login";
        return;
      }

      const u = JSON.parse(stored);
      setUser(u);
      const headers = { Authorization: `Bearer ${token}` };

      try {
        // 1. Fetch Learner Analytics
        const aRes = await fetch(`http://localhost:8000/api/v1/analytics/learner/${u.id}`, { headers });
        if (aRes.ok) setAnalytics(await aRes.json());

        // 2. Fetch Competencies
        const cRes = await fetch(`http://localhost:8000/api/v1/adaptive/competencies/${u.id}`, { headers });
        if (cRes.ok) setCompetencies(await cRes.json());

        // 3. Fetch Adaptive Next Step
        // First get a course ID
        const coursesRes = await fetch("http://localhost:8000/api/v1/courses", { headers });
        if (coursesRes.ok) {
          const courses = await coursesRes.json();
          if (courses.length > 0) {
            const nextRes = await fetch("http://localhost:8000/api/v1/adaptive/next", {
              method: "POST",
              headers: { ...headers, "Content-Type": "application/json" },
              body: JSON.stringify({
                session_id: "00000000-0000-0000-0000-000000000001",
                course_id: courses[0].id,
              }),
            });
            if (nextRes.ok) setAdaptiveRec(await nextRes.json());
          }
        }
      } catch (err) {
        console.error("Failed to load dashboard data", err);
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, []);

  const getDecisionBadge = (decision: string) => {
    switch (decision) {
      case "advance":
        return "bg-emerald-100 text-emerald-800 border-emerald-300";
      case "skip":
        return "bg-purple-100 text-purple-800 border-purple-300";
      case "remediate":
        return "bg-amber-100 text-amber-800 border-amber-300";
      case "change_modality":
        return "bg-blue-100 text-blue-800 border-blue-300";
      default:
        return "bg-slate-100 text-slate-800 border-slate-300";
    }
  };

  return (
    <div className="min-h-screen bg-slate-50">
      <Navbar />
      <div className="flex">
        <Sidebar />
        <main className="flex-1 p-8 max-w-6xl">
          {/* Greeting Header */}
          <div className="mb-8 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
            <div>
              <h1 className="text-2xl font-bold text-slate-900 tracking-tight">
                Welcome back, {user?.full_name?.split(" ")[0] || "Learner"}!
              </h1>
              <p className="text-sm text-slate-500 mt-1">
                Your learning path is dynamically personalized in real time based on demonstrated mastery.
              </p>
            </div>
            <div className="flex items-center gap-2">
              <Link
                href="/learner/learning"
                className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg bg-indigo-600 text-white text-sm font-semibold hover:bg-indigo-700 transition-colors shadow-sm"
              >
                <Compass className="w-4 h-4" /> Start Adaptive Session
              </Link>
              <Link
                href="/learner/insights"
                className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg bg-white border border-slate-200 text-slate-700 text-sm font-semibold hover:bg-slate-50 transition-colors shadow-sm"
              >
                <Sparkles className="w-4 h-4 text-indigo-600" /> AI Insights
              </Link>
            </div>
          </div>

          {/* Real-time Adaptive Next Recommendation Banner */}
          {adaptiveRec && (
            <div className="mb-8 p-5 bg-gradient-to-r from-indigo-50/80 via-white to-indigo-50/30 border border-indigo-200 rounded-2xl shadow-sm">
              <div className="flex items-start justify-between gap-4">
                <div className="space-y-1.5">
                  <div className="flex items-center gap-2">
                    <span className="flex h-2.5 w-2.5 rounded-full bg-indigo-600 animate-pulse" />
                    <span className="text-xs font-bold uppercase tracking-wider text-indigo-700">
                      Real-Time Pedagogical Sequencing
                    </span>
                    <span className={`px-2 py-0.5 rounded-full text-xs font-bold uppercase border ${getDecisionBadge(adaptiveRec.decision)}`}>
                      Decision: {adaptiveRec.decision}
                    </span>
                  </div>
                  <h3 className="text-lg font-bold text-slate-900">
                    Recommended: {adaptiveRec.recommended_content_title || adaptiveRec.competency_name || "Foundations Review"}
                  </h3>
                  <p className="text-sm text-slate-600 max-w-3xl leading-relaxed">
                    {adaptiveRec.reason}
                  </p>
                </div>
                <Link
                  href="/learner/learning"
                  className="flex-shrink-0 inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-indigo-600 text-white text-xs font-semibold hover:bg-indigo-700 transition-colors"
                >
                  Jump to Lesson <ArrowRight className="w-3.5 h-3.5" />
                </Link>
              </div>
            </div>
          )}

          {/* Metric KPI Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
            <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm">
              <div className="flex items-center justify-between text-slate-500 mb-2">
                <span className="text-xs font-semibold uppercase tracking-wider">Average Mastery</span>
                <Award className="w-5 h-5 text-indigo-600" />
              </div>
              <div className="text-2xl font-bold text-slate-900">
                {analytics?.average_mastery !== undefined ? `${Math.round(analytics.average_mastery * 100)}%` : "--"}
              </div>
              <p className="text-xs text-slate-500 mt-1">Multi-factor Bayesian mastery</p>
            </div>

            <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm">
              <div className="flex items-center justify-between text-slate-500 mb-2">
                <span className="text-xs font-semibold uppercase tracking-wider">Accuracy Rate</span>
                <CheckCircle2 className="w-5 h-5 text-emerald-600" />
              </div>
              <div className="text-2xl font-bold text-slate-900">
                {analytics?.accuracy_rate !== undefined ? `${Math.round(analytics.accuracy_rate * 100)}%` : "--"}
              </div>
              <p className="text-xs text-slate-500 mt-1">Across diagnostic questions</p>
            </div>

            <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm">
              <div className="flex items-center justify-between text-slate-500 mb-2">
                <span className="text-xs font-semibold uppercase tracking-wider">Avg Latency</span>
                <Clock className="w-5 h-5 text-blue-600" />
              </div>
              <div className="text-2xl font-bold text-slate-900">
                {analytics?.avg_response_time_ms ? `${(analytics.avg_response_time_ms / 1000).toFixed(1)}s` : "--"}
              </div>
              <p className="text-xs text-slate-500 mt-1">Question response time</p>
            </div>

            <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm">
              <div className="flex items-center justify-between text-slate-500 mb-2">
                <span className="text-xs font-semibold uppercase tracking-wider">Course Progress</span>
                <TrendingUp className="w-5 h-5 text-purple-600" />
              </div>
              <div className="text-2xl font-bold text-slate-900">
                {analytics?.average_course_progress_pct !== undefined ? `${analytics.average_course_progress_pct}%` : "--"}
              </div>
              <p className="text-xs text-slate-500 mt-1">Active curriculum completion</p>
            </div>
          </div>

          {/* Competency Mastery Overview */}
          <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="text-base font-bold text-slate-900">Live Competency Mastery Graph</h3>
                <p className="text-xs text-slate-500">Real-time state estimates calibrated against your learning events</p>
              </div>
              <span className="text-xs font-medium px-2.5 py-1 rounded-full bg-slate-100 text-slate-700">
                {competencies.length} Competencies Evaluated
              </span>
            </div>

            <div className="space-y-4">
              {competencies.length === 0 ? (
                <div className="py-8 text-center text-sm text-slate-400">
                  No competency evidence recorded yet. Complete an assessment to initialize your model.
                </div>
              ) : (
                competencies.map((comp) => {
                  const pct = Math.round(comp.mastery * 100);
                  const isHigh = pct >= 80;
                  const isLow = pct < 50;
                  const barColor = isHigh ? "bg-emerald-600" : isLow ? "bg-rose-500" : "bg-indigo-600";
                  return (
                    <div key={comp.competency_id} className="p-4 rounded-xl bg-slate-50 border border-slate-200/80">
                      <div className="flex items-center justify-between mb-2">
                        <div>
                          <div className="text-sm font-semibold text-slate-900">{comp.name}</div>
                          <div className="text-xs text-slate-400 capitalize">Taxonomy: {comp.domain || "understand"}</div>
                        </div>
                        <div className="flex items-center gap-3">
                          <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-white border border-slate-200 text-slate-700 capitalize">
                            Status: {comp.status}
                          </span>
                          <span className="text-sm font-bold text-slate-900">{pct}%</span>
                        </div>
                      </div>
                      <div className="w-full bg-slate-200 h-2.5 rounded-full overflow-hidden">
                        <div className={`h-full rounded-full transition-all duration-500 ${barColor}`} style={{ width: `${pct}%` }} />
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}
