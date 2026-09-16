"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BookOpen,
  Compass,
  Award,
  Sparkles,
  Users,
  AlertTriangle,
  FileText,
  LayoutDashboard,
  Download,
  Settings,
  Layers,
} from "lucide-react";

export function Sidebar() {
  const pathname = usePathname();
  const [role, setRole] = useState<string>("learner");

  useEffect(() => {
    if (typeof window !== "undefined") {
      const stored = localStorage.getItem("user");
      if (stored) {
        try {
          const u = JSON.parse(stored);
          setRole(u.role || "learner");
        } catch (e) {}
      }
    }
  }, []);

  const isLearner = role === "learner";
  const isManager = role === "manager" || role === "instructor";
  const isAdmin = role === "org_admin" || role === "admin" || role === "super_admin";

  const learnerLinks = [
    { href: "/learner/dashboard", label: "My Dashboard", icon: LayoutDashboard },
    { href: "/learner/learning", label: "Adaptive Learning", icon: Compass },
    { href: "/learner/insights", label: "AI Insights & Why?", icon: Sparkles },
  ];

  const managerLinks = [
    { href: "/manager/dashboard", label: "Team Performance", icon: Users },
    { href: "/manager/reports", label: "Grounded Digests", icon: FileText },
  ];

  const adminLinks = [
    { href: "/admin/dashboard", label: "Executive Analytics", icon: Layers },
  ];

  return (
    <aside className="w-64 bg-white border-r border-slate-200 min-h-[calc(100vh-4rem)] p-4 flex flex-col justify-between">
      <div className="space-y-6">
        {/* Learner Section */}
        <div>
          <div className="px-3 text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">
            Learner Experience
          </div>
          <nav className="space-y-1">
            {learnerLinks.map((item) => {
              const active = pathname === item.href;
              const Icon = item.icon;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                    active
                      ? "bg-indigo-50 text-indigo-700 font-semibold border-l-4 border-indigo-600 pl-2"
                      : "text-slate-600 hover:text-slate-900 hover:bg-slate-50"
                  }`}
                >
                  <Icon className={`w-4 h-4 ${active ? "text-indigo-600" : "text-slate-400"}`} />
                  {item.label}
                </Link>
              );
            })}
          </nav>
        </div>

        {/* Manager Section */}
        {(isManager || isAdmin) && (
          <div>
            <div className="px-3 text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">
              Manager & Coaching
            </div>
            <nav className="space-y-1">
              {managerLinks.map((item) => {
                const active = pathname === item.href;
                const Icon = item.icon;
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                      active
                        ? "bg-indigo-50 text-indigo-700 font-semibold border-l-4 border-indigo-600 pl-2"
                        : "text-slate-600 hover:text-slate-900 hover:bg-slate-50"
                    }`}
                  >
                    <Icon className={`w-4 h-4 ${active ? "text-indigo-600" : "text-slate-400"}`} />
                    {item.label}
                  </Link>
                );
              })}
            </nav>
          </div>
        )}

        {/* Admin Section */}
        {isAdmin && (
          <div>
            <div className="px-3 text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">
              L&D Administration
            </div>
            <nav className="space-y-1">
              {adminLinks.map((item) => {
                const active = pathname === item.href;
                const Icon = item.icon;
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                      active
                        ? "bg-indigo-50 text-indigo-700 font-semibold border-l-4 border-indigo-600 pl-2"
                        : "text-slate-600 hover:text-slate-900 hover:bg-slate-50"
                    }`}
                  >
                    <Icon className={`w-4 h-4 ${active ? "text-indigo-600" : "text-slate-400"}`} />
                    {item.label}
                  </Link>
                );
              })}
            </nav>
          </div>
        )}
      </div>

      <div className="p-3 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-500">
        <div className="font-semibold text-slate-700 mb-1 flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full bg-emerald-500"></span>
          Adaptive AI Active
        </div>
        Pedagogical sequencing & citation grounding live.
      </div>
    </aside>
  );
}
