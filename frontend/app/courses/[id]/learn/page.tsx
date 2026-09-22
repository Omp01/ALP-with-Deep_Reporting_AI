"use client";

import { useEffect } from "react";
import { useParams, useSearchParams, useRouter } from "next/navigation";

export default function CourseLearnRedirect() {
  const params = useParams();
  const searchParams = useSearchParams();
  const router = useRouter();

  const courseId = params.id as string;
  const itemId = searchParams.get("item") || searchParams.get("item_id");

  useEffect(() => {
    const query = new URLSearchParams({ course_id: courseId });
    if (itemId) query.set("item_id", itemId);
    router.replace(`/learner/learning?${query.toString()}`);
  }, [courseId, itemId, router]);

  return (
    <div className="flex min-h-screen items-center justify-center">
      <div className="animate-pulse text-sm text-fg-muted">Loading learning player...</div>
    </div>
  );
}
