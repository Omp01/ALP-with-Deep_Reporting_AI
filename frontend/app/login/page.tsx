"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import { Sparkles, Shield, ArrowRight, UserCheck, AlertCircle, Building2 } from "lucide-react";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("alice.learner@acme.com");
  const [password, setPassword] = useState("Password123!");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const personas = [
    {
      role: "Learner",
      name: "Alice Adams",
      archetype: "High Mastery",
      email: "alice.learner@acme.com",
      badge: "Mastery > 0.85",
      badgeColor: "bg-emerald-50 text-emerald-700 border-emerald-200",
      description: "Consistent fast answers, skips introductory modules, advances rapidly.",
    },
    {
      role: "Learner",
      name: "Bob Bennett",
      archetype: "Shallow Completion",
      email: "bob.learner@acme.com",
      badge: "Fast Scroll / Low Accuracy",
      badgeColor: "bg-amber-50 text-amber-700 border-amber-200",
      description: "100% course progress click-through, but fails diagnostic assessments.",
    },
    {
      role: "Learner",
      name: "Carol Clark",
      archetype: "Declining / Struggle",
      email: "carol.learner@acme.com",
      badge: "Declining Mastery",
      badgeColor: "bg-rose-50 text-rose-700 border-rose-200",
      description: "Multiple retry attempts, increasing response latency, needs remediation.",
    },
    {
      role: "Learner",
      name: "Dan Davis",
      archetype: "Disengaged Risk",
      email: "dan.learner@acme.com",
      badge: "Critical Inactivity",
      badgeColor: "bg-purple-50 text-purple-700 border-purple-200",
      description: "No activity for 10+ days, triggered early warning dropout alert.",
    },
    {
      role: "Manager",
      name: "Marcus Manager",
      archetype: "Engineering Lead",
      email: "marcus.manager@acme.com",
      badge: "Cohort Coach",
      badgeColor: "bg-blue-50 text-blue-700 border-blue-200",
      description: "Monitors team skill gaps, views at-risk alerts, assigns interventions.",
    },
    {
      role: "Admin",
      name: "Arthur Admin",
      archetype: "L&D Director",
      email: "admin@acme.com",
      badge: "Org Admin",
      badgeColor: "bg-slate-100 text-slate-800 border-slate-300",
      description: "Oversees curriculum, executes risk scans, generates grounded reports, exports BI data.",
    },
  ];

  const handleLogin = async (targetEmail = email, targetPassword = password) => {
    setLoading(true);
    setError(null);

    try {
      const res = await fetch("http://localhost:8000/api/v1/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: targetEmail, password: targetPassword }),
      });

      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || "Authentication failed");
      }

      const data = await res.json();
      localStorage.setItem("access_token", data.access_token);
      localStorage.setItem("user", JSON.stringify(data.user));

      // Route by role
      if (data.user.role === "org_admin" || data.user.role === "super_admin") {
        router.push("/admin/dashboard");
      } else if (data.user.role === "manager" || data.user.role === "instructor") {
        router.push("/manager/dashboard");
      } else {
        // Every learner login starts with a fresh AI-written check-in (skippable), then the dashboard.
        try {
          sessionStorage.setItem("checkin_pending", "1");
          sessionStorage.removeItem("checkin_current");
        } catch {
          /* without session storage the check-in page simply offers a Start button */
        }
        router.push("/learner/checkin");
      }
    } catch (err: any) {
      setError(err.message || "An unexpected error occurred");
    } finally {
      setLoading(false);
    }
  };

  const quickSelectPersona = (p: (typeof personas)[0]) => {
    setEmail(p.email);
    setPassword("Password123!");
    handleLogin(p.email, "Password123!");
  };

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col justify-center py-12 px-4 sm:px-6 lg:px-8">
      <div className="sm:mx-auto sm:w-full sm:max-w-md text-center">
        <div className="w-12 h-12 rounded-xl bg-indigo-600 text-white flex items-center justify-center font-bold text-2xl mx-auto shadow-md">
          A
        </div>
        <h2 className="mt-4 text-2xl font-bold tracking-tight text-slate-900">
          Adaptive Learning Platform
        </h2>
        <p className="mt-1 text-sm text-slate-500">
          Sign in to test adaptive sequencing & deep reporting AI
        </p>
      </div>

      <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-4xl">
        <div className="bg-white py-8 px-6 shadow-sm border border-slate-200 rounded-2xl sm:px-10">
          {error && (
            <div className="mb-6 p-4 rounded-xl bg-rose-50 border border-rose-200 text-rose-800 text-sm flex items-center gap-2.5">
              <AlertCircle className="w-5 h-5 flex-shrink-0 text-rose-600" />
              <span>{error}</span>
            </div>
          )}

          {/* Persona Quick Select */}
          <div className="mb-8">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-500 flex items-center gap-2">
                <UserCheck className="w-4 h-4 text-indigo-600" />
                Select Demo Persona (One-Click Sign In)
              </h3>
              <span className="text-xs text-slate-400">Pre-seeded with real telemetry</span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              {personas.map((p) => (
                <button
                  key={p.email}
                  type="button"
                  onClick={() => quickSelectPersona(p)}
                  className="text-left p-3.5 rounded-xl border border-slate-200 hover:border-indigo-400 hover:bg-indigo-50/30 hover:shadow-sm transition-all group relative bg-white"
                >
                  <div className="flex items-start justify-between">
                    <div>
                      <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">{p.role}</span>
                      <div className="font-semibold text-slate-900 text-sm group-hover:text-indigo-600">{p.name}</div>
                    </div>
                    <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full border ${p.badgeColor}`}>
                      {p.badge}
                    </span>
                  </div>
                  <p className="mt-2 text-xs text-slate-500 leading-relaxed line-clamp-2">
                    {p.description}
                  </p>
                  <div className="mt-3 flex items-center gap-1 text-xs font-semibold text-indigo-600">
                    Sign in as {p.name.split(" ")[0]} <ArrowRight className="w-3.5 h-3.5" />
                  </div>
                </button>
              ))}
            </div>
          </div>

          <div className="relative my-6">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-slate-200" />
            </div>
            <div className="relative flex justify-center text-xs uppercase">
              <span className="bg-white px-3 text-slate-400 font-semibold tracking-wider">Or Manual Login</span>
            </div>
          </div>

          {/* Form */}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleLogin();
            }}
            className="space-y-4 max-w-md mx-auto"
          >
            <div>
              <label className="block text-sm font-medium text-slate-700">Work Email</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                className="mt-1 block w-full px-3.5 py-2.5 bg-white border border-slate-300 rounded-lg text-slate-900 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-600 focus:border-transparent"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-700">Password</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                className="mt-1 block w-full px-3.5 py-2.5 bg-white border border-slate-300 rounded-lg text-slate-900 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-600 focus:border-transparent"
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full mt-2 inline-flex items-center justify-center px-4 py-2.5 rounded-lg bg-indigo-600 text-white text-sm font-semibold hover:bg-indigo-700 transition-colors shadow-sm disabled:opacity-50"
            >
              {loading ? "Authenticating..." : "Sign In with Credentials"}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
