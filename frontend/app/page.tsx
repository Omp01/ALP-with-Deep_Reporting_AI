"use client";

import React, { useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  Sparkles,
  Compass,
  FileCheck2,
  Users,
  Layers,
  ArrowRight,
  ShieldCheck,
  Zap,
} from "lucide-react";

export default function HomePage() {
  const router = useRouter();

  useEffect(() => {
    if (typeof window !== "undefined") {
      const token = localStorage.getItem("access_token");
      const storedUser = localStorage.getItem("user");
      if (token && storedUser) {
        try {
          const u = JSON.parse(storedUser);
          if (u.role === "manager" || u.role === "instructor") {
            router.push("/manager/dashboard");
          } else if (u.role === "org_admin" || u.role === "admin" || u.role === "super_admin") {
            router.push("/admin/dashboard");
          } else {
            router.push("/learner/dashboard");
          }
        } catch (e) {}
      }
    }
  }, [router]);

  return (
    <div className="min-h-screen flex flex-col bg-slate-50">
      {/* Header */}
      <header className="border-b border-slate-200 bg-white sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-indigo-600 flex items-center justify-center shadow-xs">
              <span className="text-white font-bold text-base">A</span>
            </div>
            <div>
              <span className="text-base font-bold text-slate-900 tracking-tight block">
                Adaptive LMS
              </span>
              <span className="text-[10px] text-slate-400 font-medium block">
                Deep Reporting AI
              </span>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <a
              href="http://localhost:8000/docs"
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs font-semibold text-slate-600 hover:text-slate-900 px-3 py-1.5 rounded-lg hover:bg-slate-50 transition-colors"
            >
              API Swagger
            </a>
            <button
              onClick={() => router.push("/login")}
              className="px-4 py-2 bg-indigo-600 text-white text-xs font-semibold rounded-lg hover:bg-indigo-700 transition-colors shadow-xs"
            >
              Sign In / Switch Persona
            </button>
          </div>
        </div>
      </header>

      {/* Hero */}
      <main className="flex-1 flex items-center justify-center bg-gradient-to-b from-white to-slate-50">
        <div className="max-w-4xl mx-auto px-6 py-16 text-center animate-fade-in">
          <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-indigo-50 text-indigo-700 text-xs font-semibold mb-6 border border-indigo-200 shadow-2xs">
            <Sparkles className="w-3.5 h-3.5 text-indigo-600" />
            Live Bayesian Competency & Grounded AI Reporting
          </div>

          <h1 className="text-4xl sm:text-5xl font-extrabold text-slate-900 tracking-tight leading-tight mb-6">
            Adaptive Learning Management with{" "}
            <span className="text-transparent bg-clip-text bg-gradient-to-r from-indigo-600 to-teal-600">
              Deep Reporting AI
            </span>
          </h1>

          <p className="text-base sm:text-lg text-slate-600 max-w-2xl mx-auto mb-8 leading-relaxed">
            A containerized enterprise LMS modeling real understanding through Bayesian evidence, real-time pedagogical sequencing, multi-signal risk intervention, and verifiable AI reports with clickable citations.
          </p>

          {/* Quick Action CTAs */}
          <div className="flex flex-col sm:flex-row items-center justify-center gap-3 mb-14">
            <button
              onClick={() => router.push("/login")}
              className="w-full sm:w-auto px-6 py-3 bg-indigo-600 text-white text-sm font-semibold rounded-xl hover:bg-indigo-700 transition-all shadow-md hover:shadow-lg flex items-center justify-center gap-2"
            >
              Explore Demo Personas <ArrowRight className="w-4 h-4" />
            </button>
            <a
              href="http://localhost:8000/api/v1/embed/report"
              target="_blank"
              rel="noopener noreferrer"
              className="w-full sm:w-auto px-6 py-3 bg-white text-slate-700 text-sm font-semibold rounded-xl border border-slate-300 hover:border-slate-400 hover:bg-slate-50 transition-all shadow-xs"
            >
              Preview Embeddable Widget
            </a>
          </div>

          {/* Feature Highlights Grid */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-5 text-left mb-12">
            <div className="p-6 rounded-2xl border border-slate-200 bg-white shadow-xs hover:shadow-md transition-shadow">
              <div className="w-10 h-10 rounded-xl bg-indigo-50 text-indigo-600 flex items-center justify-center mb-4 font-bold">
                <Compass className="w-5 h-5" />
              </div>
              <h3 className="font-bold text-slate-900 mb-1.5 text-base">Adaptive Sequencing</h3>
              <p className="text-xs text-slate-600 leading-relaxed">
                Deterministic pedagogical policies (remediate, advance, skip, change modality) driven by multi-factor mastery algorithms.
              </p>
            </div>

            <div className="p-6 rounded-2xl border border-slate-200 bg-white shadow-xs hover:shadow-md transition-shadow">
              <div className="w-10 h-10 rounded-xl bg-emerald-50 text-emerald-600 flex items-center justify-center mb-4 font-bold">
                <ShieldCheck className="w-5 h-5" />
              </div>
              <h3 className="font-bold text-slate-900 mb-1.5 text-base">Grounded AI Citations</h3>
              <p className="text-xs text-slate-600 leading-relaxed">
                Narrative reports backed by strict telemetry fact packages. Clickable [E-#] citations let users inspect exact underlying evidence.
              </p>
            </div>

            <div className="p-6 rounded-2xl border border-slate-200 bg-white shadow-xs hover:shadow-md transition-shadow">
              <div className="w-10 h-10 rounded-xl bg-amber-50 text-amber-600 flex items-center justify-center mb-4 font-bold">
                <Zap className="w-5 h-5" />
              </div>
              <h3 className="font-bold text-slate-900 mb-1.5 text-base">Multi-Signal Early Warning</h3>
              <p className="text-xs text-slate-600 leading-relaxed">
                Autonomous risk anomaly detection evaluating latency spikes, consecutive failures, and stagnation with one-click resolution.
              </p>
            </div>
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-200 bg-white py-6">
        <div className="max-w-7xl mx-auto px-6 text-center text-xs text-slate-500">
          Adaptive Learning Management System · Multi-Tenant B2B Architecture · All Systems Operational
        </div>
      </footer>
    </div>
  );
}
