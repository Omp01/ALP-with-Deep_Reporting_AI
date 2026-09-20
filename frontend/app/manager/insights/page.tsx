"use client";

import { ReportPage } from "@/components/reports/report-view";

export default function TeamInsightsPage() {
  return (
    <ReportPage
      audience="team"
      title="AI Team Insights"
      description="Which skills are weak across your team, who is stuck, who is improving, and who may need help. Every statement cites evidence you can open. Individual activity is not shown, only what bears on these questions."
      roles={["manager", "instructor", "org_admin", "system_admin"]}
    />
  );
}
