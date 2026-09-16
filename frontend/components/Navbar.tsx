"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { LogOut, User, Shield, Building2, Sparkles } from "lucide-react";

export function Navbar() {
  const router = useRouter();
  const [user, setUser] = useState<{ email?: string; full_name?: string; role?: string; organization?: { name: string } } | null>(null);

  useEffect(() => {
    if (typeof window !== "undefined") {
      const stored = localStorage.getItem("user");
      if (stored) {
        try {
          setUser(JSON.parse(stored));
        } catch (e) {}
      }
    }
  }, []);

  const handleLogout = () => {
    if (typeof window !== "undefined") {
      localStorage.removeItem("access_token");
      localStorage.removeItem("user");
    }
    router.push("/login");
  };

  const getRoleBadgeColor = (role?: string) => {
    switch (role) {
      case "org_admin":
      case "admin":
        return "bg-purple-100 text-purple-800 border-purple-200";
      case "manager":
        return "bg-amber-100 text-amber-800 border-amber-200";
      default:
        return "bg-blue-100 text-blue-800 border-blue-200";
    }
  };

  return (
    <header className="bg-white border-b border-slate-200 sticky top-0 z-40">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        {/* Brand */}
        <div className="flex items-center gap-3">
          <Link href="/" className="flex items-center gap-2">
            <div className="w-9 h-9 rounded-lg bg-indigo-600 flex items-center justify-center text-white font-bold text-lg shadow-sm">
              A
            </div>
            <span className="font-bold text-slate-900 text-lg tracking-tight">Adaptive LMS</span>
          </Link>
          <span className="hidden sm:inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium bg-slate-100 text-slate-700 border border-slate-200">
            <Building2 className="w-3.5 h-3.5 text-slate-500" />
            {user?.organization?.name || "Acme Corporation"}
          </span>
          <span className="hidden md:inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
            <Sparkles className="w-3 h-3 text-emerald-600" /> Deep Reporting AI
          </span>
        </div>

        {/* User profile & actions */}
        <div className="flex items-center gap-4">
          {user ? (
            <>
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-full bg-slate-100 border border-slate-300 flex items-center justify-center text-slate-700 text-sm font-semibold">
                  {user.full_name ? user.full_name[0] : "U"}
                </div>
                <div className="hidden sm:block text-left">
                  <div className="text-sm font-semibold text-slate-900 leading-none">{user.full_name || user.email}</div>
                  <div className="text-xs text-slate-500 mt-0.5 capitalize flex items-center gap-1.5">
                    <span className={`px-1.5 py-0.2 rounded border text-[10px] font-bold uppercase tracking-wider ${getRoleBadgeColor(user.role)}`}>
                      {user.role}
                    </span>
                  </div>
                </div>
              </div>

              <button
                onClick={handleLogout}
                title="Sign out"
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-200 text-sm font-medium text-slate-600 hover:text-slate-900 hover:bg-slate-50 transition-colors"
              >
                <LogOut className="w-4 h-4" />
                <span className="hidden sm:inline">Logout</span>
              </button>
            </>
          ) : (
            <Link
              href="/login"
              className="inline-flex items-center justify-center px-4 py-2 rounded-lg bg-indigo-600 text-white text-sm font-semibold hover:bg-indigo-700 transition-colors shadow-sm"
            >
              Sign In
            </Link>
          )}
        </div>
      </div>
    </header>
  );
}
