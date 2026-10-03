"use client";

import React from "react";
import { Navbar } from "@/components/Navbar";
import { Sidebar } from "@/components/Sidebar";
import { LearningIntelligenceCenter } from "@/components/reporting/learning-intelligence-center";

export default function ManagerDashboardPage() {
  return (
    <div className="min-h-screen bg-slate-50">
      <Navbar />
      <div className="flex">
        <Sidebar />
        <main className="flex-1 p-8 max-w-7xl">
          <LearningIntelligenceCenter />
        </main>
      </div>
    </div>
  );
}
