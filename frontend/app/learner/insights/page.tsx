"use client";

import { ReportPage } from "@/components/reports/report-view";

export default function LearnerInsightsPage() {
  return (
    <ReportPage
      audience="learner"
      title="AI Learning Insights"
      description="What you are good at, where you are weaker, why, and what to do next. Every statement is built from your own graded answers, and you can open the evidence behind it."
      roles={["learner", "manager", "instructor", "org_admin", "system_admin"]}
    />
  );
}
