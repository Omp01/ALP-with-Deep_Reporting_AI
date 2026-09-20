"use client";

import { ReportPage } from "@/components/reports/report-view";

export default function CapabilityIntelligencePage() {
  return (
    <ReportPage
      audience="organization"
      title="Capability Intelligence"
      description="Which competencies are strong or weak across the organization, where coverage is thin, and where learning risk is concentrated."
      roles={["instructor", "org_admin", "system_admin"]}
    />
  );
}
