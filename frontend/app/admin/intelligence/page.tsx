"use client";

import { ReportPage } from "@/components/reports/report-view";

export default function LearningIntelligencePage() {
  return (
    <ReportPage
      audience="ld"
      title="Learning Intelligence"
      description="Which content is followed by better mastery, where learners get stuck, which competencies lack material, and which assessments give useful evidence. Associations are reported as associations, never as proof of cause."
      roles={["instructor", "org_admin", "system_admin"]}
    />
  );
}
