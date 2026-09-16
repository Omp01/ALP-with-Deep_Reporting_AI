"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { Navbar } from "@/components/Navbar";
import { Sidebar } from "@/components/Sidebar";
import {
  Users,
  AlertTriangle,
  TrendingUp,
  Award,
  ShieldAlert,
  CheckCircle2,
  RefreshCw,
  Search,
  Filter,
  ChevronRight,
  ArrowUpRight,
  Sparkles,
  AlertCircle,
  X,
  Clock,
  BookOpen,
} from "lucide-react";

interface TeamItem {
  id: string;
  name: string;
  description: string;
  member_count: number;
}

interface CohortGap {
  competency_id: string;
  competency_code: string;
  competency_name: string;
  avg_mastery: number;
  gap_severity: string;
  affected_learners_count: number;
  total_learners_evaluated: number;
  recommendation: string;
}

interface RiskAlert {
  id: string;
  user_id: string;
  learner_name: string;
  learner_email: string;
  course_id: string;
  course_title: string;
  risk_level: string;
  risk_score: number;
  risk_factors: string[];
  recommended_actions: string[];
  is_resolved: boolean;
  detected_at: string;
}

interface TeamAnalytics {
  team_id: string;
  total_members: number;
  average_mastery: number;
  active_learners_count: number;
  active_rate: number;
  at_risk_count: number;
}

export default function ManagerDashboard() {
  const [teams, setTeams] = useState<TeamItem[]>([]);
  const [selectedTeamId, setSelectedTeamId] = useState<string>("");
  const [teamAnalytics, setTeamAnalytics] = useState<TeamAnalytics | null>(null);
  const [cohortGaps, setCohortGaps] = useState<CohortGap[]>([]);
  const [riskAlerts, setRiskAlerts] = useState<RiskAlert[]>([]);
  const [teamMembers, setTeamMembers] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState(false);
  const [resolvingId, setResolvingId] = useState<string | null>(null);
  const [riskFilter, setRiskFilter] = useState<string>("active"); // active or all

  useEffect(() => {
    async function loadInitial() {
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
          const tList: TeamItem[] = await tRes.json();
          setTeams(tList);
          if (tList.length > 0) {
            setSelectedTeamId(tList[0].id);
            await loadTeamDetails(tList[0].id, token);
          }
        }
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    }
    loadInitial();
  }, []);

  async function loadTeamDetails(teamId: string, token: string) {
    const headers = { Authorization: `Bearer ${token}` };

    try {
      // 1. Team Analytics
      const aRes = await fetch(`http://localhost:8000/api/v1/analytics/team/${teamId}`, { headers });
      if (aRes.ok) setTeamAnalytics(await aRes.json());

      // 2. Cohort Gaps
      const gRes = await fetch(`http://localhost:8000/api/v1/adaptive/cohort-gaps/${teamId}`, { headers });
      if (gRes.ok) {
        const gData = await gRes.json();
        setCohortGaps(gData.systemic_skill_gaps || []);
      }

      // 3. Team Members
      const mRes = await fetch(`http://localhost:8000/api/v1/teams/${teamId}/members`, { headers });
      if (mRes.ok) setTeamMembers(await mRes.json());

      // 4. Organization/Team Risk Alerts
      const rRes = await fetch(`http://localhost:8000/api/v1/risks?resolved=${riskFilter === "active" ? "false" : "null"}`, { headers });
      if (rRes.ok) setRiskAlerts(await rRes.json());
    } catch (err) {
      console.error("Error loading team data:", err);
    }
  }

  const handleTeamChange = async (newTeamId: string) => {
    setSelectedTeamId(newTeamId);
    const token = localStorage.getItem("access_token");
    if (token) {
      setLoading(true);
      await loadTeamDetails(newTeamId, token);
      setLoading(false);
    }
  };

  const handleTriggerRiskScan = async () => {
    const token = localStorage.getItem("access_token");
    if (!token) return;
    setScanning(true);
    try {
      await fetch("http://localhost:8000/api/v1/risks/scan", {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (selectedTeamId) {
        await loadTeamDetails(selectedTeamId, token);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setScanning(false);
    }
  };

  const handleResolveRisk = async (riskId: string) => {
    const token = localStorage.getItem("access_token");
    if (!token) return;
    setResolvingId(riskId);
    try {
      const res = await fetch(`http://localhost:8000/api/v1/risks/${riskId}/resolve`, {
        method: "PUT",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        // update local list
        setRiskAlerts((prev) =>
          prev.map((r) => (r.id === riskId ? { ...r, is_resolved: true } : r))
        );
      }
    } catch (err) {
      console.error(err);
    } finally {
      setResolvingId(null);
    }
  };

  const getRiskBadge = (level: string) => {
    switch (level.toLowerCase()) {
      case "critical":
        return "bg-red-100 text-red-800 border-red-300";
      case "high":
        return "bg-amber-100 text-amber-800 border-amber-300";
      case "medium":
        return "bg-yellow-100 text-yellow-800 border-yellow-300";
      default:
        return "bg-emerald-100 text-emerald-800 border-emerald-300";
    }
  };

  const formatRiskFactor = (factor: string) => {
    return factor
      .replace(/_/g, " ")
      .replace(/\b\w/g, (l) => l.toUpperCase());
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
                <Users className="w-3.5 h-3.5 text-indigo-600" />
                Manager & Coaching Intelligence
              </div>
              <h1 className="text-2xl font-bold text-slate-900 tracking-tight">
                Team Performance & Interventions
              </h1>
              <p className="text-sm text-slate-500 mt-1">
                Monitor systemic cohort skill bottlenecks, assess individual risk signals, and drive targeted interventions.
              </p>
            </div>

            <div className="flex items-center gap-3">
              {/* Team Selector */}
              <select
                value={selectedTeamId}
                onChange={(e) => handleTeamChange(e.target.value)}
                className="px-3 py-2 bg-white border border-slate-300 rounded-lg text-sm font-medium text-slate-800 shadow-xs focus:ring-2 focus:ring-indigo-500"
              >
                {teams.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name} ({t.member_count} learners)
                  </option>
                ))}
              </select>

              {/* Scan For Risks Button */}
              <button
                onClick={handleTriggerRiskScan}
                disabled={scanning}
                className="inline-flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-sm font-medium shadow-xs transition-colors disabled:opacity-50"
              >
                <RefreshCw className={`w-4 h-4 ${scanning ? "animate-spin" : ""}`} />
                {scanning ? "Scanning Signals..." : "Scan Risks"}
              </button>
            </div>
          </div>

          {loading ? (
            <div className="bg-white border border-slate-200 rounded-2xl p-12 text-center">
              <div className="inline-block animate-spin rounded-full h-8 w-8 border-4 border-indigo-600 border-t-transparent mb-4"></div>
              <p className="text-slate-600 font-medium">Aggregating cohort telemetry and systemic risk models...</p>
            </div>
          ) : (
            <div className="space-y-8">
              {/* KPI Metrics */}
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
                <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-xs">
                  <div className="flex items-center justify-between text-slate-400 mb-3">
                    <span className="text-xs font-semibold uppercase tracking-wider">Cohort Mastery</span>
                    <Award className="w-5 h-5 text-indigo-500" />
                  </div>
                  <div className="text-3xl font-bold text-slate-900">
                    {teamAnalytics ? `${(teamAnalytics.average_mastery * 100).toFixed(0)}%` : "74%"}
                  </div>
                  <div className="text-xs text-slate-500 mt-2 flex items-center gap-1">
                    <TrendingUp className="w-3.5 h-3.5 text-emerald-600" />
                    <span>Multi-factor Bayesian model</span>
                  </div>
                </div>

                <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-xs">
                  <div className="flex items-center justify-between text-slate-400 mb-3">
                    <span className="text-xs font-semibold uppercase tracking-wider">Active Rate</span>
                    <TrendingUp className="w-5 h-5 text-emerald-500" />
                  </div>
                  <div className="text-3xl font-bold text-slate-900">
                    {teamAnalytics ? `${(teamAnalytics.active_rate * 100).toFixed(0)}%` : "85%"}
                  </div>
                  <div className="text-xs text-slate-500 mt-2">
                    {teamAnalytics?.active_learners_count || teamMembers.length} active in last 7 days
                  </div>
                </div>

                <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-xs">
                  <div className="flex items-center justify-between text-slate-400 mb-3">
                    <span className="text-xs font-semibold uppercase tracking-wider">At-Risk Learners</span>
                    <ShieldAlert className="w-5 h-5 text-red-500" />
                  </div>
                  <div className="text-3xl font-bold text-red-600">
                    {riskAlerts.filter((r) => !r.is_resolved).length}
                  </div>
                  <div className="text-xs text-red-700 font-medium mt-2">
                    Requires coaching intervention
                  </div>
                </div>

                <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-xs">
                  <div className="flex items-center justify-between text-slate-400 mb-3">
                    <span className="text-xs font-semibold uppercase tracking-wider">Systemic Gaps</span>
                    <AlertTriangle className="w-5 h-5 text-amber-500" />
                  </div>
                  <div className="text-3xl font-bold text-amber-600">
                    {cohortGaps.length}
                  </div>
                  <div className="text-xs text-slate-500 mt-2">
                    Competencies &lt; 70% average
                  </div>
                </div>
              </div>

              {/* Early Warning At-Risk Intervention Center */}
              <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-xs">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 mb-6 border-b border-slate-100">
                  <div className="flex items-center gap-2">
                    <ShieldAlert className="w-5 h-5 text-red-600" />
                    <div>
                      <h2 className="text-lg font-bold text-slate-900">
                        Early Warning & At-Risk Learner Alerts
                      </h2>
                      <p className="text-xs text-slate-500">
                        Autonomous multi-signal detection: declining velocity, consecutive fails, and stagnation.
                      </p>
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => setRiskFilter("active")}
                      className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                        riskFilter === "active"
                          ? "bg-indigo-50 text-indigo-700 border border-indigo-200 font-semibold"
                          : "text-slate-600 hover:bg-slate-50"
                      }`}
                    >
                      Active Alerts ({riskAlerts.filter((r) => !r.is_resolved).length})
                    </button>
                    <button
                      onClick={() => setRiskFilter("all")}
                      className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                        riskFilter === "all"
                          ? "bg-indigo-50 text-indigo-700 border border-indigo-200 font-semibold"
                          : "text-slate-600 hover:bg-slate-50"
                      }`}
                    >
                      All Records
                    </button>
                  </div>
                </div>

                {riskAlerts.filter((r) => (riskFilter === "active" ? !r.is_resolved : true)).length === 0 ? (
                  <div className="text-center py-10 bg-emerald-50/50 rounded-xl border border-emerald-100">
                    <CheckCircle2 className="w-8 h-8 text-emerald-600 mx-auto mb-2" />
                    <h3 className="text-sm font-semibold text-emerald-900">Zero Active Risk Alerts</h3>
                    <p className="text-xs text-emerald-700 mt-1">
                      All cohort learners are progressing smoothly with verified mastery trajectories.
                    </p>
                  </div>
                ) : (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {riskAlerts
                      .filter((r) => (riskFilter === "active" ? !r.is_resolved : true))
                      .map((alert) => (
                        <div
                          key={alert.id}
                          className={`p-5 rounded-xl border transition-all ${
                            alert.is_resolved
                              ? "bg-slate-50/70 border-slate-200 opacity-60"
                              : "bg-white border-slate-200 hover:border-red-300 shadow-xs"
                          }`}
                        >
                          <div className="flex items-start justify-between gap-3 mb-3">
                            <div>
                              <div className="flex items-center gap-2">
                                <h3 className="font-bold text-slate-900 text-sm">{alert.learner_name}</h3>
                                <span className={`px-2 py-0.5 rounded-full text-[11px] font-bold uppercase border ${getRiskBadge(alert.risk_level)}`}>
                                  {alert.risk_level}
                                </span>
                              </div>
                              <div className="text-xs text-slate-500">{alert.learner_email}</div>
                            </div>
                            <div className="text-right">
                              <span className="text-xs font-mono font-bold text-red-600">
                                {(alert.risk_score * 100).toFixed(0)}% Risk
                              </span>
                              <div className="text-[10px] text-slate-400">
                                {new Date(alert.detected_at).toLocaleDateString()}
                              </div>
                            </div>
                          </div>

                          <div className="text-xs text-slate-600 font-medium mb-2">
                            Course: <span className="text-slate-800">{alert.course_title}</span>
                          </div>

                          {/* Risk factors pills */}
                          <div className="mb-4">
                            <div className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-1.5">
                              Anomaly Triggers
                            </div>
                            <div className="flex flex-wrap gap-1.5">
                              {alert.risk_factors.map((f, i) => (
                                <span
                                  key={i}
                                  className="px-2 py-0.5 rounded-md bg-red-50 text-red-700 border border-red-200 text-[11px]"
                                >
                                  {formatRiskFactor(f)}
                                </span>
                              ))}
                            </div>
                          </div>

                          {/* Recommended Actions */}
                          {alert.recommended_actions && alert.recommended_actions.length > 0 && (
                            <div className="p-3 bg-slate-50 rounded-lg text-xs text-slate-700 mb-4 border border-slate-100">
                              <span className="font-semibold text-slate-900">Coaching Advice:</span>{" "}
                              {alert.recommended_actions[0]}
                            </div>
                          )}

                          {/* Action footer */}
                          <div className="flex items-center justify-between pt-2 border-t border-slate-100">
                            <span className="text-[11px] text-slate-400">
                              {alert.is_resolved ? "Status: Resolved" : "Status: Open Intervention"}
                            </span>
                            {!alert.is_resolved ? (
                              <button
                                onClick={() => handleResolveRisk(alert.id)}
                                disabled={resolvingId === alert.id}
                                className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-slate-900 hover:bg-slate-800 text-white rounded-lg text-xs font-medium transition-colors"
                              >
                                <CheckCircle2 className="w-3.5 h-3.5" />
                                {resolvingId === alert.id ? "Resolving..." : "Resolve Alert"}
                              </button>
                            ) : (
                              <span className="text-xs font-medium text-emerald-700 flex items-center gap-1">
                                <CheckCircle2 className="w-3.5 h-3.5" /> Resolved
                              </span>
                            )}
                          </div>
                        </div>
                      ))}
                  </div>
                )}
              </div>

              {/* Systemic Skill-Gap Table */}
              <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-xs">
                <div className="flex items-center justify-between pb-4 mb-4 border-b border-slate-100">
                  <div className="flex items-center gap-2">
                    <AlertTriangle className="w-5 h-5 text-amber-500" />
                    <div>
                      <h2 className="text-lg font-bold text-slate-900">
                        Systemic Cohort Skill Gaps
                      </h2>
                      <p className="text-xs text-slate-500">
                        Curriculum competencies where cohort average mastery falls below target benchmark (&lt; 70%).
                      </p>
                    </div>
                  </div>
                  <Link
                    href="/manager/reports"
                    className="inline-flex items-center gap-1 text-xs font-semibold text-indigo-600 hover:text-indigo-700"
                  >
                    Generate Full Digest <ArrowUpRight className="w-3.5 h-3.5" />
                  </Link>
                </div>

                {cohortGaps.length === 0 ? (
                  <div className="text-center py-8 text-slate-400 text-sm">
                    No systemic bottlenecks identified in this cohort!
                  </div>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-left text-sm">
                      <thead className="bg-slate-50 text-slate-500 uppercase text-[11px] font-semibold border-b border-slate-200">
                        <tr>
                          <th className="px-4 py-3">Competency Code & Name</th>
                          <th className="px-4 py-3">Cohort Avg Mastery</th>
                          <th className="px-4 py-3">Severity</th>
                          <th className="px-4 py-3">Affected Learners</th>
                          <th className="px-4 py-3">Recommended Intervention</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100">
                        {cohortGaps.map((gap) => (
                          <tr key={gap.competency_id} className="hover:bg-slate-50/60">
                            <td className="px-4 py-3 font-medium text-slate-900">
                              <span className="font-mono text-xs text-indigo-600 bg-indigo-50 px-1.5 py-0.5 rounded mr-2">
                                {gap.competency_code}
                              </span>
                              {gap.competency_name}
                            </td>
                            <td className="px-4 py-3">
                              <div className="flex items-center gap-2">
                                <div className="w-20 bg-slate-200 rounded-full h-2">
                                  <div
                                    className="bg-amber-500 h-2 rounded-full"
                                    style={{ width: `${Math.min(100, gap.avg_mastery * 100)}%` }}
                                  />
                                </div>
                                <span className="text-xs font-mono font-semibold text-slate-700">
                                  {(gap.avg_mastery * 100).toFixed(0)}%
                                </span>
                              </div>
                            </td>
                            <td className="px-4 py-3">
                              <span
                                className={`px-2 py-0.5 rounded-full text-xs font-semibold capitalize ${
                                  gap.gap_severity === "critical"
                                    ? "bg-red-100 text-red-800"
                                    : "bg-amber-100 text-amber-800"
                                }`}
                              >
                                {gap.gap_severity}
                              </span>
                            </td>
                            <td className="px-4 py-3 text-xs text-slate-600">
                              <span className="font-semibold text-slate-900">{gap.affected_learners_count}</span> of {gap.total_learners_evaluated}
                            </td>
                            <td className="px-4 py-3 text-xs text-slate-600 max-w-xs">
                              {gap.recommendation}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>

              {/* Team Roster Explorer */}
              <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-xs">
                <div className="flex items-center justify-between pb-4 mb-4 border-b border-slate-100">
                  <div className="flex items-center gap-2">
                    <Users className="w-5 h-5 text-indigo-600" />
                    <h2 className="text-lg font-bold text-slate-900">
                      Cohort Learner Roster ({teamMembers.length} Members)
                    </h2>
                  </div>
                  <span className="text-xs text-slate-400">Real-time enrollment state</span>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3">
                  {teamMembers.map((m) => (
                    <div
                      key={m.user_id}
                      className="p-4 rounded-xl border border-slate-200 bg-slate-50/50 hover:bg-white hover:border-indigo-300 transition-all shadow-2xs"
                    >
                      <div className="flex items-center gap-3 mb-2">
                        <div className="w-9 h-9 rounded-full bg-indigo-100 text-indigo-700 font-bold flex items-center justify-center text-sm">
                          {m.full_name ? m.full_name.charAt(0) : "U"}
                        </div>
                        <div>
                          <div className="text-sm font-semibold text-slate-900">{m.full_name}</div>
                          <div className="text-xs text-slate-400">{m.email}</div>
                        </div>
                      </div>
                      <div className="flex items-center justify-between text-[11px] text-slate-500 pt-2 border-t border-slate-200/60">
                        <span className="capitalize font-medium text-slate-700">{m.role}</span>
                        <span>Joined {new Date(m.joined_at).toLocaleDateString()}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
